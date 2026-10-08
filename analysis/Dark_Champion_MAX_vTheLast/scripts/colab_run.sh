#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export COLAB_MODE=true
exec .venv-control/bin/python scripts/service_manager.py start
