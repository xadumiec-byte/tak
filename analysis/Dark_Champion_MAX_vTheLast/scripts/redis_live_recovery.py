"""Real Redis crash/reclaim acceptance on an isolated Modal validation session."""
import asyncio
import json
import os
import platform
import re
import shlex
import signal
import subprocess
import sys
import time
import traceback
import httpx
import redis.asyncio as redis
from runtime_config import ROOT
from service_manager import SERVICES, owned, start_identity

class RecoveryUnavailable(RuntimeError):
    pass

def control_command(env, script, root=ROOT):
    if env.get('DARK_DEPLOYMENT') != 'modal' or env.get('DARK_ACCEPTANCE_SESSION') != 'true':
        raise RecoveryUnavailable('Fault injection requires an isolated Modal acceptance session')
    directory = root / '.run/ssh'
    identity, known = directory / 'identity', directory / 'known_hosts'
    if not identity.exists() or not known.exists():
        raise RecoveryUnavailable('Pinned control SSH identity is unavailable')
    match = re.match(r'^\[([A-Za-z0-9.-]+)\]:(\d+)\s+ssh-ed25519\s+', known.read_text())
    if not match or not 1 <= int(match[2]) <= 65535:
        raise RecoveryUnavailable('Invalid pinned control SSH destination')
    return ['ssh', '-T', '-p', match[2], '-i', str(identity),
        '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', f'UserKnownHostsFile={known}', '-o', 'ConnectTimeout=10', 'root@' + match[1],
        'python3 -c ' + shlex.quote(script)]

def control(env, crash=False):
    script = '''import json,subprocess
name='dark-modal-redis-1'
data=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
labels=data['Config'].get('Labels') or {}
if data['Name']!='/'+name or labels.get('com.docker.compose.project')!='dark-modal' or labels.get('com.docker.compose.service')!='redis':
 raise RuntimeError('Refusing to alter a container outside the acceptance Redis service')
result={'container_id':data['Id'],'started_at':data['State']['StartedAt'],'restart_count':data['RestartCount']}
'''
    if crash:
        script += '''if not data['State']['Running']:raise RuntimeError('Redis is not running')
subprocess.run(['docker','kill','--signal=KILL',data['Id']],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['docker','start',data['Id']],check=True,stdout=subprocess.DEVNULL)
result.update(fault='Docker SIGKILL',process_recovery='explicit supervised service restart')
'''
    script += 'print(json.dumps(result),flush=True)\n'
    result = subprocess.run(control_command(env, script), capture_output=True, text=True,
                            timeout=30, check=True)
    return json.loads(result.stdout)

