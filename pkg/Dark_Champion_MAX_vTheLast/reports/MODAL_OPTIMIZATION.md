# Modal cost, token and throughput optimization

Certified source hash: `0262b4ace65ffdf33f88a18db80c9c780e2b0b97f18454212052a3b73bd2b0a5`. Target: Modal Linux / NVIDIA A100 80 GB.

## Configuration

- GPU serving scales to zero (`min_containers=0`) and allows at most one GPU container. The 10-second `scaledown_window` lowers idle-GPU cost at the price of cold starts. Modal's cold-start guide documents this trade-off: [Cold start performance](https://modal.com/docs/guide/cold-start) and [scale](https://modal.com/docs/guide/scale).
- Modal research defaults use one round, three queries, three results per query, at most nine candidates, and generation ceilings of 300 query-planning + 300 gap-analysis + 2,000 synthesis tokens. The configured ceiling is 2,600 versus 4,900 previously (46.9% lower maximum). This is a cap calculation; actual token savings and research-quality comparison were not measured.
- Keep `VLLM_MAX_NUM_BATCHED_TOKENS=8192`, 32K context, two sequences, 0.92 GPU-memory utilization, prefix caching, chunked prefill, and persistent model-weight/cache Volume. Model-weight storage in Volumes follows [Modal model-weight guidance](https://modal.com/docs/guide/model-weights). The [Modal throughput example](https://modal.com/docs/examples/vllm_throughput) informed the tested matrix.
- `HF_HUB_ENABLE_HF_TRANSFER` remains disabled because the repository records a live missing-package failure. No unbenchmarked transfer/cache flag was enabled.

## Measured live A100 matrix

All three runs used the same current source hash, A100 80 GB, 32K context, two sequences, and eight concurrent benchmark requests. No failures or observed OOM log events; baseline restore exit code 0.

| Batched tokens | Aggregate throughput | Mean / p95 request latency | Stream TTFT | Stream decode | Startup | VRAM used |
|---:|---:|---:|---:|---:|---:|---:|
| 8,192 | 93.21 tok/s | 6.34 / 10.04 s | 0.115 s | 49.76 tok/s | 94.3 s | 74,223 MiB |
| 16,384 | 93.62 tok/s | 6.26 / 10.00 s | 0.109 s | 49.50 tok/s | 160.3 s | 73,311 MiB |
| 32,768 | 94.32 tok/s | 6.21 / 9.92 s | 0.111 s | 49.57 tok/s | 158.3 s | 71,555 MiB |

32,768 raised aggregate throughput by only 1.19% over 8,192, while adding about 64 seconds of startup. 8,192 remains the cost/interactive default; the observed throughput delta did not justify the slower cold start. The 32K context gate independently passed. Full raw measurements are in `reports/A100_MATRIX.json` and `reports/A100_BENCHMARK.md`.

## Live certification

- 34/34 mandatory live acceptance gates PASS on the certified hash, including real tool call, sandbox isolation, Redis crash recovery, dense+sparse hybrid retrieval, reranking, citations, injection resistance, concurrency, 8K/16K/32K context, restart, and matrix.
- Public deployment smoke passed models, authentication, and real completion (3/3).
- Local regression: 94 full tests PASS; 23 focused config/worker/jobs regression tests PASS.
- Actual token savings are **not measured**. The 46.9% figure is only the reduction in configured maximum generation tokens.

Official Modal documentation checked 2026-10-08: [cold start](https://modal.com/docs/guide/cold-start), [scale](https://modal.com/docs/guide/scale), [model weights](https://modal.com/docs/guide/model-weights), [throughput example](https://modal.com/docs/examples/vllm_throughput).
