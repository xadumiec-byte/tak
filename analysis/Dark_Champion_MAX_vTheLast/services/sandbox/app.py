import os
import shlex
import subprocess, tempfile
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Dark Code Sandbox")

# All file operations are confined to this workspace root (container-local).
WORKSPACE_ROOT = Path(os.getenv("SANDBOX_WORKSPACE", "/tmp/dark-workspace")).resolve()
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

class Run(BaseModel):
    code: str = Field(max_length=50000)
    timeout: int = Field(default=10, ge=1, le=30)

def resolve_in_workspace(path: str) -> Path:
    candidate = (WORKSPACE_ROOT / path.lstrip("/")).resolve()
    if candidate != WORKSPACE_ROOT and WORKSPACE_ROOT not in candidate.parents:
        raise HTTPException(400, "Path escapes sandbox workspace")
    return candidate

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/execute")
def execute(req: Run):
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        try:
            p = subprocess.run(
                ["python","-I","-c",req.code],
                cwd=d, capture_output=True, text=True,
                timeout=req.timeout, env={"PATH":"/usr/local/bin:/usr/bin:/bin"},
            )
            return {"exit_code":p.returncode,"stdout":p.stdout[-20000:],"stderr":p.stderr[-20000:]}
        except subprocess.TimeoutExpired as e:
            return {"exit_code":124,"stdout":(e.stdout or "")[-20000:],"stderr":"Execution timed out"}

class ShellRun(BaseModel):
    command: str = Field(min_length=1, max_length=8000)
    timeout: int = Field(default=30, ge=1, le=120)

@app.post("/shell")
def shell(req: ShellRun):
    # Explicit argv parsing keeps the command surface auditable (no silent re-splitting).
    try:
        argv = shlex.split(req.command)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid command quoting: {exc}") from exc
    if not argv:
        raise HTTPException(400, "Empty command")
    try:
        p = subprocess.run(
            argv, cwd=WORKSPACE_ROOT, capture_output=True, text=True,
            timeout=req.timeout, env={"PATH":"/usr/local/bin:/usr/bin:/bin"},
        )
        return {"exit_code":p.returncode,"stdout":p.stdout[-50000:],"stderr":p.stderr[-50000:]}
    except subprocess.TimeoutExpired:
        return {"exit_code":124,"stdout":"","stderr":"Execution timed out"}

class FilePath(BaseModel):
    path: str = Field(min_length=1, max_length=4096)

class FileWrite(FilePath):
    content: str = Field(max_length=1_000_000)

@app.post("/file/read")
def file_read(req: FilePath):
    target = resolve_in_workspace(req.path)
    if not target.is_file():
        raise HTTPException(404, "Not a file")
    return {"path": req.path, "content": target.read_text(errors="replace")[:1_000_000]}

@app.post("/file/write")
def file_write(req: FileWrite):
    target = resolve_in_workspace(req.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content)
    return {"path": req.path, "bytes": len(req.content.encode())}

@app.post("/file/list")
def file_list(req: FilePath):
    target = resolve_in_workspace(req.path)
    if not target.is_dir():
        raise HTTPException(404, "Not a directory")
    entries = []
    for item in sorted(target.iterdir()):
        if len(entries) >= 1000:
            break
        entries.append({"name": item.name, "type": "dir" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None})
    return {"path": req.path, "entries": entries}
