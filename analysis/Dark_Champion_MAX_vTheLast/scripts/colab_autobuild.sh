#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/cache_env.sh
PYTHON="${PYTHON:-python}"

mark() {
  "$PYTHON" scripts/resume_state.py --mark "$1" --status "$2" --detail "${3:-}"
}

gate_passed() {
  "$PYTHON" - "$1" <<'PY'
import json,sys
from pathlib import Path
name=sys.argv[1]
p=Path("reports/RESUME_STATE.json")
if not p.exists(): raise SystemExit(1)
try: s=json.loads(p.read_text())
except Exception: raise SystemExit(1)
g=s.get("gates",{}).get(name,{})
raise SystemExit(0 if g.get("status")=="PASS" else 1)
PY
}

echo "[gate] environment"
"$PYTHON" scripts/detect_environment.py --require colab-a100-40gb
mark environment PASS "A100 >=40GB verified"

echo "[gate] static"
if ! gate_passed static; then
  "$PYTHON" -m compileall -q services scripts tests
  mark static PASS "compileall passed"
else
  echo "resume: static already PASS"
fi

echo "[gate] bootstrap"
if ! gate_passed bootstrap; then
  bash scripts/colab_bootstrap.sh
  mark bootstrap PASS "bootstrap completed"
else
  echo "resume: bootstrap already PASS"
fi

CONTROL_PY=".venv-control/bin/python"
[[ -x "$CONTROL_PY" ]] || { mark bootstrap FAIL "missing control python"; exit 1; }

echo "[gate] model cache"
if ! gate_passed model_cache; then
  "$CONTROL_PY" scripts/prepare_model_cache.py
  mark model_cache PASS "model snapshot available in runtime HF cache"
else
  echo "resume: model cache already PASS"
fi

echo "[gate] preflight"
"$CONTROL_PY" scripts/preflight.py
mark preflight PASS "preflight passed"

echo "[gate] start"
bash scripts/start.sh
mark start PASS "stack start returned success"

echo "[gate] baseline acceptance"
set +e
"$CONTROL_PY" scripts/live_acceptance.py --restart --baseline
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
  mark baseline FAIL "live_acceptance exit=$rc"
  echo "Baseline failed; matrix skipped."
  exit "$rc"
fi
mark baseline PASS "baseline live acceptance passed"

echo "[gate] matrix"
set +e
"$CONTROL_PY" scripts/live_acceptance.py --restart --matrix
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
  mark matrix FAIL "matrix exit=$rc"
  exit "$rc"
fi
mark matrix PASS "A100 matrix passed"
echo "AUTOBUILD COMPLETE"
