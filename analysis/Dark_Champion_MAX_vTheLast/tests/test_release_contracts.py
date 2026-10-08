import importlib.util
import sys
import uuid
import json
import httpx
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]

def load(monkeypatch, service, name):
    directory = ROOT / "services" / service
    monkeypatch.syspath_prepend(str(directory))
    monkeypatch.setenv("DARK_API_KEY", "test-key")
    spec = importlib.util.spec_from_file_location(name, directory / "app.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module

def test_gateway_auth_and_models(monkeypatch):
    gateway = load(monkeypatch, "gateway", "gateway_test")
    with TestClient(gateway.app) as client:
        assert client.get("/v1/models").status_code == 401
        response = client.get("/v1/models", headers={"Authorization": "Bearer test-key"})
        assert response.status_code == 200
        assert len(response.json()["data"]) == 5

def test_gateway_preserves_extensions(monkeypatch):
    gateway = load(monkeypatch, "gateway", "gateway_test")
    fields = {"top_p": 0.7, "stop": ["END"], "seed": 7,
              "tools": [], "tool_choice": "none", "parallel_tool_calls": False,
              "response_format": {"type": "json_object"},
              "stream_options": {"include_usage": True}, "vendor_extension": 42}
    request = gateway.ChatRequest(model="dark-code", messages=[], **fields)
    payload = request.model_dump(exclude_none=True)
    assert all(payload[key] == value for key, value in fields.items())

def test_tool_timeout_is_bounded(monkeypatch):
    gateway = load(monkeypatch, "gateway", "gateway_test")
    with pytest.raises(ValueError):
        gateway.ExecuteCodeRequest(code="", timeout=31)

def test_chunk_ids_are_qdrant_uuids(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "services" / "research"))
    import rag
    chunks = rag.chunk_document("https://example.org/a", "A", "hello world " * 500)
    assert chunks
    assert chunks == rag.chunk_document("https://example.org/a", "A", "hello world " * 500)
    for chunk in chunks:
        assert str(uuid.UUID(chunk.id)) == chunk.id

@pytest.mark.parametrize("stream", [False, True])
def test_gateway_forwarding_and_sse(monkeypatch, stream):
    gateway = load(monkeypatch, "gateway", "gateway_test")
    captured = []
    sse = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n'
    def upstream(request):
        captured.append(json.loads(request.content))
        assert request.headers["authorization"].startswith("Bearer ")
        if stream:
            return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx, "AsyncClient",
                        lambda **kwargs: original(transport=httpx.MockTransport(upstream), **kwargs))
    with TestClient(gateway.app) as client:
        response = client.post("/v1/chat/completions",
            headers={"Authorization": "Bearer test-key"},
            json={"model": "dark-code", "messages": [{"role": "user", "content": "hello"}],
                  "stream": stream, "seed": 13, "tools": [], "vendor_extension": "retained"})
        assert response.status_code == 200
        if stream:
            assert response.content == sse
            assert response.headers["content-type"].startswith("text/event-stream")
        else:
            assert response.json()["choices"][0]["message"]["content"] == "hello"
    assert captured[0]["model"] == gateway.VLLM_MODEL
    assert captured[0]["seed"] == 13
    assert captured[0]["vendor_extension"] == "retained"

def test_stream_connect_failure_closes_client(monkeypatch):
    gateway = load(monkeypatch, "gateway", "gateway_cleanup_test")
    instances = []
    original = httpx.AsyncClient
    def failed(request):
        raise httpx.ConnectError("offline", request=request)
    def create(**kwargs):
        client = original(transport=httpx.MockTransport(failed), **kwargs)
        instances.append(client)
        return client
    monkeypatch.setattr(gateway.httpx, "AsyncClient", create)
    with TestClient(gateway.app) as client:
        response = client.post("/v1/chat/completions", headers={"Authorization":"Bearer test-key"},
                               json={"model":"dark-code","messages":[],"stream":True})
        assert response.status_code == 502
    assert instances[0].is_closed

def test_research_stream_is_sse(monkeypatch):
    gateway = load(monkeypatch, "gateway", "gateway_research_test")
    def upstream(request):
        if request.method == "POST": return httpx.Response(200, json={"job_id":"job"})
        return httpx.Response(200, json={"status":"DONE","result":{"answer":"source [1]"}})
    original=httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx,"AsyncClient",lambda **kw: original(transport=httpx.MockTransport(upstream),**kw))
    with TestClient(gateway.app) as client:
        response=client.post('/v1/chat/completions',headers={'Authorization':'Bearer test-key'},
            json={'model':'dark-research','messages':[{'role':'user','content':'question'}],'stream':True})
        assert response.status_code == 200
        assert 'data: [DONE]' in response.text
        assert 'source [1]' in response.text
