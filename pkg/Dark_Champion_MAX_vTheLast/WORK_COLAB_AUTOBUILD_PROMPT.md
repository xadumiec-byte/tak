# DARK CHAMPION MAX vTheLast — AUTONOMOUS COLAB BUILD

Continue the current repository. Current state is REVISE — A100 LIVE VALIDATION REQUIRED.
Target: Google Colab / Linux / NVIDIA A100 40GB. Goal: READY only after real live gates pass.

Start immediately:
```bash
python scripts/detect_environment.py --require colab-a100-40gb
```
Exit 2 is an environment blocker, not a product defect. If it is not COLAB_A100, stop before heavy installs/model downloads and persist the blocker.

If it passes, execute:
```bash
bash scripts/colab_autobuild.sh
```

Rules:
- Read reports/WORK_STATE.json, reports/NEXT_ACTIONS.md, reports/FINAL_AUDIT.md, reports/VERSION_MATRIX.md and INSTALL_COLAB.md first when present.
- Repository reports are persistent memory. Do not repeat completed audits or PASS work unless affected source changed.
- Use local files/commands/tests/logs first; official web/plugin sources only for unresolved current compatibility/API/version facts. Persist verified findings locally and do not research them twice.
- Work gate-by-gate: environment -> cheap static checks -> bootstrap -> preflight -> auxiliary services -> vLLM -> tiny completion/SSE -> baseline live acceptance -> integrations -> matrix -> final.
- Never run the expensive matrix before baseline acceptance passes.
- Fix one reproducible failure at a time: reproduce -> root cause -> regression test -> minimal patch -> focused test -> affected regression -> rerun failed live gate.
- After three failed attempts on one root cause, stop speculative patching; reduce to a minimal reproduction and verify upstream behavior if needed.
- Preserve sandbox isolation, SSRF protection, authentication and private-service boundaries.
- Never fabricate GPU/model/latency/TTFT/throughput/VRAM/OOM/compatibility results.
- Keep progress compact: GATE / STATUS / PATCH / TEST / NEXT.
- Persist checkpoints after important gates in WORK_STATE.json, NEXT_ACTIONS.md, LIVE_ACCEPTANCE.json/.md and A100_BENCHMARK.md.
- Continue autonomously through reversible, testable local actions. Stop only for credentials/payment/irreversible external actions/wrong hardware/genuine external blocker.
- READY requires every mandatory live gate PASS against the current source hash. Only READY permits Dark_Champion_MAX_vTheLast_FINAL.zip.

Do not explain the plan. Detect the environment and execute the cheapest unresolved gate now.


## FAST CACHE / AUTO-RESUME
Before build, source `scripts/cache_env.sh`. Treat `reports/RESUME_STATE.json` as the compact restart checkpoint.
After a Colab disconnect, rerun `bash scripts/colab_autobuild.sh`; do not restart the historical audit.
Use cached downloads/environments when valid, but revalidate runtime-dependent gates.
Never store secrets in the cache.
`COLAB_ONE_CELL.py` is the canonical single-cell launcher reference.

## Active profile: A100 40GB

DARK_GPU_PROFILE=a100-40gb; model Qwen/Qwen2.5-Coder-14B-Instruct at revision aedcc2d42b622764e023cf882b6652e646b95671; configured context 16384, batch 8192, sequences 2, GPU utilization 0.92. Keep embeddings and reranking on CPU. The detector requires measured A100 memory >=37500 MiB for the 40GB target; the original 80GB requirement is still strict.

Baseline uses `scripts/live_acceptance.py --restart --baseline`; success does not promote READY. Matrix runs only after all baseline gates actually pass. 32K is not certified by the initial 16K profile. Standard Colab still needs private external isolated auxiliary services.
