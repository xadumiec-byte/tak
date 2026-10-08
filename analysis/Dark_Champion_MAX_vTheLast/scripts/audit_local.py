"""Capture local checks without interpreting unavailable infrastructure as success."""
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
commands = [
    [sys.executable, "--version"],
    [sys.executable, "-m", "compileall", "-q", "services", "scripts", "tests"],
    [sys.executable, "-m", "pytest", "-q"],
    [sys.executable, "scripts/preflight.py"],
    ["docker", "compose", "config", "--quiet"],
    ["docker", "info"],
    ["bash", "scripts/colab_bootstrap.sh"],
    ["bash", "scripts/colab_run.sh"],
    ["nvidia-smi"],
]
results = []
for command in commands:
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                errors="replace", timeout=60)
        entry = {"command": command, "exit_code": result.returncode,
                 "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        entry = {"command": command, "exit_code": None, "error": str(exc)}
    results.append(entry)
    print(command, entry["exit_code"], flush=True)
(ROOT / "reports" / "LOCAL_COMMANDS.json").write_text(
    json.dumps({"environment": platform.platform(), "results": results}, indent=2), encoding="utf-8")
