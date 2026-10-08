#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export TOKENIZERS_PARALLELISM=true
cd "$(dirname "$0")/.."
export COLAB_MODE=true
# Standard Colab can use a private external control host for isolated auxiliaries.
python scripts/runtime_config.py
auxiliary_mode="$(python -c 'import sys; sys.path.insert(0,"scripts"); from runtime_config import environment; print(environment().get("AUXILIARY_MODE","docker"))')"
export AUXILIARY_MODE="$auxiliary_mode"
if [[ "$auxiliary_mode" == "docker" ]]; then docker info >/dev/null; fi

echo "[1/7] GPU"
nvidia-smi

echo "[2/7] System packages"
apt-get -qq update
apt-get -qq install -y --no-install-recommends git curl jq build-essential python3-dev

echo "[3/7] uv + vLLM"
python -m pip install -q uv==0.12.23
[[ -d .venv-vllm ]] || uv venv .venv-vllm --python 3.12
.venv-vllm/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Existing inference environment requires Python 3.12"'
uv pip install --python .venv-vllm/bin/python -r requirements-inference.lock

echo "[4/7] Project Python dependencies"
[[ -d .venv-control ]] || uv venv .venv-control --python 3.12
.venv-control/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Existing control environment requires Python 3.12"'
uv pip install --python .venv-control/bin/python --torch-backend=cpu --require-hashes -r requirements-control.lock

echo "[5/7] Isolated auxiliary services are built at startup; no host browser installation"

echo "[6/7] Secrets/config"
.venv-control/bin/python scripts/bootstrap_env.py

echo "[7/7] Static preflight"
.venv-control/bin/python scripts/preflight.py
echo "Bootstrap complete."
