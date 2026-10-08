"""Recover pending jobs; token fencing prevents stale worker completion."""
import asyncio
import logging
import os
import uuid
import redis.asyncio as redis
from app import REDIS_URL, ResearchRequest, run_research
import jobs

async def lease(client, entry_id, job_id, token, consumer):
    while True:
        await asyncio.sleep(20)
        await client.set('research:worker_alive', consumer, ex=60)
        if not await jobs.heartbeat(client, entry_id, job_id, token, consumer):
            return

async def process(client, entry, consumer):
    claimed = await jobs.claim(client, entry)
    if not claimed: return
    job_id, token, raw = claimed
    entry_id = entry[0]
    if int(await client.hget('research:'+job_id, 'attempt')) > 3:
        await jobs.finish(client, entry_id, job_id, token, 'FAILED', 'Recovery attempt limit exceeded')
        return
    try:
        request = ResearchRequest.model_validate_json(raw)
    except Exception as exc:
        await jobs.finish(client, entry_id, job_id, token, 'FAILED', str(exc))
        return
    task = asyncio.create_task(run_research(request, job_id=job_id, attempt_id=token))
    keeper = asyncio.create_task(lease(client, entry_id, job_id, token, consumer))
    try:
        done, _ = await asyncio.wait([task, keeper], timeout=600, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            await jobs.finish(client, entry_id, job_id, token, 'DONE', task.result())
        elif keeper in done:
            keeper.result()
            # Cancellation or ownership transfer: never write a stale result.
        else:
            await jobs.finish(client, entry_id, job_id, token, 'FAILED', 'Research deadline exceeded')
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await jobs.finish(client, entry_id, job_id, token, 'FAILED', str(exc))
    finally:
        task.cancel(); keeper.cancel()
        await asyncio.gather(task, keeper, return_exceptions=True)

async def main():
    client = redis.from_url(REDIS_URL, decode_responses=True)
    consumer = f'{os.getpid()}-{uuid.uuid4()}'
    cursor = '0-0'
    group_ready = False
    try:
        while True:
            try:
                # Redis can still be starting when the worker process is launched.
                # Keep group creation inside the retry loop so a transient refusal
                # does not permanently kill the worker and block service readiness.
                if not group_ready:
                    await jobs.ensure_group(client)
                    group_ready = True
                await client.set('research:worker_alive', consumer, ex=60)
                entry, cursor = await jobs.next_job(client, consumer, cursor)
                if entry: await process(client, entry, consumer)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception('research worker failed; pending job remains recoverable')
                await asyncio.sleep(1)
    finally:
        await client.aclose()

if __name__ == '__main__':
    asyncio.run(main())
