import asyncio
import ipaddress
import json
import os
import re
import logging
import socket
import uuid
import redis.asyncio as redis
import jobs
from context import compile_context, local_tokenizer, validate_citations
from safe_fetch import fetch_html, DomainBudget, validate_url
from qdrant_client import AsyncQdrantClient
from rag import chunk_document, index_chunks, retrieve
from qdrant_client.models import Distance, VectorParams, PointStruct
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Dark Research", version="2.0.0-UNLOCKED")

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://searxng:8080").rstrip("/")
CRAWL4AI_URL = os.getenv("CRAWL4AI_URL", "http://crawl4ai:11235").rstrip("/")
CRAWL4AI_API_TOKEN = os.environ["CRAWL4AI_API_TOKEN"]
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://host.docker.internal:8000/v1").rstrip("/")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "local-vllm")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen3-Coder-30B-A3B-Instruct")
MAX_SOURCES = int(os.getenv("RESEARCH_MAX_SOURCES", "100"))
MAX_CHARS = int(os.getenv("RESEARCH_MAX_CHARS_PER_SOURCE", "50000"))
DEFAULT_ROUNDS = int(os.getenv("RESEARCH_MAX_ROUNDS", "10"))
DEFAULT_QUERIES = int(os.getenv("RESEARCH_QUERIES_PER_ROUND", "5"))
DEFAULT_RESULTS = int(os.getenv("RESEARCH_RESULTS_PER_QUERY", "5"))
QUERY_MAX_TOKENS = int(os.getenv("RESEARCH_QUERY_MAX_TOKENS", "700"))
GAP_MAX_TOKENS = int(os.getenv("RESEARCH_GAP_MAX_TOKENS", "700"))
ANSWER_MAX_TOKENS = int(os.getenv("RESEARCH_ANSWER_MAX_TOKENS", "16000"))
TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "300"))
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://embedding-service:8092")
RERANKER_URL = os.getenv("RERANKER_URL", "http://reranker-service:8093")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "dark_research")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

class ResearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=12000)
    max_rounds: int = Field(default=DEFAULT_ROUNDS, ge=1, le=10)
    queries_per_round: int = Field(default=DEFAULT_QUERIES, ge=2, le=10)
    results_per_query: int = Field(default=DEFAULT_RESULTS, ge=2, le=10)

@dataclass
class Source:
    title: str
    url: str
    snippet: str = ""
    text: str = ""

def public_http_url(url: str) -> bool:
    """Public HTTP(S) targets plus operator-declared internal CIDRs.

    Cloud metadata (169.254.x), loopback and unspecified addresses stay blocked;
    private ranges pass only when listed in RESEARCH_ALLOWED_INTERNAL_CIDRS.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
        except socket.gaierror:
            return False
        from safe_fetch import _address_allowed
        return bool(addresses) and all(_address_allowed(ipaddress.ip_address(a)) for a in addresses)
    except Exception:
        return False

async def llm(messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 16000) -> str:
    payload = {
        "model": VLLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{VLLM_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {VLLM_API_KEY}"},
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

def extract_json_array(text: str) -> list[str]:
    match = re.search(r"\[[\s\S]*?\]", text)
    if not match:
        return []
    try:
        value = json.loads(match.group(0))
        return [str(item).strip() for item in value if str(item).strip()]
    except json.JSONDecodeError:
        return []

async def plan_queries(question: str, count: int, context: str = "") -> list[str]:
    prompt = f"""Create exactly {count} diverse web-search queries for rigorous research.
