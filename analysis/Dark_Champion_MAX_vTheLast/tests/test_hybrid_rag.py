import asyncio
import sys
from pathlib import Path
import httpx
from qdrant_client import AsyncQdrantClient
sys.path.insert(0,str(Path(__file__).parents[1]/'services/research'))
import rag

def test_real_inmemory_qdrant_hybrid_and_job_isolation(monkeypatch):
    async def scenario():
        client=AsyncQdrantClient(location=':memory:')
        original_close=client.close
        async def no_close(): pass
        monkeypatch.setattr(client,'close',no_close)
        monkeypatch.setattr(rag,'AsyncQdrantClient',lambda **kw:client)
        async def embed(texts):
            return {'vectors':[[1.,0.] for _ in texts],
                    'sparse_vectors':[{'indices':[7],'values':[1.]} for _ in texts]}
        monkeypatch.setattr(rag,'embed',embed)
        docs=rag.chunk_document('https://a.example','A','alpha evidence '*20,'job-A')
        others=rag.chunk_document('https://b.example','B','foreign evidence '*20,'job-B')
        stale=rag.chunk_document('https://a.example','Old','foreign stale attempt '*20,'job-A',attempt_id='stale-worker')
        await rag.index_chunks(docs+others+stale)
        original=httpx.AsyncClient
        def rerank(request):
            import json
            data=json.loads(request.content)
            assert all('foreign' not in d for d in data['documents'])
            return httpx.Response(200,json={'results':[{'index':i,'score':1.} for i in range(len(data['documents']))]})
        monkeypatch.setattr(rag.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(rerank),**kw))
        result=await rag.retrieve('alpha','job-A')
        assert result and all(d['job_id']=='job-A' for d in result)
        assert result[0]['chunk_id']==docs[0].id
        assert await rag.retrieve('alpha','missing-job')==[]
        info=await client.get_collection(rag.COLLECTION)
        assert 'dense' in info.config.params.vectors and 'sparse' in info.config.params.sparse_vectors
        await original_close()
    asyncio.run(scenario())
