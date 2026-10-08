#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,platform,re,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

def cmd(a):
    try:
        r=subprocess.run(a,capture_output=True,text=True,timeout=20,check=False)
        return r.returncode,r.stdout.strip(),r.stderr.strip()
    except Exception as e: return None,"",f"{type(e).__name__}: {e}"

def gpu():
    x=shutil.which("nvidia-smi")
    if not x: return {"available":False,"name":None,"memory_mb":None}
    rc,o,e=cmd([x,"--query-gpu=name,memory.total,driver_version","--format=csv,noheader,nounits"])
    if rc!=0 or not o: return {"available":False,"name":None,"memory_mb":None,"error":e}
    p=[v.strip() for v in o.splitlines()[0].split(",")]
    m=re.search(r"\d+",p[1]) if len(p)>1 else None
    return {"available":True,"name":p[0],"memory_mb":int(m.group()) if m else None,
            "driver_version":p[2] if len(p)>2 else None}

def detect():
    system=platform.system()
    modal_runtime = bool(os.environ.get('MODAL_TASK_ID'))
    colab=("COLAB_RELEASE_TAG" in os.environ or "COLAB_GPU" in os.environ or Path("/content").exists())
    g=gpu()
    if system=="Windows": c="WINDOWS_LOCAL"
    elif modal_runtime and system == 'Linux':
        memory = g.get('memory_mb')
        is_a100 = 'A100' in (g.get('name') or '').upper()
        c = ('MODAL_A100' if is_a100 and isinstance(memory, int) and memory >= 75000 else
             'MODAL_A100_40GB' if is_a100 and isinstance(memory, int) and memory >= 37500 else
             'MODAL_GPU_OTHER' if g['available'] else 'MODAL_CPU')
    elif colab and not g["available"]: c="COLAB_CPU"
    elif colab and g["available"]:
        is_a100 = "A100" in (g["name"] or "").upper()
        memory = g.get("memory_mb")
        c = "COLAB_A100" if is_a100 and isinstance(memory, int) and memory >= 75000 else ("COLAB_A100_40GB" if is_a100 and isinstance(memory, int) and memory >= 37500 else "COLAB_GPU_OTHER")
    elif system=="Linux": c="LINUX_LOCAL"
    else: c="UNKNOWN"
    return {"timestamp_utc":datetime.now(timezone.utc).isoformat(),"classification":c,
            "system":system,"platform":platform.platform(),"python":sys.version.split()[0],
            "executable":sys.executable,"is_colab":colab,"is_modal":modal_runtime,"gpu":g}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--require",choices=["any","linux","colab","colab-gpu","colab-a100","colab-a100-40gb","modal-a100-40gb","modal-a100"],default="any")
    p.add_argument("--report",default="reports/RUNTIME_ENVIRONMENT.json")
    a=p.parse_args(); d=detect()
    q=Path(a.report); q.parent.mkdir(parents=True,exist_ok=True)
    q.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(d,indent=2,ensure_ascii=False))
    allowed={"any":None,"linux":{"LINUX_LOCAL","COLAB_CPU","COLAB_GPU_OTHER","COLAB_A100","COLAB_A100_40GB","MODAL_CPU","MODAL_GPU_OTHER","MODAL_A100","MODAL_A100_40GB"},
             "colab":{"COLAB_CPU","COLAB_GPU_OTHER","COLAB_A100","COLAB_A100_40GB"},
             "colab-gpu":{"COLAB_GPU_OTHER","COLAB_A100","COLAB_A100_40GB"},"colab-a100":{"COLAB_A100"},"colab-a100-40gb":{"COLAB_A100","COLAB_A100_40GB"},
             "modal-a100-40gb":{"MODAL_A100","MODAL_A100_40GB"},"modal-a100":{"MODAL_A100"}}[a.require]
    if allowed is not None and d["classification"] not in allowed:
        print(f"BLOCKED_BY_ENVIRONMENT: require={a.require}, detected={d['classification']}",file=sys.stderr)
        return 2
    print("ENVIRONMENT_OK:",d["classification"]); return 0
if __name__=="__main__": raise SystemExit(main())
