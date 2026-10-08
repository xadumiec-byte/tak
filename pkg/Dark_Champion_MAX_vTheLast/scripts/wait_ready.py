import os
import time
import httpx
import redis
from runtime_config import environment

def targets(env):
    return {"vllm":env["VLLM_BASE_URL"]+"/models", "gateway":env["GATEWAY_URL"]+"/health",
            "research":env["RESEARCH_URL"]+"/health", "embedding":env["EMBEDDING_URL"]+"/health",
            "reranker":env["RERANKER_URL"]+"/health", "sandbox":env["SANDBOX_URL"]+"/health",
            "crawler":env["CRAWL4AI_URL"]+"/health", "qdrant":env["QDRANT_URL"]+"/healthz",
            "searxng":env["SEARXNG_URL"]+"/", "open-webui":env["OPEN_WEBUI_URL"]+"/health"}

def wait(env,timeout=900):
    pending=targets(env)
    pending["redis-worker"]=None
    deadline=time.monotonic()+timeout
    redis_client=redis.from_url(env["REDIS_URL"],socket_timeout=3)
    try:
        with httpx.Client(timeout=5,trust_env=False) as client:
            while pending and time.monotonic()<deadline:
                for name,url in list(pending.items()):
                    try:
                        if url is None:
                            ready=bool(redis_client.ping() and redis_client.get("research:worker_alive"))
                        else:
                            headers={"Authorization":"Bearer "+env.get("VLLM_API_KEY","")} if name=="vllm" else None
                            ready=200<=client.get(url,headers=headers).status_code<300
                        if ready:
                            print("READY",name,flush=True);pending.pop(name)
                    except Exception: pass
                if pending:time.sleep(2)
    finally:redis_client.close()
    if pending:raise RuntimeError("Not ready: "+", ".join(pending))

if __name__=="__main__":wait(environment())
