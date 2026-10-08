#!/usr/bin/env bash
set -euo pipefail

# Fast runtime cache stays on Colab local disk.
RUNTIME_ROOT="${DARK_RUNTIME_CACHE_ROOT:-/content/.cache/dark-champion}"
mkdir -p "$RUNTIME_ROOT"/{hf,torch,xdg}

export HF_HOME="${HF_HOME:-$RUNTIME_ROOT/hf}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"
export TORCH_HOME="${TORCH_HOME:-$RUNTIME_ROOT/torch}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$RUNTIME_ROOT/xdg}"

# Package-manager caches may be persisted on Drive without putting model
# random-access reads on the slower mounted filesystem.
if [[ -n "${DARK_PERSIST_CACHE_ROOT:-}" ]]; then
  PERSIST="$DARK_PERSIST_CACHE_ROOT"
  mkdir -p "$PERSIST"/{uv,pip,wheels}
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$PERSIST/uv}"
  export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$PERSIST/pip}"
  export DARK_WHEEL_CACHE="${DARK_WHEEL_CACHE:-$PERSIST/wheels}"
else
  mkdir -p "$RUNTIME_ROOT"/{uv,pip,wheels}
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$RUNTIME_ROOT/uv}"
  export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$RUNTIME_ROOT/pip}"
  export DARK_WHEEL_CACHE="${DARK_WHEEL_CACHE:-$RUNTIME_ROOT/wheels}"
fi

export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-true}"

echo "runtime cache: $RUNTIME_ROOT"
echo "HF_HOME: $HF_HOME"
echo "UV_CACHE_DIR: $UV_CACHE_DIR"
echo "PIP_CACHE_DIR: $PIP_CACHE_DIR"
