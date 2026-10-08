from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
errors=[]; warnings=[]

def run(cmd):
    return subprocess.run(cmd, text=True, capture_output=True)

if shutil.which("nvidia-smi"):
    r=run(["nvidia-smi","--query-gpu=name,memory.total,compute_cap","--format=csv,noheader"])
    print("GPU:",r.stdout.strip())
    if "A100" not in r.stdout: warnings.append("GPU is not A100; retune VRAM defaults.")
else: errors.append("nvidia-smi missing")

env=ROOT/".env"
if not env.exists(): errors.append(".env missing; run scripts/bootstrap_env.py")
else:
    text=env.read_text()
    values=dict(line.split('=',1) for line in text.splitlines() if line and not line.startswith('#') and '=' in line)
    try:
        configured=int(values.get('VLLM_MAX_MODEL_LEN','32768'))
        verified=int(values.get('VLLM_VERIFIED_CONTEXT_LIMIT','262144'))
        if not 0 < configured <= verified: errors.append('Context exceeds verified checkpoint limit')
    except ValueError: errors.append('Verified checkpoint context limit is missing/invalid')
    for key in ["DARK_API_KEY","VLLM_API_KEY","CRAWL4AI_API_TOKEN","WEBUI_SECRET_KEY"]:
        line=next((x for x in text.splitlines() if x.startswith(key+"=")), "")
        value=line.partition("=")[2]
        if not value or value in {"local-vllm","generated-by-bootstrap"}:
            errors.append(f"{key} is unset/default")

for p in ROOT.rglob("*.py"):
    if not any(part.startswith('.venv') or part in {'__pycache__','.git'} for part in p.parts):
        r=run([sys.executable,"-m","py_compile",str(p)])
        if r.returncode: errors.append(f"compile failed: {p}: {r.stderr}")

print("\nWARNINGS")
for x in warnings: print("-",x)
print("\nERRORS")
for x in errors: print("-",x)
raise SystemExit(1 if errors else 0)
