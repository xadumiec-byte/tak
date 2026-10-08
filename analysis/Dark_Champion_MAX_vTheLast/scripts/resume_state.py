#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

STATE = Path("reports/RESUME_STATE.json")

def source_hash() -> str:
    h = hashlib.sha256()
    roots = [Path("services"), Path("scripts"), Path("tests")]
    files = []
    for root in roots:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for p in sorted(files):
        if p == STATE:
            continue
        h.update(str(p).encode())
        h.update(p.read_bytes())
    return h.hexdigest()

def load() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"gates": {}}

def save(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    s["updated_utc"] = datetime.now(timezone.utc).isoformat()
    s["source_hash"] = source_hash()
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATE)

def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=False).returncode

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark")
    ap.add_argument("--status", choices=["PASS","FAIL","BLOCKED"])
    ap.add_argument("--detail", default="")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    state = load()
    current_hash = source_hash()

    if state.get("source_hash") and state["source_hash"] != current_hash:
        state["source_changed_since_checkpoint"] = True

    if args.mark:
        if not args.status:
            ap.error("--mark requires --status")
        state.setdefault("gates", {})[args.mark] = {
            "status": args.status,
            "detail": args.detail,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source_hash": current_hash,
        }
        save(state)

    if args.show or not args.mark:
        print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
