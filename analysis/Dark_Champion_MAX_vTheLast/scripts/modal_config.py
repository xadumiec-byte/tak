"""Modal deployment contract; validation is independent of the cloud SDK."""
from pathlib import Path
import ipaddress
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENDPOINTS = ("REDIS", "QDRANT", "SEARXNG", "CRAWL4AI", "SANDBOX", "OPEN_WEBUI")
REQUIRED_SECRETS = ("DARK_API_KEY", "VLLM_API_KEY", "SANDBOX_API_KEY", "CRAWL4AI_API_TOKEN")

# Favor scale-to-zero cost and bounded default research work on Modal. Per-request
# research limits remain overridable by trusted callers of the research service.
MODAL_RUNTIME_ENV = {
    'VLLM_MAX_MODEL_LEN': '32768',
    'RESEARCH_MAX_ROUNDS': '1',
    'RESEARCH_QUERIES_PER_ROUND': '3',
    'RESEARCH_RESULTS_PER_QUERY': '3',
    'RESEARCH_MAX_SOURCES': '9',
    'RESEARCH_QUERY_MAX_TOKENS': '300',
    'RESEARCH_GAP_MAX_TOKENS': '300',
    'RESEARCH_ANSWER_MAX_TOKENS': '2000',
}

def exclude_upload(path):
    path = Path(path)
    try:
        parts = path.relative_to(ROOT).parts
    except ValueError:
        parts = path.parts
    return any(p.startswith('.venv') or p in {'.git', '.run', '.cache', '__pycache__',
        '.pytest_cache', '.pytest-temp', 'reports', 'model_cache', 'hf_cache'} for p in parts) or (
        path.name.startswith('.env') and path.name != '.env.example') or path.suffix in {
        '.zip', '.pyc', '.safetensors', '.bin', '.pt', '.pth', '.onnx'}

def modal_environment(values, *, forwarded=False):
    """Reject unreachable loopbacks and unsafe public transports before GPU startup."""
    from runtime_config import resolve, validate_external
    env = dict(values)
    env.update(COLAB_MODE='true', AUXILIARY_MODE='external', DARK_DEPLOYMENT='modal',
               GATEWAY_HOST='0.0.0.0', VLLM_HOST='127.0.0.1')
    for name in REQUIRED_ENDPOINTS:
        value = env.get(name + '_EXTERNAL_URL', '')
        parsed = urlsplit(value)
        if not parsed.hostname:
            raise ValueError(name + '_EXTERNAL_URL is required')
        if parsed.hostname.lower() == 'localhost':
            raise ValueError(name + ' points to loopback instead of the external control host')
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address and (address.is_unspecified or address.is_link_local or
                        (address.is_loopback and not (forwarded and parsed.hostname == '127.0.0.1'))):
            raise ValueError(name + ' points to an unreachable or unsafe address')
    for key in REQUIRED_SECRETS:
        if not env.get(key) or env[key] in {'generated-by-bootstrap', 'local-vllm'}:
            raise ValueError(key + ' is required in Modal Secret')
    validate_external(env)
    # These processes belong to this single Modal container, never to external overrides.
    for name in ('VLLM', 'GATEWAY', 'RESEARCH', 'EMBEDDING', 'RERANKER'):
        env.pop(name + '_EXTERNAL_URL', None)
    return resolve(env)
