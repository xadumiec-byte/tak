#!/usr/bin/env bash
set -euo pipefail

# JIT helper executables (e.g. pip-installed ninja) belong to the inference venv.
EXECUTABLE="${VLLM_EXECUTABLE:-vllm}"
if [[ "$EXECUTABLE" == */* ]]; then
  export PATH="$(dirname -- "$EXECUTABLE"):$PATH"
fi

MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-Coder-14B-Instruct}"
API_KEY="${VLLM_API_KEY:?VLLM_API_KEY must be set}"
HOST="${VLLM_HOST:-127.0.0.1}"
PORT="${VLLM_PORT:-8000}"

# Initial A100-40GB profile; capacity and performance require live validation.
MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-16384}"
GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.92}"
MAX_NUM_BATCHED_TOKENS="${VLLM_MAX_NUM_BATCHED_TOKENS:-8192}"
MAX_NUM_SEQS="${VLLM_MAX_NUM_SEQS:-2}"

ARGS=(
  serve "$MODEL"
  --host "$HOST"
  --port "$PORT"
  --api-key "$API_KEY"
  --dtype auto
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --max-model-len "$MAX_MODEL_LEN"
  --max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS"
  --max-num-seqs "$MAX_NUM_SEQS"
  --enable-prefix-caching
  --enable-chunked-prefill
  --generation-config vllm
)
if [[ "${VLLM_MODEL_REVISION:-}" != "" ]]; then
  ARGS+=(--revision "$VLLM_MODEL_REVISION" --tokenizer-revision "$VLLM_MODEL_REVISION")
fi

# Parser configuration requires a real tool round trip on the pinned checkpoint.
if [[ "${VLLM_TOOL_CALL_PARSER:-}" != "" ]]; then
  ARGS+=(--enable-auto-tool-choice --tool-call-parser "$VLLM_TOOL_CALL_PARSER")
fi
if [[ "${VLLM_TRUST_REMOTE_CODE:-false}" == "true" ]]; then
  ARGS+=(--trust-remote-code)
fi

exec "$EXECUTABLE" "${ARGS[@]}"
