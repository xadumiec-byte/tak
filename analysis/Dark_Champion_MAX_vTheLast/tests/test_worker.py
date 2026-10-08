import asyncio
import importlib.util
from pathlib import Path
import sys
import fakeredis.aioredis
import pytest

@pytest.mark.parametrize('invalid',[False,True])
def test_worker_success_and_poison_job_failure(monkeypatch,invalid):
    directory=Path(__file__).parents[1]/'services/research'
    monkeypatch.syspath_prepend(str(directory));monkeypatch.setenv('CRAWL4AI_API_TOKEN','fixture')
    spec=importlib.util.spec_from_file_location('research_worker_fixture',directory/'worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    async def research(request,job_id,attempt_id):
        assert job_id and attempt_id
        return {'answer':'Supported [1]'}
    monkeypatch.setattr(worker,'run_research',research)
    async def scenario():
        queue=fakeredis.aioredis.FakeRedis(decode_responses=True)
        await worker.jobs.ensure_group(queue)
        job=await worker.jobs.enqueue(queue,{'question':'x' if invalid else 'valid question'})
        entry,_=await worker.jobs.next_job(queue,'worker')
        await worker.process(queue,entry,'worker')
        assert await queue.hget('research:'+job,'status')==('FAILED' if invalid else 'DONE')
        assert (await queue.xpending(worker.jobs.STREAM,worker.jobs.GROUP))['pending']==0
        await queue.aclose()
    asyncio.run(scenario())

def test_worker_retries_initial_redis_group_creation(monkeypatch):
    directory=Path(__file__).parents[1]/'services/research'
    monkeypatch.syspath_prepend(str(directory));monkeypatch.setenv('CRAWL4AI_API_TOKEN','fixture')
    spec=importlib.util.spec_from_file_location('research_worker_startup_fixture',directory/'worker.py')
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    calls=[];heartbeats=[]
    class Client:
        async def set(self,key,value,ex): heartbeats.append((key,value,ex))
        async def aclose(self): pass
    client=Client()
    monkeypatch.setattr(worker.redis,'from_url',lambda *a,**kw:client)
    async def ensure_group(_client):
        calls.append('ensure')
        if len(calls)==1: raise ConnectionError('Redis not ready yet')
    async def next_job(*args): raise asyncio.CancelledError
    async def no_wait(_seconds): pass
    monkeypatch.setattr(worker.jobs,'ensure_group',ensure_group)
    monkeypatch.setattr(worker.jobs,'next_job',next_job)
    monkeypatch.setattr(worker.asyncio,'sleep',no_wait)
    with pytest.raises(asyncio.CancelledError): asyncio.run(worker.main())
    assert calls==['ensure','ensure']
    assert len(heartbeats)==1 and heartbeats[0][0]=='research:worker_alive'
