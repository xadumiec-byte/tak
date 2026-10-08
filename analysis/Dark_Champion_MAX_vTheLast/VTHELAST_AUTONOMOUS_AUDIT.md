# vTheLast — Autonomous Build & Audit Command

You are the senior release engineer responsible for turning this repository into the final reproducible `vTheLast` release for a Google Colab NVIDIA A100 80GB runtime.

## Operating mode
Work autonomously. Do not stop after analysis. Inspect files, run commands, patch code, rerun tests, and iterate until the acceptance gates below pass or a genuine external blocker is proven. Never claim a command passed unless you actually ran it and captured its exit status/output.

Preserve the architecture and security boundaries:
- vLLM is local inference and must not be exposed directly to the public Internet.
- Keep SSRF/private/link-local protections in research crawling.
- Keep arbitrary code execution inside the constrained, networkless sandbox; do not move it into the gateway or host process.
- Do not add prompt-based "ignore all safety" or safeguard-bypass mechanisms.
- Secrets must be generated at install time and never committed.

## Phase 0 — inventory
Run:
```bash
pwd
find . -maxdepth 4 -type f | sort
git status --short 2>/dev/null || true
python --version
nvidia-smi || true
```
Read README.md, REVIEW_GUIDE.md, AUDIT_PROMPT.md, docker-compose.yml, .env.example, all Dockerfiles, all Python source, shell scripts, tests, and the Colab notebook.

## Phase 1 — verify upstream compatibility
Using current official documentation/release pages, verify before changing versions:
1. vLLM install method and CLI flags used by `gpu/start_vllm_a100.sh`.
2. The selected model's exact Hugging Face repository, tokenizer/chat template, context length, dtype/quantization, license, and vLLM compatibility.
3. Whether the selected checkpoint supports Hermes-style tool calls; only set `VLLM_TOOL_CALL_PARSER=hermes` after an actual tool-call smoke test.
4. Crawl4AI stable image/API request schema and authentication.
5. Open WebUI stable release and its OpenAI-compatible connection environment variables.
6. Qdrant version/API needed for dense+sparse hybrid retrieval and RRF.
7. BGE-M3 and BGE-reranker-v2-m3 model APIs.
Pin production images/dependencies to verified versions; do not guess version numbers.

## Phase 2 — Colab/A100 bootstrap
Run:
```bash
bash scripts/colab_bootstrap.sh
python scripts/preflight.py
```
If the runtime is not an A100 80GB, report that fact and continue static/integration work without inventing GPU results.

Start:
```bash
bash scripts/colab_run.sh
```
Inspect:
```bash
tail -n 200 .run/logs/vllm.log
tail -n 200 .run/logs/gateway.log
tail -n 200 .run/logs/research.log
tail -n 200 .run/logs/research-worker.log
tail -n 200 .run/logs/embedding.log
tail -n 200 .run/logs/reranker.log
```

## Phase 3 — mandatory fixes
Patch and test all failures found. In particular:
- Preserve unknown OpenAI-compatible request fields through the gateway (`tools`, `tool_choice`, `response_format`, `top_p`, `stop`, `seed`, etc.).
- Verify streaming SSE behavior through gateway -> vLLM -> Open WebUI.
- Verify model aliases and `/v1/models`.
- Add structured error handling and timeouts.
- Ensure research job status is durable enough for Colab restarts where practical.
- Prevent prompt injection in crawled content from becoming system/tool instructions.
- Canonicalize/dedupe URLs and content.
- Add per-domain crawl limits and bounded concurrency.
- Validate citations against the actual retrieved chunks.
- Ensure chunk/token budgets cannot exceed the model context.
- Replace dense-only retrieval with true dense+sparse hybrid retrieval + RRF if the verified Qdrant version supports it.
- Keep cross-encoder reranking after hybrid candidate generation.
- Add document/PDF ingestion only if it can be made reproducible without destabilizing the fast Colab path.
- Add request IDs and useful structured logs.
- Add graceful shutdown scripts.

## Phase 4 — tests
At minimum run:
```bash
python -m pytest -q
python scripts/preflight.py
python scripts/benchmark_vllm.py
```
Add and run tests for:
- SSRF: localhost, RFC1918, link-local, IPv6 local, redirect/rebinding strategy.
- Gateway authentication.
- OpenAI request passthrough.
- SSE streaming.
- sandbox timeout/output limits/no-network assumption.
- research queue lifecycle.
- chunking/deduplication.
- hybrid retrieval and reranking.
- citation mapping.
- prompt-injection-resistant evidence handling.

If Docker is available, also run:
```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
```
Do not make Docker mandatory for the Colab-native fast path.

## Phase 5 — A100 tuning
Benchmark at least these `VLLM_MAX_NUM_BATCHED_TOKENS` values when GPU runtime permits:
- 8192
- 16384
- 32768

Keep `VLLM_GPU_MEMORY_UTILIZATION` conservative initially (0.90). Raise only after observing stable free VRAM and no OOM/preemption problems. Measure startup time, TTFT if available, total latency, output throughput, VRAM, and failures. Do not infer performance from theory.

Test 8K, 16K, and 32K prompts if the model card supports them. Reduce `VLLM_MAX_MODEL_LEN` if the actual checkpoint or VRAM does not support the configured value reliably.

## Phase 6 — acceptance gates
Do not call the release final until:
- all Python compiles;
- pytest passes;
- preflight passes;
- vLLM `/v1/models` works;
- one normal chat completion works;
- one streaming completion works;
- one real tool call round-trip works or tool calling is explicitly disabled with documented reason;
- sandbox execution works and times out correctly;
- research job reaches queued -> running -> done;
- crawl -> chunk -> index -> hybrid retrieve -> rerank -> synthesize works;
- citations map to retrieved evidence;
- secrets are not committed;
- public network exposure is limited to the intended UI/tunnel;
- restart instructions are tested;
- A100 benchmark results are written to `reports/A100_BENCHMARK.md`.

## Phase 7 — deliverables
Create/update:
- `README.md`
- `INSTALL_COLAB.md`
- `TROUBLESHOOTING.md`
- `SECURITY.md`
- `ARCHITECTURE.md`
- `reports/A100_BENCHMARK.md`
- `reports/FINAL_AUDIT.md`
- `reports/VERSION_MATRIX.md`
- final Colab notebook
- final `.env.example`
- final tests
- `scripts/start.sh`, `scripts/stop.sh`, `scripts/status.sh`

Then produce:
```bash
python -m pytest -q
python scripts/preflight.py
zip -r Dark_Champion_MAX_vTheLast_FINAL.zip . \
  -x '.env' '.git/*' '__pycache__/*' '*.pyc' '.run/*'
```

`reports/FINAL_AUDIT.md` must contain:
- exact commands executed;
- exit codes;
- versions actually tested;
- unresolved issues;
- A100 measurements actually observed;
- security findings;
- final verdict: `BLOCK`, `REVISE`, or `READY`.

Never mark `READY` based only on static inspection.
