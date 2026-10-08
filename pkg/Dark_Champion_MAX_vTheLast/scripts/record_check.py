"""Append command evidence without repeating immutable environment probes."""
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
command=sys.argv[1:]
if not command:raise SystemExit('Supply command and arguments')
result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,errors='replace')
path=ROOT/'reports/CONTINUATION_COMMANDS.json'
entries=json.loads(path.read_text()) if path.exists() else []
entries.append({'command':command,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
path.write_text(json.dumps(entries,indent=2),encoding='utf-8')
print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr)
raise SystemExit(result.returncode)
