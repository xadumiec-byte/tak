import importlib.util
import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("runtime_config", ROOT / "scripts/runtime_config.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

def test_native_addresses_have_no_docker_dns():
    env = config.resolve({"COLAB_MODE": "true", "VLLM_BASE_URL": "http://host.docker.internal:8000/v1"})
    for name in config.PORTS:
        key = "VLLM_BASE_URL" if name == "VLLM" else name + "_URL"
        assert "127.0.0.1" in env[key]
    assert env["REDIS_URL"] == "redis://127.0.0.1:6379/0"

def test_external_auxiliary_is_explicit():
    env = config.resolve({"COLAB_MODE": "true", "QDRANT_EXTERNAL_URL": "https://qdrant.example/"})
    assert env["QDRANT_URL"] == "https://qdrant.example"
    assert config.resolve({})["SANDBOX_URL"] == "http://sandbox-broker:8091"

def test_external_mode_fails_closed_without_auxiliaries():
    with pytest.raises(ValueError): config.validate_external({'AUXILIARY_MODE':'external'})
    env={'AUXILIARY_MODE':'external'}
    for name in ['QDRANT','SEARXNG','CRAWL4AI','SANDBOX','OPEN_WEBUI']:
        env[name+'_EXTERNAL_URL']='https://control.example/'+name.lower()
    env['REDIS_EXTERNAL_URL']='rediss://control.example:6379/0'
    config.validate_external(env)
    env['SANDBOX_EXTERNAL_URL']='http://public.example'
    with pytest.raises(ValueError):config.validate_external(env)

def test_auxiliary_plan_and_pid_ownership(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    import service_manager
    plan=service_manager.auxiliary_config(config.resolve({'COLAB_MODE':'true'}))
    services=plan['services']
    assert {'redis','qdrant','searxng','crawl4ai','open-webui','sandbox-broker','sandbox-runtime'}==set(services)
    assert services['open-webui']['environment']['OPENAI_API_BASE_URL']=='http://127.0.0.1:8088/v1'
    assert services['redis']['ports']==['127.0.0.1:6379:6379']
    assert plan['networks']['extraction']['internal']
    monkeypatch.setattr(service_manager,'start_identity',lambda pid:'new-owner')
    assert not service_manager.owned({'pid':123,'start':'old-owner'})
