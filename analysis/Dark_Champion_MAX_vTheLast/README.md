# Dark Champion MAX — vTheLast

Release level: **REVISE**. Source changes and local evidence are recorded in `reports/WORK_STATE.json` and `reports/FINAL_AUDIT.md`. Full Linux/Docker and A100 validation remain required. This archive is not a FINAL release.

## Runtime

One A100 80GB serves the pinned Qwen/Qwen3-Coder-30B-A3B-Instruct checkpoint through vLLM. Gateway, research worker, BGE-M3 and reranker use the CPU. Native inference and CPU dependencies have separate environments and lockfiles.

The previous RC checkpoint returned HTTP 401 from the public Hub API. Its access/compatibility could not be established. The replacement is public and ungated; exact revision, configuration, license and checkpoint byte size are recorded in `reports/UPSTREAM_METADATA.json`.

Open WebUI connects to the authenticated gateway. Model aliases remain dark-general, dark-code, dark-reason, dark-max and dark-research. Gateway requests preserve compatible extension fields; ordinary and research streams use SSE.

## Deployment

Read `INSTALL_COLAB.md`. `COLAB_MODE=true` generates native loopback addresses through `scripts/runtime_config.py`. Two auxiliary modes are supported:

- `AUXILIARY_MODE=docker`: a working Linux Docker engine runs Redis, Qdrant, SearXNG, static Crawl4AI extraction, Open WebUI and the sandbox broker.
- `AUXILIARY_MODE=external`: standard Colab uses explicitly configured private auxiliary endpoints. Docker is required on the external sandbox/control host, not in Colab.

Start/stop/status use `scripts/start.sh`, `scripts/stop.sh`, `scripts/status.sh`. PID records include process identity to prevent stale PID reuse. Startup health-polls every required service and the worker lease.

## Research

Redis Streams persist QUEUED -> CLAIMED -> RUNNING -> DONE/FAILED/CANCELLED. Completion is acknowledged atomically and fenced by an owner token. Stale deliveries are reclaimed; recovery attempts are limited to three. API cancellation prevents late completion.

Fetching resolves and validates all addresses at connection time, connects to the checked numeric IP, preserves the TLS hostname and repeats validation for redirects. Responses, concurrency, domains and total requests are bounded. Failed URLs are not recrawled within a job and failed fetches are not promoted to evidence.

Crawl4AI performs static HTML cleanup/markdown extraction on an internal network. There is no browser or JavaScript execution. JavaScript-only sites may produce insufficient evidence and fail the job explicitly.

BGE-M3 returns dense and sparse vectors. Qdrant stores named vectors, fuses both retrieval legs with RRF, then a CPU cross-encoder reranks candidates. Logical job and worker attempt filters prevent cross-job and stale-attempt evidence leakage. Old dense-only collections are retained but are no longer used; the canonical new collection suffix is `_hybrid_v1`.

The context compiler separates system policy, user question and JSON-encoded untrusted evidence. It reserves generation tokens, uses a cached real tokenizer when available, otherwise a conservative UTF-8 byte bound. Every returned citation maps to a retrieved chunk and URL. Missing/invalid citations fail the job.

## Tools and sandbox

Gateway -> authenticated broker -> disposable container. Generated Python never runs in gateway, research worker or Colab host. Each execution has no network, read-only root, tmpfs, non-root UID, dropped capabilities, PID/memory/CPU limits and bounded output. Broker owns container cleanup, including timeout/cancellation paths.

Automatic agent calling remains disabled unless `VLLM_TOOL_CALL_PARSER` is explicitly configured after a real checkpoint smoke test. Agent responses include tool traces and enforce step/context budgets. Parser/automatic round-trip is an explicit live acceptance gate.

## Tests and handoff

```bash
python -m pytest -q
python scripts/live_acceptance.py --restart --matrix
```

Run live acceptance with the native control environment after services start. It writes LIVE_ACCEPTANCE.json/md and actual benchmark artifacts. `--offline` tests report generation without probing unavailable infrastructure and exits nonzero. NOT TESTED/BLOCKED never become PASS.

`python scripts/package_release.py` produces an intermediate package from WORK_STATE. FINAL requires READY live evidence matching the current source hash. Runtime secrets, caches, virtual environments, execution files and model weights are excluded.

## Continuation

Read only WORK_STATE.json, NEXT_ACTIONS.md and FINAL_AUDIT.md, then relevant source. Historical baseline: BASELINE_AUDIT.md. Codex is a development tool; the product has no Codex runtime dependency.