Prefer primary sources, official documentation, papers, and recent authoritative material.
Return only a JSON array of strings.
Question: {question}
Known evidence/gaps: {context[:4000]}"""
    output = await llm([{"role": "user", "content": prompt}], temperature=0.3,
                       max_tokens=QUERY_MAX_TOKENS)
    queries = extract_json_array(output)
    if not queries:
        queries = [question]
    return queries[:count]

async def search(query: str, limit: int) -> list[Source]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{SEARXNG_URL}/search",
            params={"q": query, "format": "json", "language": "all", "safesearch": 0},
        )
        response.raise_for_status()
        results = []
        for item in response.json().get("results", [])[:limit]:
            url = item.get("url", "")
            if public_http_url(url):
                results.append(Source(
                    title=item.get("title", url),
                    url=url,
                    snippet=item.get("content", "") or "",
                ))
        return results

async def crawl(source: Source, domain_budget=None) -> Source:
    headers = {"Authorization": f"Bearer {CRAWL4AI_API_TOKEN}"}
    try:
        html, final_url = await fetch_html(source.url, domain_budget=domain_budget)
        payload = {"url": final_url, "html": html}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(f"{CRAWL4AI_URL}/extract", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            source.text = str(data.get("markdown", ""))[:MAX_CHARS]
            source.url = final_url
    except Exception as exc:
        # Failed or unsafe fetches must never be promoted to retrieved evidence.
        logging.warning('crawl rejected or failed: %s', type(exc).__name__)
        source.text = ""
    return source

def dedupe(sources: list[Source]) -> list[Source]:
    seen = set()
    unique = []
    for source in sources:
        parts = urlsplit(source.url)
        host = (parts.hostname or "").lower()
        if ":" in host: host = "[" + host + "]"
        port = parts.port
        if port and not (parts.scheme == "https" and port == 443 or parts.scheme == "http" and port == 80):
            host += ":" + str(port)
        query = urlencode([(k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True)
                           if not k.lower().startswith("utm_") and k.lower() not in {"fbclid","gclid"}])
        normalized = urlunsplit((parts.scheme.lower(),host,parts.path or "/",query,""))
        if normalized not in seen:
            seen.add(normalized)
            source.url = normalized
            unique.append(source)
    return unique[:MAX_SOURCES]

def evidence_block(sources: list[Source]) -> str:
    blocks = []
    for index, source in enumerate(sources, 1):
        text = source.text or source.snippet
        blocks.append(f"[{index}] {source.title}\nURL: {source.url}\n{text[:MAX_CHARS]}")
    return "\n\n".join(blocks)

def bounded_context(question, chunks, reserve):
    tokenizer = local_tokenizer()
    limit = int(os.getenv("VLLM_MAX_MODEL_LEN", "32768"))
    limit = min(limit, int(os.getenv("VLLM_VERIFIED_CONTEXT_LIMIT", "262144")))
    if tokenizer is not None and 0 < tokenizer.model_max_length < 1000000:
        limit = min(limit, tokenizer.model_max_length)
    return compile_context(question, chunks, limit, reserve=reserve, tokenizer=tokenizer)

async def identify_gaps(question, sources):
    chunks = []
    for source in sources:
        chunks.extend(vars(c) | {"chunk_id":c.id} for c in chunk_document(source.url, source.title, source.text))
    context = bounded_context("Identify missing evidence. Return SUFFICIENT if complete. Question: " + question, chunks, GAP_MAX_TOKENS)
    return await llm(context["messages"], temperature=.1, max_tokens=GAP_MAX_TOKENS)

async def synthesize(question, chunks):
    context = bounded_context(question, chunks, ANSWER_MAX_TOKENS)
    answer = await llm(context["messages"], temperature=.15, max_tokens=ANSWER_MAX_TOKENS)
    used = validate_citations(answer, context["citations"])
    references = "\n".join(f"[{i}] {context['citations'][i]['url']}" for i in used)
    return {"answer":answer + "\n\nSources\n" + references,
            "citations":context["citations"], "used_citations":used,
            "context":{k:context[k] for k in ("prompt_tokens","generation_reserve","estimator")}}






@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

async def query_memory(question: str, top_k: int = 10) -> list[dict]:
    """Persistent memory: semantic search over ALL past research jobs (no job scoping)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue
    top_k = max(1, min(top_k, 50))
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{EMBEDDING_URL}/embed", json={"texts": [question]})
            response.raise_for_status()
            vectors = response.json()["vectors"][0]
        client_q = AsyncQdrantClient(url=QDRANT_URL)
        try:
            if not await client_q.collection_exists(QDRANT_COLLECTION):
                return []
            result = await client_q.query_points(
                QDRANT_COLLECTION,
                query=vectors,
                query_filter=Filter(must=[FieldCondition(key="text", match=MatchValue(value=True))]),
                limit=top_k,
                with_payload=True,
            )
        finally:
            await client_q.close()
        return [{"id": str(p.id), "score": float(p.score), **(p.payload or {})} for p in result.points]
    except Exception:
        logging.getLogger("dark-research").exception("query_memory failed; continuing without persistent memory")
        return []

