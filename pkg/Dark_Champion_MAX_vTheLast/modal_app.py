"""Modal compute migration. Auxiliary Docker isolation remains on the control host."""
import os
import sys
from pathlib import Path
import modal

ROOT = Path(__file__).resolve().parent if modal.is_local() else Path('/app/dark-champion')
sys.path.insert(0, str(ROOT / 'scripts'))
from modal_config import MODAL_RUNTIME_ENV, exclude_upload

app = modal.App('dark-champion-max')
cache = modal.Volume.from_name('dark-champion-model-cache', create_if_missing=True)
reports = modal.Volume.from_name('dark-champion-validation', create_if_missing=True)

# Separate locked CPU and inference environments preserve the tested dependency boundary.
image = (modal.Image.from_registry(
    'nvidia/cuda:13.0.2-devel-ubuntu22.04@sha256:6b6617592b94e7dcc6ffbe6d00720eed27bc6e3b4f06b26b93b4070c31f57391',
    add_python='3.12')
    .apt_install('git', 'curl', 'build-essential', 'python3-dev', 'openssh-client')
    .pip_install('uv==0.12.23')
    .add_local_file(ROOT / 'requirements-control.lock', '/locks/control.lock', copy=True)
    .add_local_file(ROOT / 'requirements-inference.lock', '/locks/inference.lock', copy=True)
    .run_commands(
        'uv venv /opt/control --python 3.12',
        'uv pip install --python /opt/control/bin/python --torch-backend=cpu --require-hashes -r /locks/control.lock',
        'uv venv /opt/inference --python 3.12',
        'uv pip install --python /opt/inference/bin/python -r /locks/inference.lock')
    .env({'HF_HOME': '/cache/hf', 'VLLM_CACHE_ROOT': '/cache/vllm',
          'TOKENIZERS_PARALLELISM': 'false', 'FLASHINFER_WORKSPACE_BASE': '/cache',
          'PYTHONPATH': '/app/dark-champion', 'DARK_GPU_PROFILE': 'a100-80gb',
          **MODAL_RUNTIME_ENV})
    .add_local_dir(ROOT, '/app/dark-champion', ignore=exclude_upload))

def prepare_runtime(route=None, acceptance=False):
    import subprocess
    root = Path('/app/dark-champion')
    os.chdir(root)
    sys.path.insert(0, str(root / 'scripts'))
    from runtime_config import read_env
    from modal_config import modal_environment
    values = {**read_env(root / '.env.example'), **os.environ}
    transport = None
    if route:
        from modal_control import start_forwarder
        transport = start_forwarder(values, route, root)
    env = modal_environment(values, forwarded=transport is not None)
    if acceptance:
        env['DARK_ACCEPTANCE_SESSION'] = 'true'
    else:
        env.pop('DARK_ACCEPTANCE_SESSION', None)
    # Reports, PID records and credentials must not enter the model cache volume.
    (root / 'reports').mkdir(exist_ok=True)
    for name, target in (('.venv-control', '/opt/control'), ('.venv-vllm', '/opt/inference')):
        path = root / name
        if not path.exists(): path.symlink_to(target, target_is_directory=True)
    from release_manifest import source_hash
    report_dir = Path('/validation') / source_hash()
    report_dir.mkdir(parents=True, exist_ok=True)
    # Generation-specific directory avoids carrying PASS across source revisions.
    import shutil
    source_reports = root / 'reports'
    if not source_reports.is_symlink():
        for path in source_reports.iterdir():
            if path.is_file(): shutil.copy2(path, report_dir / path.name)
        shutil.rmtree(source_reports)
        source_reports.symlink_to(report_dir, target_is_directory=True)
    subprocess.run(['/opt/control/bin/python', 'scripts/runtime_config.py'], env=env, check=True)
    subprocess.run(['/opt/control/bin/python', 'scripts/detect_environment.py',
                    '--require', 'modal-a100'], env=env, check=True)
    return root, env, transport

def persist_volumes():
    cache.commit()
    reports.commit()

@app.function(image=image, gpu='A100-80GB', cpu=8, memory=65536,
              min_containers=0, max_containers=1, scaledown_window=10,
              timeout=1800, startup_timeout=1800, include_source=False,
              secrets=[modal.Secret.from_name('dark-champion-max-runtime-v1')],
              volumes={'/cache': cache, '/validation': reports})
