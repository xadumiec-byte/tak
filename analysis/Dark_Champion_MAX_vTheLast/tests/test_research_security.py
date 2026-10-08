import importlib.util
import sys
import pytest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "services" / "research" / "app.py"

def load_module(monkeypatch):
    monkeypatch.setenv("CRAWL4AI_API_TOKEN", "test-token")
    monkeypatch.syspath_prepend(str(MODULE.parent))
    spec = importlib.util.spec_from_file_location("research_app", MODULE)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module

def test_localhost_rejected(monkeypatch):
    module = load_module(monkeypatch)
    assert module.public_http_url("http://localhost:8000/private") is False
    assert module.public_http_url("http://127.0.0.1/private") is False

def test_non_http_rejected(monkeypatch):
    module = load_module(monkeypatch)
    assert module.public_http_url("file:///etc/passwd") is False

@pytest.mark.parametrize("url", ["http://10.0.0.1", "http://172.16.1.1",
    "http://192.168.1.1", "http://169.254.169.254", "http://[::1]",
    "http://[fc00::1]", "http://[fe80::1]"])
def test_private_addresses_rejected(monkeypatch, url):
    assert not load_module(monkeypatch).public_http_url(url)
