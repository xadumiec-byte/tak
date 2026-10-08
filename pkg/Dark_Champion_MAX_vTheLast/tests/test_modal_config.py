import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from modal_config import (MODAL_RUNTIME_ENV, exclude_upload, modal_environment, ROOT,
                          REQUIRED_ENDPOINTS, REQUIRED_SECRETS)

def test_modal_runtime_defaults_bound_idle_gpu_and_research_work():
    assert MODAL_RUNTIME_ENV['RESEARCH_MAX_ROUNDS'] == '1'
    assert MODAL_RUNTIME_ENV['RESEARCH_QUERIES_PER_ROUND'] == '3'
    assert MODAL_RUNTIME_ENV['RESEARCH_RESULTS_PER_QUERY'] == '3'
    assert MODAL_RUNTIME_ENV['RESEARCH_MAX_SOURCES'] == '9'
    assert MODAL_RUNTIME_ENV['RESEARCH_QUERY_MAX_TOKENS'] == '300'
    assert MODAL_RUNTIME_ENV['RESEARCH_GAP_MAX_TOKENS'] == '300'
    assert MODAL_RUNTIME_ENV['RESEARCH_ANSWER_MAX_TOKENS'] == '2000'
    assert MODAL_RUNTIME_ENV['VLLM_MAX_MODEL_LEN'] == '32768'

def configured():
    env = {name + '_EXTERNAL_URL': ('rediss' if name == 'REDIS' else 'https') + '://control.example.com'
           for name in REQUIRED_ENDPOINTS}
    env.update({key: 'test-only-key' for key in REQUIRED_SECRETS})
    return env

def test_never_upload_credentials_caches_or_historical_pass():
    for name in ('.env', '.env.production', '.venv-modal/pyvenv.cfg', '.run/runtime.json',
                 'reports/LIVE_ACCEPTANCE.json', 'model.safetensors', 'release.zip'):
        assert exclude_upload(ROOT / name)
    assert not exclude_upload(ROOT / '.env.example')
    assert not exclude_upload(ROOT / 'services/gateway/app.py')

@pytest.mark.parametrize('url', ['http://localhost:6333', 'http://127.0.0.1:6333',
                               'http://0.0.0.0:6333', 'http://169.254.169.254:6333',
                               'http://public.example.com:6333'])
def test_external_endpoint_validation(url):
    env = configured(); env['QDRANT_EXTERNAL_URL'] = url
    with pytest.raises(ValueError): modal_environment(env)

def test_modal_resolves_owned_services_locally():
    env = configured(); env['RESEARCH_EXTERNAL_URL'] = 'https://stale.example.com'
    result = modal_environment(env)
    assert result['RESEARCH_URL'] == 'http://127.0.0.1:8090'
    assert result['VLLM_BASE_URL'] == 'http://127.0.0.1:8000/v1'
    assert result['GATEWAY_HOST'] == '0.0.0.0'
    assert result['AUXILIARY_MODE'] == 'external'

def test_missing_auth_and_missing_auxiliary_fail_closed():
    for key in ('SANDBOX_API_KEY', 'REDIS_EXTERNAL_URL'):
        env = configured(); env.pop(key)
        with pytest.raises(ValueError): modal_environment(env)

def test_only_owned_ssh_forwarding_accepts_loopback():
    from modal_control import PORTS
    env = configured()
    for name, port in PORTS.items():
        env[name + '_EXTERNAL_URL'] = ('redis' if name == 'REDIS' else 'http') + f'://127.0.0.1:{port}'
    with pytest.raises(ValueError): modal_environment(env)
    assert modal_environment(env, forwarded=True)['QDRANT_URL'] == 'http://127.0.0.1:6333'
    env['QDRANT_EXTERNAL_URL'] = 'http://169.254.169.254:6333'
    with pytest.raises(ValueError): modal_environment(env, forwarded=True)

def test_ssh_identity_fails_closed_before_launch(tmp_path):
    from modal_control import start_forwarder
    for route in ({'host':'example.com;bad', 'port':22, 'host_key':'ssh-ed25519 test'},
                  {'host':'example.com', 'port':22, 'host_key':''}):
        with pytest.raises(ValueError): start_forwarder({}, route, tmp_path)
    assert not (tmp_path / '.run').exists()

@pytest.mark.parametrize('address', ['1.1.1.1', '169.254.169.254', '0.0.0.0', 'container;command'])
def test_crawler_ssh_target_cannot_be_public_or_metadata(tmp_path, address):
    from modal_control import start_forwarder
    with pytest.raises(ValueError):
        start_forwarder({}, {'host':'control.example.com', 'port':22,
            'host_key':'ssh-ed25519 test', 'crawler_host':address}, tmp_path)
    assert not (tmp_path / '.run').exists()
