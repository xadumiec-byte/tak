#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname "$0")/start_vllm_a100.sh" "$@"
