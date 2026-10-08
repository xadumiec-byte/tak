#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv-control/bin/python scripts/service_manager.py stop
