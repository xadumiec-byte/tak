"""Single deployment addressing layer. Never source untrusted values as shell code."""
import json
import os
import ipaddress
from urllib.parse import urlsplit
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTS = {"VLLM": 8000, "GATEWAY": 8088, "RESEARCH": 8090,
         "SANDBOX": 8091, "EMBEDDING": 8092, "RERANKER": 8093,
         "SEARXNG": 8080, "CRAWL4AI": 11235, "QDRANT": 6333, "OPEN_WEBUI": 3000}
DOCKER_HOSTS = {"RESEARCH": "research", "SANDBOX": "sandbox-broker",
                "EMBEDDING": "embedding-service", "RERANKER": "reranker-service",
                "SEARXNG": "searxng", "CRAWL4AI": "crawl4ai", "QDRANT": "qdrant"}

def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    return values

def resolve(values):
    env = dict(values)
    native = env.get("COLAB_MODE", "false").lower() == "true"
    for name, default in PORTS.items():
        port = int(env.get(f"{name}_PORT", default))
        if not 1 <= port <= 65535:
            raise ValueError(f"Invalid {name} port")
        key = "VLLM_BASE_URL" if name == "VLLM" else f"{name}_URL"
        override = env.get(f"{name}_EXTERNAL_URL")
        if override:
            env[key] = override.rstrip("/")
        elif native:
            env[key] = f"http://127.0.0.1:{port}" + ("/v1" if name == "VLLM" else "")
        elif name in DOCKER_HOSTS:
            env[key] = f"http://{DOCKER_HOSTS[name]}:{port}"
    env["REDIS_URL"] = env.get("REDIS_EXTERNAL_URL") or (
        "redis://127.0.0.1:6379/0" if native else "redis://redis:6379/0")
    return env

def environment():
    return resolve({**read_env(ROOT / ".env"), **os.environ})

def validate_external(env):
    if env.get('AUXILIARY_MODE','docker') != 'external': return
    for name in ['REDIS','QDRANT','SEARXNG','CRAWL4AI','SANDBOX','OPEN_WEBUI']:
        value=env.get(name+'_EXTERNAL_URL')
        if not value: raise ValueError(name+'_EXTERNAL_URL is required in external mode')
        parsed=urlsplit(value)
        if not parsed.hostname: raise ValueError('Invalid external '+name+' address')
        try: local=not ipaddress.ip_address(parsed.hostname).is_global
        except ValueError: local=parsed.hostname=='localhost'
        allowed={'redis','rediss'} if name=='REDIS' else {'http','https'}
        if parsed.scheme not in allowed: raise ValueError('Invalid external protocol')
        if not local and parsed.scheme not in {'https','rediss'}:
            raise ValueError('Public external endpoints require TLS')

if __name__ == "__main__":
    validate_external(environment())
    target = ROOT / ".run" / "runtime.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(environment()), encoding="utf-8")
    target.chmod(0o600)
    print("Runtime configuration written to .run/runtime.json")
