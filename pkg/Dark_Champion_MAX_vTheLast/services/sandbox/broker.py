"""Trusted Docker broker. Clients cannot choose images, mounts, commands or limits."""
import asyncio
import json
import os
import docker
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Dark Sandbox Broker")
KEY = os.environ["SANDBOX_API_KEY"]
IMAGE = os.getenv("SANDBOX_IMAGE", "dark-sandbox-runtime:local")
slots = asyncio.Semaphore(2)

class Run(BaseModel):
    code: str = Field(max_length=50000)
    timeout: int = Field(default=10, ge=1, le=30)

def runtime_options(request):
    return dict(image=IMAGE, command=["python", "-I", "/app/runner.py", request.model_dump_json()],
        network_mode="none", read_only=True, cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"], user="10001:10001",
        pids_limit=64, mem_limit="512m", memswap_limit="512m", nano_cpus=1000000000,
        tmpfs={"/tmp": "rw,noexec,nosuid,size=64m,mode=1777"},
        log_config=docker.types.LogConfig(type="json-file", config={"max-size": "128k", "max-file": "1"}),
        labels={"dark-champion": "sandbox-execution"})

def run_isolated(request):
    client = docker.from_env(timeout=request.timeout + 10)
    container = None
    try:
        container = client.containers.create(**runtime_options(request))
        container.start()
        completion = container.wait(timeout=request.timeout + 5)
        data = container.logs(stdout=True, stderr=False)
        if not data and isinstance(completion,dict) and completion.get('StatusCode'):
            return {'exit_code':int(completion['StatusCode']),'stdout':'','stderr':'Runtime terminated before response',
                    'output_limited':False,'timed_out':False}
        if len(data) > 250000:
            raise ValueError("Invalid oversized runtime response")
        result = json.loads(data)
        if not isinstance(result, dict) or not {"exit_code", "stdout", "stderr"}.issubset(result):
            raise ValueError("Invalid runtime result")
        # Runtime output is untrusted even when the generated code disrupts its wrapper.
        stdout = str(result["stdout"])[:40000]
        return {"exit_code": int(result["exit_code"]),
                "stdout": stdout, "stderr": str(result["stderr"])[:40000-len(stdout)],
                "output_limited": bool(result.get("output_limited")), "timed_out": bool(result.get("timed_out"))}
    finally:
        try:
            if container is not None:
                container.remove(force=True)
        finally:
            client.close()

@app.get("/health")
async def health():
    def check():
        client = docker.from_env(timeout=5)
        try:
            client.ping()
            client.images.get(IMAGE)
        finally:
            client.close()
    try:
        await asyncio.to_thread(check)
    except Exception:
        raise HTTPException(503, "Docker sandbox runtime unavailable")
    return {"status": "ok"}

@app.post("/execute")
async def execute(request: Run, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {KEY}":
        raise HTTPException(401, "Invalid sandbox key")
    if slots.locked():
        raise HTTPException(429, "Sandbox capacity exhausted")
    async with slots:
        # Thread owns cleanup; cancellation cannot discard a running container.
        task = asyncio.create_task(asyncio.to_thread(run_isolated, request))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
        except Exception:
            raise HTTPException(502, "Sandbox execution failed; inspect broker logs")
