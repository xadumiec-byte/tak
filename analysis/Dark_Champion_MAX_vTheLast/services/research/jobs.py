"""Redis Streams queue, atomic state fencing and acknowledged completion."""
import json
import uuid
from redis.exceptions import ResponseError

STREAM = "research:jobs:v1"
GROUP = "research-workers"
TERMINAL = {"DONE", "FAILED", "CANCELLED"}
LEASE_MS = 120000
ENQUEUE = """
if redis.call('XLEN', KEYS[1]) >= 10000 then return 0 end
redis.call('HSET', KEYS[2], 'status', 'QUEUED', 'request', ARGV[1], 'state_history', '["QUEUED"]')
redis.call('XADD', KEYS[1], '*', 'job_id', ARGV[2])
return 1
"""

CLAIM = """
local status = redis.call('HGET', KEYS[1], 'status')
if not status or status == 'DONE' or status == 'FAILED' or status == 'CANCELLED' then return 0 end
redis.call('HSET', KEYS[1], 'status', 'CLAIMED', 'owner', ARGV[1])
local history = cjson.decode(redis.call('HGET', KEYS[1], 'state_history') or '[]')
table.insert(history, 'CLAIMED')
redis.call('HSET', KEYS[1], 'state_history', cjson.encode(history))
redis.call('HINCRBY', KEYS[1], 'attempt', 1)
return 1
"""
RUNNING = """
if redis.call('HGET', KEYS[1], 'owner') ~= ARGV[1] or redis.call('HGET', KEYS[1], 'status') ~= 'CLAIMED' then return 0 end
redis.call('HSET', KEYS[1], 'status', 'RUNNING')
local history = cjson.decode(redis.call('HGET', KEYS[1], 'state_history') or '[]')
table.insert(history, 'RUNNING')
redis.call('HSET', KEYS[1], 'state_history', cjson.encode(history))
return 1
"""
FINISH = """
if redis.call('HGET', KEYS[1], 'owner') ~= ARGV[1] or redis.call('HGET', KEYS[1], 'status') ~= 'RUNNING' then return 0 end
redis.call('HSET', KEYS[1], 'status', ARGV[2], ARGV[3], ARGV[4])
local history = cjson.decode(redis.call('HGET', KEYS[1], 'state_history') or '[]')
table.insert(history, ARGV[2])
redis.call('HSET', KEYS[1], 'state_history', cjson.encode(history))
redis.call('EXPIRE', KEYS[1], 86400)
redis.call('XACK', KEYS[2], ARGV[5], ARGV[6])
redis.call('XDEL', KEYS[2], ARGV[6])
return 1
"""
HEARTBEAT = """
if redis.call('HGET', KEYS[1], 'owner') ~= ARGV[1] or redis.call('HGET', KEYS[1], 'status') ~= 'RUNNING' then return 0 end
redis.call('XCLAIM', KEYS[2], ARGV[2], ARGV[3], 0, ARGV[4], 'JUSTID')
return 1
"""
CANCEL = """
local status = redis.call('HGET', KEYS[1], 'status')
if not status then return -1 end
if status == 'DONE' or status == 'FAILED' then return 0 end
redis.call('HSET', KEYS[1], 'status', 'CANCELLED')
local history = cjson.decode(redis.call('HGET', KEYS[1], 'state_history') or '[]')
table.insert(history, 'CANCELLED')
redis.call('HSET', KEYS[1], 'state_history', cjson.encode(history))
redis.call('EXPIRE', KEYS[1], 86400)
return 1
"""

async def ensure_group(client):
    try:
        await client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc): raise

async def enqueue(client, request):
    job_id = str(uuid.uuid4())
    if not await client.eval(ENQUEUE, 2, STREAM, f"research:{job_id}", json.dumps(request), job_id):
        raise ValueError("Research queue capacity exhausted")
    return job_id

async def next_job(client, consumer, reclaim_cursor="0-0"):
    recovered = await client.xautoclaim(STREAM, GROUP, consumer, LEASE_MS, start_id=reclaim_cursor, count=1)
    cursor, entries = recovered[:2]
    if not entries:
        batches = await client.xreadgroup(GROUP, consumer, {STREAM:">"}, count=1, block=1000)
        entries = batches[0][1] if batches else []
    return (entries[0] if entries else None), cursor

async def claim(client, entry):
    entry_id, fields = entry
    job_id = fields['job_id']
    key = f"research:{job_id}"
    token = str(uuid.uuid4())
    if not await client.eval(CLAIM, 1, key, token):
        await client.xack(STREAM, GROUP, entry_id)
        await client.xdel(STREAM, entry_id)
        return None
    if not await client.eval(RUNNING, 1, key, token): return None
    return job_id, token, await client.hget(key, "request")

async def finish(client, entry_id, job_id, token, status, value):
    field = "result" if status == "DONE" else "error"
    return await client.eval(FINISH, 2, f"research:{job_id}", STREAM, token, status,
                             field, json.dumps(value) if field == "result" else str(value), GROUP, entry_id)

async def heartbeat(client, entry_id, job_id, token, consumer):
    return await client.eval(HEARTBEAT, 2, f"research:{job_id}", STREAM, token, GROUP, consumer, entry_id)

async def cancel(client, job_id):
    return await client.eval(CANCEL, 1, f"research:{job_id}")