@modal.concurrent(max_inputs=8)
@modal.web_server(8088, startup_timeout=1800)
def serve():
    import subprocess
    sys.path.insert(0, '/app/dark-champion/scripts')
    from modal_production import ensure_control
    # desktop=False keeps the legacy -R 8088 validation transport; the desktop
    # launcher (scripts/modal_desktop.py) uses ensure_control(desktop=True) with a
    # SOCKS tunnel instead.
    control, private_route = ensure_control(Path('/app/dark-champion'))
    root, env, transport = prepare_runtime(private_route)
    subprocess.run(['/opt/control/bin/python', 'scripts/service_manager.py', 'start'],
                   cwd=root, env=env, check=True)
    persist_volumes()

@app.function(image=image, gpu='A100-80GB', cpu=8, memory=65536,
              min_containers=0, max_containers=1, scaledown_window=10,
              timeout=1800, startup_timeout=1800, include_source=False,
              secrets=[modal.Secret.from_name('dark-champion-max-runtime-v1')],
              volumes={'/cache': cache, '/validation': reports})
@modal.concurrent(max_inputs=8)
def ui_status():
    """Readiness probe for the desktop launcher: gateway + UI through one SSH hop."""
    import socket
    sys.path.insert(0, '/app/dark-champion/scripts')
    from modal_production import ensure_control
    from modal_control import start_forwarder
    values = {**os.environ}
    control, private_route = ensure_control(Path('/app/dark-champion'), desktop=True)
    transport = start_forwarder(values, private_route, Path('/app/dark-champion'))
    try:
        def probe(port):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=5): return True
            except OSError: return False
        return {'gateway': probe(8088), 'ui': probe(3000)}
    finally:
        transport.terminate(); transport.wait(timeout=10)

@app.function(image=image, gpu='A100-80GB', cpu=8, memory=65536,
              max_containers=1, timeout=3600, include_source=False,
              volumes={'/cache': cache, '/validation': reports})
def validate(matrix=False, route=None, diagnostic=False, repair_window=0, gates=""):
    """Use the canonical live runner inside the actual GPU environment."""
    import subprocess
    root, env, transport = prepare_runtime(route, acceptance=True)
    def outcome(result):
        return {**result, 'report_prefix': (root / 'reports').resolve().name}
    if not 0 <= repair_window <= 1200:
        raise ValueError('Repair window must be between 0 and 1200 seconds')
    try:
        startup = subprocess.run(['/opt/control/bin/python', 'scripts/service_manager.py', 'start'],
                                 cwd=root, env=env, text=True, capture_output=True)
        startup_log = startup.stdout + startup.stderr
        for key in ('DARK_API_KEY', 'VLLM_API_KEY', 'SANDBOX_API_KEY', 'CRAWL4AI_API_TOKEN'):
            startup_log = startup_log.replace(env.get(key, '\0'), '[REDACTED]')
        (root / 'reports/MODAL_STARTUP.log').write_text(startup_log)
        if startup.returncode:
            return outcome({'status': 'REVISE', 'startup_exit': startup.returncode})
        if diagnostic:
            rc = subprocess.run(['/opt/control/bin/python', 'scripts/research_diagnostic.py', '--lifecycle'], cwd=root, env=env).returncode
            return outcome({'status': 'REVISE', 'diagnostic_exit': rc})
        if gates:
            rc = subprocess.run(['/opt/control/bin/python', 'scripts/live_acceptance.py', '--gates', gates], cwd=root, env=env).returncode
            return outcome({'status': 'REVISE', 'focused_exit': rc})
        command = ['/opt/control/bin/python', 'scripts/live_acceptance.py', '--restart', '--baseline']
        baseline = subprocess.run(command, cwd=root, env=env).returncode
        if baseline: return outcome({'status': 'REVISE', 'baseline_exit': baseline})
        if matrix:
            rc = subprocess.run(command[:-1] + ['--matrix'], cwd=root, env=env).returncode
            return outcome({'status': 'READY' if rc == 0 else 'REVISE', 'matrix_exit': rc})
        return outcome({'status': 'REVISE', 'baseline_exit': 0, 'matrix': 'NOT TESTED'})
    finally:
        if repair_window:
            import time
            persist_volumes()
            print('REPAIR_WINDOW_OPEN', repair_window, flush=True)
            deadline = time.monotonic() + repair_window
            while time.monotonic() < deadline and not (root / '.run/end-repair').exists():
                time.sleep(5)
        try:
            subprocess.run(['/opt/control/bin/python', 'scripts/service_manager.py', 'stop'],
                           cwd=root, env=env, check=False)
        finally:
            import shutil
            logs = root / 'reports/runtime_logs'
            logs.mkdir(exist_ok=True)
            for path in (root / '.run/logs').glob('*.log'):
                text = path.read_text(errors='replace')
                for key in ('DARK_API_KEY', 'VLLM_API_KEY', 'SANDBOX_API_KEY', 'CRAWL4AI_API_TOKEN'):
                    text = text.replace(env.get(key, '\0'), '[REDACTED]')
                (logs / path.name).write_text(text)
            persist_volumes()
            if transport:
                transport.terminate()
                transport.wait(timeout=10)

