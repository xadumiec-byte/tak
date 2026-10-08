import hashlib
import os
import re
import uuid
from dataclasses import dataclass
import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as m

EMBEDDING_URL=os.getenv("EMBEDDING_URL","http://embedding-service:8092")
RERANKER_URL=os.getenv("RERANKER_URL","http://reranker-service:8093")
QDRANT_URL=os.getenv("QDRANT_URL","http://qdrant:6333")
COLLECTION=os.getenv("QDRANT_COLLECTION","dark_research") + "_hybrid_v1"
SIZE=int(os.getenv("RESEARCH_CHUNK_CHARS","4000"))
OVERLAP=int(os.getenv("RESEARCH_CHUNK_OVERLAP","400"))
if SIZE < 120 or not 0 <= OVERLAP < SIZE:
    raise ValueError("Invalid chunk size/overlap")

@dataclass
class Chunk:
    id: str
    url: str
    title: str
    text: str
    job_id: str
    document_id: str
    content_hash: str
    chunk_index: int
    attempt_id: str = "default"

def chunk_document(url, title, text, job_id="adhoc", attempt_id="default"):
    text=re.sub(r"\s+"," ",text or "").strip()
    content_hash=hashlib.sha256(text.encode()).hexdigest()
    document_id=str(uuid.uuid5(uuid.NAMESPACE_URL,url))
    chunks=[]
    for index,start in enumerate(range(0,len(text),SIZE-OVERLAP)):
        part=text[start:start+SIZE].strip()
        if part:
            ident=str(uuid.uuid5(uuid.NAMESPACE_URL,f"{job_id}\n{attempt_id}\n{document_id}\n{content_hash}\n{index}"))
            chunks.append(Chunk(ident,url,title,part,job_id,document_id,content_hash,index,attempt_id))
        if start+SIZE>=len(text): break
    return chunks

async def embed(texts):
    async with httpx.AsyncClient(timeout=180) as client:
        response=await client.post(f"{EMBEDDING_URL}/embed",json={"texts":texts})
        response.raise_for_status()
        data=response.json()
        if len(data["vectors"]) != len(texts) or len(data["sparse_vectors"]) != len(texts):
            raise ValueError("Embedding cardinality mismatch")
        return data

async def index_chunks(chunks):
    if not chunks: return
    data=await embed([c.text for c in chunks])
    client=AsyncQdrantClient(url=QDRANT_URL)
    try:
        if not await client.collection_exists(COLLECTION):
            try:
                await client.create_collection(COLLECTION,
                    vectors_config={"dense":m.VectorParams(size=len(data["vectors"][0]),distance=m.Distance.COSINE)},
                    sparse_vectors_config={"sparse":m.SparseVectorParams()})
            except Exception:
                if not await client.collection_exists(COLLECTION): raise
        info=await client.get_collection(COLLECTION)
        vectors=info.config.params.vectors
        if not isinstance(vectors,dict) or "dense" not in vectors or "sparse" not in (info.config.params.sparse_vectors or {}):
            raise ValueError("Incompatible collection schema; rebuild hybrid index")
        points=[]
        for chunk,dense,sparse in zip(chunks,data["vectors"],data["sparse_vectors"]):
            points.append(m.PointStruct(id=chunk.id,vector={"dense":dense,"sparse":m.SparseVector(**sparse)},
                payload={"job_id":chunk.job_id,"attempt_id":chunk.attempt_id,"document_id":chunk.document_id,"chunk_id":chunk.id,
                         "canonical_url":chunk.url,"url":chunk.url,"title":chunk.title,
                         "content_hash":chunk.content_hash,"chunk_index":chunk.chunk_index,"text":chunk.text}))
        await client.upsert(COLLECTION,points=points,wait=True)
    finally:
        await client.close()

async def retrieve(query,job_id,limit=12,attempt_id="default"):
    if not job_id: raise ValueError("job_id is required for isolated retrieval")
    limit=max(1,min(limit,24))
    data=await embed([query])
    client=AsyncQdrantClient(url=QDRANT_URL)
    scoped=m.Filter(must=[m.FieldCondition(key="job_id",match=m.MatchValue(value=job_id)),
                         m.FieldCondition(key="attempt_id",match=m.MatchValue(value=attempt_id))])
    try:
        if not await client.collection_exists(COLLECTION): return []
        result=await client.query_points(COLLECTION,
            prefetch=[m.Prefetch(query=data["vectors"][0],using="dense",filter=scoped,limit=48),
                      m.Prefetch(query=m.SparseVector(**data["sparse_vectors"][0]),using="sparse",filter=scoped,limit=48)],
            query=m.FusionQuery(fusion=m.Fusion.RRF),query_filter=scoped,limit=48,with_payload=True)
    finally:
        await client.close()
    docs=[{"id":str(p.id),"score":float(p.score),**(p.payload or {})} for p in result.points]
    if not docs:return []
    async with httpx.AsyncClient(timeout=180) as client:
        response=await client.post(f"{RERANKER_URL}/rerank",json={"query":query,"documents":[d["text"] for d in docs]})
        response.raise_for_status()
        order=[int(item["index"]) for item in response.json()["results"]]
    if len(order) != len(set(order)) or any(i < 0 or i >= len(docs) for i in order):
        raise ValueError("Invalid reranker indices")
    return [docs[i] for i in order[:limit]]
