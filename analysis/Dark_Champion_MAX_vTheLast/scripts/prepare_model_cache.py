#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

def env_file_value(name: str) -> str | None:
    for filename in (".env", ".env.example"):
        p = Path(filename)
        if not p.exists():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return None

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.getenv("VLLM_MODEL") or env_file_value("VLLM_MODEL"))
    ap.add_argument("--revision", default=os.getenv("VLLM_MODEL_REVISION") or env_file_value("VLLM_MODEL_REVISION"))
    ap.add_argument("--local-dir", default="")
    ap.add_argument("--manifest", default="reports/MODEL_CACHE.json")
    args = ap.parse_args()
    if not args.model:
        print("VLLM_MODEL is not configured", file=sys.stderr)
        return 1

    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:
        print(f"huggingface_hub unavailable: {exc}", file=sys.stderr)
        return 1

    started = time.time()
    kwargs = {"repo_id": args.model}
    if args.revision:
        kwargs["revision"] = args.revision
    if args.local_dir:
        kwargs["local_dir"] = args.local_dir

    print(f"MODEL_CACHE: {args.model} revision={args.revision or 'default'}", flush=True)
    path = snapshot_download(**kwargs)
    elapsed = time.time() - started

    manifest = {
        "model": args.model,
        "revision_requested": args.revision,
        "resolved_path": str(path),
        "hf_home": os.getenv("HF_HOME"),
        "elapsed_seconds": round(elapsed, 3),
        "complete": True,
    }
    out = Path(args.manifest)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