def explicit_sources(question: str) -> list[Source]:
    """Read user-specified source URLs through the same guarded crawl path."""
    sources = []
    for candidate in re.findall(r"https?://[^\s<>\"']+", question):
        url = candidate.rstrip('.,;!?)]}')
        try:
            validate_url(url)
        except ValueError:
            continue
        sources.append(Source(title=url, url=url))
        if len(sources) >= MAX_SOURCES:
            break
    return dedupe(sources)

async def run_research(request: ResearchRequest, job_id: str | None = None, attempt_id: str = "default") -> dict[str, Any]:
    job_id = job_id or str(uuid.uuid4())
    all_sources: list[Source] = explicit_sources(request.question)
    # Persistent memory: recall related past research before crawling.
    memory_hits = await query_memory(request.question, top_k=10)
    memory_block = "\n".join(
        f"[memory {i + 1}] score={hit['score']:.3f} url={hit.get('url', hit.get('id'))}\n{str(hit.get('text', ''))[:2000]}"
        for i, hit in enumerate(memory_hits)
    )
    if memory_block:
        request = request.model_copy(update={"question": request.question + "\n\nRELEVANT PRIOR RESEARCH (persistent memory):\n" + memory_block})
    gaps = ""
    queries_used: list[str] = []
    attempted_urls = set()
    domain_budget = DomainBudget(per_domain=3, max_requests=MAX_SOURCES*3)

    for round_index in range(request.max_rounds):
        queries = await plan_queries(request.question, request.queries_per_round, context=gaps if round_index else "")
        queries_used.extend(queries)
        batches = await asyncio.gather(*(search(query, request.results_per_query) for query in queries), return_exceptions=True)
        discovered = []
        for batch in batches:
            if isinstance(batch, list):
                discovered.extend(batch)
            else:
                logging.warning('search failed: %s', type(batch).__name__)
        all_sources = dedupe(all_sources + discovered)
        semaphore = asyncio.Semaphore(4)
        domain_counts = {}
        limited = []
        for source in all_sources:
            domain = urlsplit(source.url).hostname
            if domain_counts.get(domain,0) >= 3: continue
            domain_counts[domain] = domain_counts.get(domain,0) + 1
            limited.append(source)
        async def fetch(source):
            if source.text: return source
            if source.url in attempted_urls: return source
            attempted_urls.add(source.url)
            async with semaphore:
                result = await crawl(source, domain_budget=domain_budget)
                attempted_urls.add(result.url)
                return result
        crawled = await asyncio.gather(*(fetch(source) for source in limited), return_exceptions=True)
        all_sources = [item for item in crawled if isinstance(item, Source) and item.text]
        if not all_sources:
            continue
        gaps = await identify_gaps(request.question, all_sources)
        if gaps.strip().upper().startswith("SUFFICIENT"):
            break

    if not all_sources:
        raise HTTPException(status_code=502, detail="No usable research sources were collected")

    chunks = []
    hashes = set()
    for source in all_sources:
        document = chunk_document(source.url, source.title, source.text or source.snippet, job_id, attempt_id)
        if document and document[0].content_hash not in hashes:
            hashes.add(document[0].content_hash)
            chunks.extend(document)
    await index_chunks(chunks)
    retrieved = await retrieve(request.question, job_id=job_id, attempt_id=attempt_id)
    result = await synthesize(request.question, retrieved)
    return {
        **result,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "retrieval_mode": "dense+sparse+rrf+reranker",
        "queries": queries_used,
        "source_count": len(all_sources),
        "sources": [{"title": s.title, "url": s.url} for s in all_sources],
    }

@app.post("/research")
async def enqueue_research(request: ResearchRequest) -> dict[str, str]:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        job_id = await jobs.enqueue(r, request.model_dump())
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from exc
    finally:
        await r.aclose()
    return {"job_id": job_id, "status": "QUEUED"}

@app.get("/research/{job_id}")
async def research_status(job_id: str):
    r = redis.from_url(REDIS_URL, decode_responses=True)
    data = await r.hgetall(f"research:{job_id}")
    await r.aclose()
    if not data:
        raise HTTPException(404, "Unknown job")
    if "result" in data:
        data["result"] = json.loads(data["result"])
    if "state_history" in data: data["state_history"] = json.loads(data["state_history"])
    return {k:v for k,v in data.items() if k in {"status","result","error","attempt","state_history"}}

@app.delete("/research/{job_id}")
async def cancel_research(job_id: str):
    r = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        result = await jobs.cancel(r, job_id)
        if result < 0: raise HTTPException(404, "Unknown job")
        return {"cancelled": bool(result)}
    finally:
        await r.aclose()
