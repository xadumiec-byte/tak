import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'services/research'))
import safe_fetch as sf

def test_dns_pinning_and_rebinding_refusal(monkeypatch):
    async def scenario():
        backend=sf.PublicBackend(); connected=[]
        async def connect(host,*args): connected.append(host); return 'stream'
        monkeypatch.setattr(backend.backend,'connect_tcp',connect)
        monkeypatch.setattr(sf.socket,'getaddrinfo',lambda *a:[(2,1,6,'',('8.8.8.8',443))])
        assert await backend.connect_tcp('public.example',443)=='stream'
        assert connected==['8.8.8.8']
        monkeypatch.setattr(sf.socket,'getaddrinfo',lambda *a:[(2,1,6,'',('127.0.0.1',443))])
        with pytest.raises(ValueError): await backend.connect_tcp('public.example',443)
        assert connected==['8.8.8.8']
    asyncio.run(scenario())

class Pool:
    responses=[]
    def __init__(self,**kw):self.requests=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    @asynccontextmanager
    async def stream(self,method,url,**kw):
        self.requests.append(url)
        yield self.responses[len(self.requests)-1]

class Response:
    def __init__(self,status,headers,body=b''):
        self.status=status; self.headers=headers; self.body=body
    async def aiter_stream(self):yield self.body

def test_redirect_to_private_address_rejected():
    Pool.responses=[Response(302,[(b'location',b'http://169.254.169.254/latest/meta-data')])]
    with pytest.raises(ValueError): asyncio.run(sf.fetch_html('https://public.example',pool_factory=Pool))

def test_response_budget_and_redirect_limit():
    Pool.responses=[Response(200,[(b'content-type',b'text/html')],b'x'*100)]
    with pytest.raises(ValueError): asyncio.run(sf.fetch_html('https://public.example',max_bytes=10,pool_factory=Pool))
    Pool.responses=[Response(302,[(b'location',b'https://public.example/loop')])]*3
    with pytest.raises(ValueError): asyncio.run(sf.fetch_html('https://public.example',max_redirects=2,pool_factory=Pool))

def test_successful_bounded_fetch():
    Pool.responses=[Response(200,[(b'content-type',b'text/html')],b'<p>evidence</p>')]
    assert asyncio.run(sf.fetch_html('https://public.example',pool_factory=Pool))[0]=='<p>evidence</p>'

def test_domain_and_request_budget():
    budget=sf.DomainBudget(per_domain=2,max_requests=3)
    budget.consume('https://a.example/1');budget.consume('https://a.example/2')
    with pytest.raises(ValueError):budget.consume('https://a.example/3')
    budget.consume('https://b.example/1')
    with pytest.raises(ValueError):budget.consume('https://b.example/1')
