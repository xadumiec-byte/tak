# Colab / A100 installation

Status: REVISE. Commands and topology are implemented; this environment cannot validate native Linux startup or the A100 stack.

## Standard Colab without Docker

Provision a private Linux control host with Docker Engine/Compose. On that host, extract this repository, generate secrets with `python scripts/bootstrap_env.py`, install `httpx==0.28.1` and `PyYAML==6.0.3`, then run:

```bash
python scripts/service_manager.py aux-up
```

The helper builds the disposable sandbox runtime and starts isolated auxiliaries. Open WebUI binds loopback. Its gateway connection is `UI_GATEWAY_URL`, defaulting to http://127.0.0.1:8088/v1; establish a private route/forward to the Colab gateway there. Expose only the authenticated UI through your TLS/private access layer.

In Colab, select an actual A100 80GB, extract the repository under /content/Dark_Champion_MAX_vTheLast, and create .env from .env.example. Set COLAB_MODE=true and AUXILIARY_MODE=external. Supply all required REDIS_EXTERNAL_URL, QDRANT_EXTERNAL_URL, SEARXNG_EXTERNAL_URL, CRAWL4AI_EXTERNAL_URL, SANDBOX_EXTERNAL_URL and OPEN_WEBUI_EXTERNAL_URL values. Public endpoints require TLS; use private routing or loopback SSH forwards for internal services. The external broker/crawler and UI must use the matching generated SANDBOX_API_KEY, CRAWL4AI_API_TOKEN and DARK_API_KEY. Keep credentials outside the archive.

Run:

```bash
bash scripts/colab_bootstrap.sh
bash scripts/start.sh
.venv-control/bin/python scripts/live_acceptance.py --restart --matrix
```

Missing auxiliary configuration fails early. No host fallback executes generated code.

## Colab/Linux with a working Docker engine

Set COLAB_MODE=true and AUXILIARY_MODE=docker. The same commands build/start local auxiliaries and native CPU/GPU processes. Merely having a Docker CLI is insufficient: the engine/kernel must support constrained networkless containers. Standard Colab does not guarantee this.

## Dependency ownership

.venv-vllm installs requirements-inference.lock. .venv-control installs hashed requirements-control.lock with the CPU PyTorch backend. This avoids the verified incompatibility between vLLM 0.31.0's newer FastAPI/Pydantic requirements and the control plane pins. Model revisions and container manifest digests are fixed. Bootstrap reuses existing environments and caches. No browser runtime is installed on the Colab host.

## Operations

```bash
bash scripts/status.sh
bash scripts/stop.sh
```

Logs: .run/logs. Runtime PID identities and auxiliary plan: .run. Redis/Qdrant/UI use Docker volumes on the control host. Keep that host persistent to recover queued/claimed jobs across Colab termination.

## Inference and parser gate

Defaults: 32768 context, 0.90 GPU memory utilization, 32 sequences, 16384 batched tokens, prefix caching and chunked prefill. These are initial settings, not measured optima.

Pinned model config advertises 262144 positions; tokenizer metadata advertises 1048576. The conservative configured/verified model limit governs the context compiler. Changing checkpoints requires updating revision and verified context limit from that checkpoint's own configuration.

The parser is disabled by default. Verify the exact pinned checkpoint's automatic tool format on the actual vLLM runtime before enabling it. Live acceptance reports BLOCKED for the automatic agent gate until this is done. Real named-tool round trips are separate tests.

Only an all-PASS live report, actual benchmark matrix and restart evidence may permit READY/FINAL. A100_READY is not claimed by the current local audit.

## Active profile: A100 40GB

DARK_GPU_PROFILE=a100-40gb; model Qwen/Qwen2.5-Coder-14B-Instruct at revision aedcc2d42b622764e023cf882b6652e646b95671; configured context 16384, batch 8192, sequences 2, GPU utilization 0.92. Keep embeddings and reranking on CPU. The detector requires measured A100 memory >=37500 MiB for the 40GB target; the original 80GB requirement is still strict.

Baseline uses `scripts/live_acceptance.py --restart --baseline`; success does not promote READY. Matrix runs only after all baseline gates actually pass. 32K is not certified by the initial 16K profile. Standard Colab still needs private external isolated auxiliary services.
