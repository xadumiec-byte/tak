"""Native Linux supervisor with explicit auxiliary Docker topology and PID ownership."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import yaml
import httpx
from runtime_config import ROOT, environment, validate_external

RUN = ROOT / ".run"
SERVICES = {
    "vllm": ["bash", "gpu/start_vllm_a100.sh"],
    "embedding": [sys.executable, "-m", "uvicorn", "services.embedding.app:app", "--host", "127.0.0.1", "--port", "8092"],
    "reranker": [sys.executable, "-m", "uvicorn", "services.reranker.app:app", "--host", "127.0.0.1", "--port", "8093"],
    "research": [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8090"],
    "research-worker": [sys.executable, "worker.py"],
    "gateway": [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8088"],
}

def start_identity(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None

def owned(record):
    return start_identity(record["pid"]) == record["start"] and record["start"] is not None

def auxiliary_config(env):
    data = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    names = ["redis", "qdrant", "searxng", "crawl4ai", "open-webui", "sandbox-broker", "sandbox-runtime"]
    data["services"] = {n: data["services"][n] for n in names}
    for name, service in data["services"].items():
        service.pop("depends_on", None)
        service.pop("env_file", None)
        if "build" in service:
            service["build"]["context"] = str(ROOT)
    data["services"]["redis"]["ports"] = ["127.0.0.1:6379:6379"]
    data["services"]["sandbox-broker"]["ports"] = ["127.0.0.1:8091:8091"]
    ui = data["services"]["open-webui"]
    ui.pop("ports", None)
    ui["network_mode"] = "host"
    ui["environment"].update({"HOST": "127.0.0.1", "PORT": env.get("OPEN_WEBUI_PORT","3000"), "OPENAI_API_BASE_URL": env.get("UI_GATEWAY_URL","http://127.0.0.1:8088/v1")})
    search = data["services"]["searxng"]
    search["volumes"] = [str(ROOT / "infra/searxng/settings.yml") + ":/etc/searxng/settings.yml:ro"]
    return data

def compose(env, *args):
    subprocess.run(["docker", "compose", "-p", "dark-colab", "-f", str(RUN / "auxiliary.yml"), *args], cwd=ROOT, env=env, check=True)

def stop(env):
    for path in (RUN / "pids").glob("*.json"):
        record = json.loads(path.read_text())
        if owned(record):
            os.killpg(record["pid"], signal.SIGTERM)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not any(owned(json.loads(p.read_text())) for p in (RUN / "pids").glob("*.json")):
            break
        time.sleep(.2)
    for path in (RUN / "pids").glob("*.json"):
        record = json.loads(path.read_text())
        if owned(record): os.killpg(record["pid"], signal.SIGKILL)
        path.unlink()
    if env.get('AUXILIARY_MODE','docker') == 'docker' and (RUN / "auxiliary.yml").exists():
        compose(env, "stop")

def start(env):
    if sys.platform != "linux":
        raise SystemExit("Native Colab startup requires Linux")
    if env.get("COLAB_MODE", "false").lower() != "true":
        raise SystemExit("Set COLAB_MODE=true for native startup")
    env["VLLM_EXECUTABLE"] = str(ROOT / ".venv-vllm/bin/vllm")
    # Prove auxiliary support BEFORE installing/downloading models or starting inference.
    validate_external(env)
    local_aux = env.get('AUXILIARY_MODE','docker') == 'docker'
    if env.get('AUXILIARY_MODE','docker') not in {'docker','external'}:
        raise SystemExit('Expected AUXILIARY_MODE=docker or external')
    if local_aux: subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, env=env, check=True)
    (RUN / "pids").mkdir(parents=True, exist_ok=True)
    (RUN / "logs").mkdir(exist_ok=True)
    if any(owned(json.loads(p.read_text())) for p in (RUN / "pids").glob("*.json")):
        raise SystemExit("Services already running; stop before restarting")
    try:
        if local_aux:
            (RUN / "auxiliary.yml").write_text(yaml.safe_dump(auxiliary_config(env), sort_keys=False))
            compose(env, "build", "sandbox-runtime", "sandbox-broker")
            compose(env, "up", "-d", "--build")
        for name, command in SERVICES.items():
            command = list(command)
            if "--port" in command:
                key = {"embedding":"EMBEDDING", "reranker":"RERANKER", "research":"RESEARCH", "gateway":"GATEWAY"}[name]
                command[command.index("--port") + 1] = env.get(key + "_PORT", command[-1])
                if name == 'gateway':
                    command[command.index('--host') + 1] = env.get('GATEWAY_HOST', '127.0.0.1')
            cwd = ROOT / "services" / ("research" if name.startswith("research") else "gateway") if name.startswith("research") or name == "gateway" else ROOT
            with (RUN / "logs" / f"{name}.log").open("ab") as log:
                process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            (RUN / "pids" / f"{name}.json").write_text(json.dumps({"pid": process.pid, "start": start_identity(process.pid)}))
        subprocess.run([sys.executable, "scripts/wait_ready.py"], cwd=ROOT, env=env, check=True)
    except BaseException:
        stop(env)
        raise

def restart_inference(env):
    path=RUN/'pids/vllm.json'
    if not path.exists():
        raise RuntimeError('A managed inference process is required for the benchmark matrix')
    record=json.loads(path.read_text())
    identity=start_identity(record['pid'])
    if identity is not None and not owned(record): raise RuntimeError('Inference PID ownership changed')
    if owned(record):os.killpg(record['pid'],signal.SIGTERM)
    deadline=time.monotonic()+10
    while owned(record) and time.monotonic()<deadline:time.sleep(.2)
    if owned(record):os.killpg(record['pid'],signal.SIGKILL)
    env['VLLM_EXECUTABLE']=str(ROOT/'.venv-vllm/bin/vllm')
    start_time=time.perf_counter()
    with (RUN/'logs/vllm.log').open('wb') as log:
        process=subprocess.Popen(SERVICES['vllm'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    path.write_text(json.dumps({'pid':process.pid,'start':start_identity(process.pid)}))
    deadline=time.monotonic()+900
    with httpx.Client(timeout=5,trust_env=False) as client:
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Inference exited; inspect vllm.log')
            try:
                r=client.get(env['VLLM_BASE_URL']+'/models',headers={'Authorization':'Bearer '+env['VLLM_API_KEY']})
                if r.is_success:return {'startup_s':time.perf_counter()-start_time,'pid':process.pid}
            except httpx.HTTPError:pass
            time.sleep(2)
    os.killpg(process.pid,signal.SIGKILL)
    raise TimeoutError('Inference startup deadline exceeded')

if __name__ == "__main__":
    env = environment()
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "start": start(env)
    elif action == 'restart-inference':print(json.dumps(restart_inference(env)))
    elif action == 'aux-up':
        RUN.mkdir(exist_ok=True)
        (RUN/'auxiliary.yml').write_text(yaml.safe_dump(auxiliary_config(env),sort_keys=False))
        compose(env,'build','sandbox-runtime','sandbox-broker')
        compose(env,'up','-d','--build')
    elif action == "stop": stop(env)
    elif action == "status":
        for path in (RUN / "pids").glob("*.json"):
            print(path.stem, "UP" if owned(json.loads(path.read_text())) else "DOWN")
    else: raise SystemExit("Expected start, stop or status")
