import asyncio
import sys
from pathlib import Path
import fakeredis.aioredis

sys.path.insert(0, str(Path(__file__).parents[1] / 'services/research'))
import jobs

def test_queue_reclaim_and_stale_completion_fenced():
    async def scenario():
        r=fakeredis.aioredis.FakeRedis(decode_responses=True)
        await jobs.ensure_group(r)
        job=await jobs.enqueue(r, {'question':'example'})
        assert await r.hget('research:'+job,'status') == 'QUEUED'
        entry,_=await jobs.next_job(r,'worker1')
        _, token1, _=await jobs.claim(r,entry)
        assert await r.hget('research:'+job,'status') == 'RUNNING'
        await r.xclaim(jobs.STREAM,jobs.GROUP,'worker1',0,[entry[0]],idle=jobs.LEASE_MS+1)
        recovered,_=await jobs.next_job(r,'worker2')
        assert recovered[0] == entry[0]
        _, token2, _=await jobs.claim(r,recovered)
        assert not await jobs.finish(r,entry[0],job,token1,'DONE',{'bad':True})
        assert await jobs.finish(r,entry[0],job,token2,'DONE',{'answer':'good'})
        assert await r.hget('research:'+job,'status') == 'DONE'
        assert (await r.xpending(jobs.STREAM,jobs.GROUP))['pending'] == 0
        await r.aclose()
    asyncio.run(scenario())

def test_cancel_and_failed_jobs_are_terminal():
    async def scenario():
        r=fakeredis.aioredis.FakeRedis(decode_responses=True)
        await jobs.ensure_group(r)
        job=await jobs.enqueue(r, {'question':'example'})
        entry,_=await jobs.next_job(r,'worker')
        _,token,_=await jobs.claim(r,entry)
        assert await jobs.cancel(r,job)
        assert not await jobs.finish(r,entry[0],job,token,'DONE',{})
        assert not await jobs.heartbeat(r,entry[0],job,token,'worker')
        job2=await jobs.enqueue(r, {'question':'failure'})
        entry2,_=await jobs.next_job(r,'worker')
        _,token2,_=await jobs.claim(r,entry2)
        assert await jobs.finish(r,entry2[0],job2,token2,'FAILED','boom')
        assert await r.hget('research:'+job2,'status') == 'FAILED'
        assert not await jobs.cancel(r,job2)
        await r.aclose()
    asyncio.run(scenario())
