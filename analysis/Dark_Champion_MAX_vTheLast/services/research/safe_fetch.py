"""Validate DNS at connect time, pin IPs, preserve TLS hostname, recheck every redirect."""
import asyncio
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit, urljoin
import httpcore

class DomainBudget:
    def __init__(self,per_domain=3,max_requests=54):
        self.per_domain=per_domain;self.max_requests=max_requests;self.domains={};self.requests=0
    def consume(self,url):
        host=urlsplit(url).hostname
        urls=self.domains.setdefault(host,set())
        if self.requests>=self.max_requests or url not in urls and len(urls)>=self.per_domain:
            raise ValueError('Crawl domain/request budget exhausted')
        urls.add(url);self.requests+=1

def validate_url(url):
    p=urlsplit(url)
    if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password:
        raise ValueError('Only public HTTP(S) URLs without credentials are supported')
    if p.port not in {None,80,443}: raise ValueError('Unsupported crawl port')
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global: raise ValueError('Non-public crawl target')
    return p

class PublicBackend(httpcore.AsyncNetworkBackend):
    def __init__(self): self.backend=httpcore.AnyIOBackend()

    async def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
        host=host.decode() if isinstance(host,bytes) else host
        infos=await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo,host,port,0,socket.SOCK_STREAM),timeout or 10)
        addresses=sorted(dict.fromkeys(info[4][0] for info in infos),key=lambda ip:ipaddress.ip_address(ip).version)
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError('Crawler refused non-public DNS result')
        last=None
        for address in addresses:
            try:
                # This numeric address is the validated result; no second hostname lookup.
                # httpcore performs TLS with the original hostname on the returned stream.
                return await self.backend.connect_tcp(address,port,timeout,local_address,socket_options)
            except (OSError,httpcore.ConnectError,httpcore.ConnectTimeout) as exc: last=exc
        raise last

    async def connect_unix_socket(self,*args,**kwargs):
        raise ValueError('Unix sockets are prohibited for crawl targets')

    async def sleep(self,seconds): await asyncio.sleep(seconds)

async def fetch_html(url,max_bytes=2000000,max_redirects=5,pool_factory=None,domain_budget=None):
    factory=pool_factory or httpcore.AsyncConnectionPool
    async with factory(network_backend=PublicBackend(),ssl_context=ssl.create_default_context(),
                       max_connections=4,max_keepalive_connections=0) as pool:
        async with asyncio.timeout(45):
            for attempt in range(max_redirects+1):
                validate_url(url)
                if domain_budget:domain_budget.consume(url)
                async with pool.stream('GET',url,headers={'Accept-Encoding':'identity','User-Agent':'DarkChampionResearch/1.0'},
                    extensions={'timeout':{'connect':10,'read':15,'write':10,'pool':10}}) as response:
                    headers={k.decode().lower():v.decode('latin1') for k,v in response.headers}
                    if response.status in {301,302,303,307,308}:
                        if attempt==max_redirects or 'location' not in headers: raise ValueError('Invalid redirect chain')
                        url=urljoin(url,headers['location'])
                        continue
                    if response.status!=200: raise ValueError('Crawl HTTP status '+str(response.status))
                    if headers.get('content-encoding','identity').lower() != 'identity':
                        raise ValueError('Compressed crawl response refused')
                    kind=headers.get('content-type','').lower()
                    if not ('text/html' in kind or 'application/xhtml+xml' in kind or 'text/plain' in kind):
                        raise ValueError('Unsupported crawl content type')
                    data=bytearray()
                    async for chunk in response.aiter_stream():
                        if len(data)+len(chunk)>max_bytes: raise ValueError('Crawl body limit exceeded')
                        data.extend(chunk)
                    return bytes(data).decode('utf-8','replace'),url
    raise ValueError('Redirect limit exceeded')