def start_worker(env):
    path = ROOT / '.run/pids/research-worker.json'
    if path.exists() and owned(json.loads(path.read_text())):
        raise RuntimeError('Refusing to start a duplicate research worker')
    with (ROOT / '.run/logs/research-worker.log').open('ab') as log:
        process = subprocess.Popen(SERVICES['research-worker'], cwd=ROOT / 'services/research',
            env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    record = {'pid': process.pid, 'start': start_identity(process.pid)}
    path.write_text(json.dumps(record))
    return record

async def run_recovery(env):
    if platform.system() != 'Linux':
        raise RecoveryUnavailable('Crash acceptance requires the managed Linux stack')
    before_docker = await asyncio.to_thread(control, env)
    sys.path.insert(0, str(ROOT / 'services/research'))
    import jobs
    client = redis.from_url(env['REDIS_URL'], decode_responses=True)
    evidence = {'status':'RUNNING','lease_ms':jobs.LEASE_MS,'docker_before':before_docker}
    worker_path = ROOT / '.run/pids/research-worker.json'
    worker = json.loads(worker_path.read_text())
    if not owned(worker) or worker['pid'] <= 1 or os.getpgid(worker['pid']) != worker['pid']:
        raise RuntimeError('Research worker PID ownership is invalid')
    stopped=False; killed=False; replacement=None
    marker='acceptance:redis-crash:'+str(time.time_ns())
    def checkpoint(phase):
        evidence['phase']=phase
        path=ROOT/'reports/REDIS_CRASH_EVIDENCE.json'
        temporary=path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        temporary.replace(path)
    try:
        if not (await client.info('persistence')).get('aof_enabled'):
            raise RuntimeError('Redis AOF must be enabled for crash acceptance')
        server=await client.info('server')
        evidence.update(redis_before=server['run_id'],redis_version=server['redis_version'])
        # Cancelled deliveries remain pending until the real reclaim lease expires.
        # Wait for normal worker cleanup instead of treating that lease as a fault.
        deadline=time.monotonic()+jobs.LEASE_MS/1000+30
        while await client.xlen(jobs.STREAM):
            if time.monotonic()>deadline:raise RecoveryUnavailable('Acceptance queue is not idle')
            await asyncio.sleep(.25)
        async with httpx.AsyncClient(timeout=30,trust_env=False) as http:
            response=await http.post(env['RESEARCH_URL']+'/research',json={
                'question':'According to https://docs.python.org/3/library/asyncio.html what is asyncio used for?',
                'max_rounds':1,'queries_per_round':2,'results_per_query':2})
            response.raise_for_status();job_id=response.json()['job_id']
            evidence['job_id']=job_id;checkpoint('QUEUED')
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                original=await client.hgetall('research:'+job_id)
                if original.get('status')=='RUNNING':break
                if original.get('status') in jobs.TERMINAL:raise RuntimeError('Fixture finished before crash')
                await asyncio.sleep(.05)
            else:raise TimeoutError('Worker did not claim crash fixture')
            if not owned(worker):raise RuntimeError('Worker ownership changed before fault')
            os.killpg(worker['pid'],signal.SIGSTOP);stopped=True
            original=await client.hgetall('research:'+job_id)
            if original['status']!='RUNNING':raise RuntimeError('Fixture finished before pause')
            entries=await client.xrange(jobs.STREAM,count=1)
            if len(entries)!=1 or entries[0][1]['job_id']!=job_id:raise RuntimeError('Unexpected stream entry')
            entry_id=entries[0][0];old_owner=original['owner']
            await client.set(marker,job_id,ex=600)
            durable=await client.execute_command('WAITAOF',1,0,5000)
            if int(durable[0])!=1:raise RuntimeError('AOF fsync barrier did not complete')
            evidence.update(aof_barrier=durable,original_attempt=int(original['attempt']),entry_id=entry_id)
            checkpoint('RUNNING_DURABLE')
            if not owned(worker):raise RuntimeError('Worker ownership changed before SIGKILL')
            os.killpg(worker['pid'],signal.SIGKILL);stopped=False;killed=True
            evidence['redis_fault']=await asyncio.to_thread(control,env,True)
            checkpoint('REDIS_SIGKILL')
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                try:
                    current=await client.info('server')
                    if current['run_id']!=server['run_id']:break
                except redis.RedisError:pass
                await asyncio.sleep(.25)
            else:raise TimeoutError('Redis did not restart')
            if await client.get(marker)!=job_id:raise RuntimeError('Durable marker was lost')
            restored=await client.hgetall('research:'+job_id)
            if restored.get('owner')!=old_owner or restored.get('status')!='RUNNING':
                raise RuntimeError('Durable running job was not restored')
            if not await client.xpending_range(jobs.STREAM,jobs.GROUP,min=entry_id,max=entry_id,count=1):
                raise RuntimeError('Pending delivery was lost')
            after_docker=await asyncio.to_thread(control,env)
            if after_docker['started_at']==before_docker['started_at']:raise RuntimeError('Redis process did not restart')
            evidence.update(redis_after=current['run_id'],docker_after=after_docker,pending_restored=True)
            checkpoint('REDIS_RESTORED')
            deadline=time.monotonic()+10
            while owned(worker) and time.monotonic()<deadline:await asyncio.sleep(.1)
            if owned(worker):raise RuntimeError('Killed worker has not been reaped')
            replacement=start_worker(env);evidence['replacement_worker']=replacement
            checkpoint('WAIT_REAL_LEASE_RECLAIM')
            deadline=time.monotonic()+jobs.LEASE_MS/1000+240;fenced=False
            while time.monotonic()<deadline:
                state=await client.hgetall('research:'+job_id)
                if state.get('owner')!=old_owner and state.get('status')=='RUNNING' and not fenced:
                    if await jobs.finish(client,entry_id,job_id,old_owner,'DONE',{'stale_callback':True}):
                        raise RuntimeError('Stale completion was accepted')
                    fenced=True;evidence['stale_completion_rejected']=True;checkpoint('RECLAIMED_FENCED')
                if state.get('status')=='DONE':break
                if state.get('status') in {'FAILED','CANCELLED'}:raise RuntimeError(str(state))
                await asyncio.sleep(.2)
            else:raise TimeoutError('Real lease reclaim did not finish')
            history=json.loads(state['state_history'])
            if not fenced or int(state['attempt'])<2 or history.count('RUNNING')<2:
                raise RuntimeError('Missing actual reclaim/fencing evidence')
            result=json.loads(state['result'])
            if not result.get('used_citations'):raise RuntimeError('Recovered research has no citations')
            if await client.xpending_range(jobs.STREAM,jobs.GROUP,min=entry_id,max=entry_id,count=1):
                raise RuntimeError('Recovered delivery was not acknowledged')
            evidence.update(status='PASS',attempts=int(state['attempt']),state_history=history,
                pending_acknowledged=True,recovered_used_citations=result['used_citations'])
            checkpoint('DONE');return evidence
    except Exception:
        evidence.update(status='FAIL',error=traceback.format_exc());checkpoint('FAILED');raise
    finally:
        if stopped and owned(worker):os.killpg(worker['pid'],signal.SIGCONT)
        if killed and (replacement is None or not owned(replacement)):
            if not worker_path.exists() or not owned(json.loads(worker_path.read_text())):start_worker(env)
        try:await client.delete(marker)
        except redis.RedisError:pass
        await client.aclose()
