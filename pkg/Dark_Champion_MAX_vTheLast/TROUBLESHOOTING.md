# Troubleshooting

## Native bootstrap stops at auxiliary preflight
Standard Colab may have no usable Docker engine. Configure AUXILIARY_MODE=external with a private control host and all six external service addresses. Do not remove isolation or execute generated code on the host.

## Engine works but sandbox health fails
Build the runtime image first: docker compose build sandbox-runtime sandbox-broker. Broker health checks the Docker daemon and fixed runtime image. Inspect broker logs and permissions on the private Docker socket.

## Startup readiness fails
Inspect .run/logs and run scripts/status.sh. Readiness requires 2xx service responses, Redis connectivity and a live worker lease. Invalid credentials are not accepted as readiness. Failed startup cleans up managed processes.

## vLLM dependency conflicts
Use the separate .venv-vllm lockfile. Do not install control-plane FastAPI/Pydantic into that environment. CPU Torch belongs to .venv-control, GPU Torch to .venv-vllm.

## Context metadata disagrees
For the pinned Qwen checkpoint, model config is 262144 positions while tokenizer metadata says 1048576. Use the smaller verified model limit and configured runtime limit. Never infer context capacity from the tokenizer value alone.

## Agent returns 409 / automatic tool gate BLOCKED
The checkpoint parser has not been validated. Verify actual vLLM automatic tool calls before configuring VLLM_TOOL_CALL_PARSER. Forced named-tool calls do not prove automatic parsing.

## Research fails or evidence is empty
Check SearXNG JSON responses, static extraction health and pinned fetch logs. JS-only sites and rejected/oversized/compressed pages may be unavailable. Invalid citations fail the job explicitly. There is no silent fallback from failed crawls to search snippets.

## Worker stopped mid-job
Pending stream delivery is recovered after the 120-second lease. Owner fencing prevents stale completion; attempt-scoped retrieval prevents stale evidence. Three recovery attempts are permitted. Redis AOF/volumes must survive the runtime restart.

## GPU OOM / performance
Keep actual logs and A100 measurements. Reduce context/sequences/batched tokens as indicated by the observed failure, then rerun focused inference. Live acceptance --matrix measures 8192/16384/32768 and restores baseline. No GPU results are inferred locally.

## Acceptance exits 2
Inspect LIVE_ACCEPTANCE.json/md. BLOCKED or NOT TESTED means the gate has not passed. --offline intentionally exits nonzero. --restart --matrix enables the full managed runtime/matrix checks; a verified automatic parser is also required.