@app.local_entrypoint()
def main(matrix: bool = False, diagnostic: bool = False, repair_window: int = 0, gates: str = ""):
    """Own the complete bounded control/GPU session and always tear down the VM."""
    import json
    import time
    from modal_control import local_keys
    if matrix and gates:raise ValueError('Focused gates cannot run the matrix')
    values, private, public = local_keys(ROOT)
    control_image = (modal.Image.from_registry('ubuntu:24.04')
        .env({'DEBIAN_FRONTEND': 'noninteractive', 'PYTHONPATH': '/app/dark-champion/scripts'})
        .apt_install('docker.io', 'docker-compose-v2', 'openssh-server', 'python3',
                     'python3-yaml', 'python3-httpx', 'curl')
        .add_local_dir(ROOT, '/app/dark-champion', copy=True, ignore=exclude_upload))
    sandbox = None
    result = {}
    from release_manifest import source_hash
    initial_prefix = source_hash()
    if not 0 <= repair_window <= 1200:
        raise ValueError('Repair window must be between 0 and 1200 seconds')
    try:
        sandbox = modal.Sandbox.create('python3', '/app/dark-champion/scripts/modal_control.py',
            app=app, image=control_image, runtime='vm', cpu=4, memory=8192, timeout=5400,
            secrets=[modal.Secret.from_dict({**values, 'MODAL_CONTROL_PUBLIC_KEY': public})],
            unencrypted_ports=[22])
        (ROOT / '.run' / 'modal_control_session.json').write_text(json.dumps({'sandbox_id': sandbox.object_id}))
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            if sandbox.poll() is not None:
                print(sandbox.stdout.read()); print(sandbox.stderr.read())
                raise RuntimeError('Control VM exited before service readiness')
            check = sandbox.exec('test', '-f', '/app/dark-champion/.run/control-ready')
            check.wait()
            if check.returncode == 0: break
            time.sleep(5)
        else: raise TimeoutError('Control VM service readiness deadline')
        identity = sandbox.exec('cat', '/etc/ssh/ssh_host_ed25519_key.pub')
        host_key = identity.stdout.read(); identity.wait()
        if identity.returncode: raise RuntimeError('Could not pin control SSH host identity')
        host, port = sandbox.tunnels()[22].tcp_socket
        crawler = sandbox.exec('docker', 'inspect', 'dark-modal-crawl4ai-1', '--format',
            '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
        crawler_host = crawler.stdout.read().strip(); crawler.wait()
        if crawler.returncode: raise RuntimeError('Could not resolve isolated crawler address')
        secret = modal.Secret.from_dict({**values, 'MODAL_CONTROL_PRIVATE_KEY': private})
        result = validate.with_options(secrets=[secret]).remote(matrix,
            {'host': host, 'port': port, 'host_key': host_key, 'crawler_host': crawler_host}, diagnostic=diagnostic, repair_window=repair_window, gates=gates)
        print(result)
    finally:
        if sandbox: sandbox.terminate()
        prefix = result.get('report_prefix', initial_prefix)
        try:
            for entry in reports.listdir(prefix, recursive=True):
                if entry.type != modal.volume.FileEntryType.FILE: continue
                relative = Path(entry.path).relative_to(prefix)
                target = ROOT / 'reports' / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b''.join(reports.read_file(entry.path)))
        except modal.exception.NotFoundError:
            pass  # No GPU runtime reached; control/build failure remains in local log.
