import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

def broker(monkeypatch):
    monkeypatch.setenv("SANDBOX_API_KEY", "sandbox-test")
    spec = importlib.util.spec_from_file_location("sandbox_broker_test", Path(__file__).parents[1] / "services/sandbox/broker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_isolation_contract(monkeypatch):
    m = broker(monkeypatch)
    options = m.runtime_options(m.Run(code="print(1)"))
    assert options['network_mode'] == 'none'
    assert options['read_only'] and options['cap_drop'] == ['ALL']
    assert options['pids_limit'] == 64 and options['mem_limit'] == '512m'
    assert options['user'] == '10001:10001'
    assert 'volumes' not in options and 'environment' not in options

@pytest.mark.parametrize('failure', [False, True])
def test_container_removed_on_success_and_failure(monkeypatch, failure):
    m = broker(monkeypatch)
    client = MagicMock()
    container = client.containers.create.return_value
    container.logs.return_value = json.dumps({'exit_code':0,'stdout':'hello','stderr':''}).encode()
    if failure:
        container.wait.side_effect = TimeoutError()
    monkeypatch.setattr(m.docker, 'from_env', lambda **kw: client)
    if failure:
        with pytest.raises(TimeoutError): m.run_isolated(m.Run(code=''))
    else:
        assert m.run_isolated(m.Run(code=''))['stdout'] == 'hello'
    container.remove.assert_called_once_with(force=True)
    client.close.assert_called_once()

def test_auth_and_output_bound(monkeypatch):
    m = broker(monkeypatch)
    client = MagicMock()
    client.containers.create.return_value.logs.return_value = json.dumps({'exit_code':0,'stdout':'x'*50000,'stderr':''}).encode()
    monkeypatch.setattr(m.docker, 'from_env', lambda **kw: client)
    with TestClient(m.app) as http:
        assert http.post('/execute',json={'code':''}).status_code == 401
        result=http.post('/execute',headers={'Authorization':'Bearer sandbox-test'},json={'code':''})
        assert result.status_code == 200
        assert len(result.json()['stdout']) == 40000
