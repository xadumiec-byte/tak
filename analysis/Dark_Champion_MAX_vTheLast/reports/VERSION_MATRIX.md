# Verified version matrix — 2026-10-06

Metadata and immutable revisions were verified once and cached in UPSTREAM_METADATA.json, IMAGE_MANIFESTS.json and TOKENIZER_METADATA.json. Metadata verification is not target runtime validation.

| Component | Canonical pin | Evidence / remaining gate |
|---|---|---|
| Target Python | 3.12; local tests 3.12.10 | local PASS; Linux install BLOCKED |
| vLLM | 0.31.0 | official PyPI/GitHub metadata; Linux inference lock resolves; A100 BLOCKED |
| Inference torch / transformers | 2.13.0 / 5.17.0 | requirements-inference.lock, target install BLOCKED |
| CPU torch / transformers / PEFT | 2.14.1+cpu / 4.57.6 / 0.21.2 | hashed control lock; actual CPU imports PASS |
| FlagEmbedding / sentence-transformers | 1.4.2 / 3.3.1 | actual dense+sparse and reranker CPU smoke PASS; CPU_MODEL_SMOKE.json records tested transitive versions |
| Control FastAPI / Pydantic / httpx | 0.115.6 / 2.10.4 / 0.28.1 | local 45-test regression PASS; separate from vLLM dependencies |
| Redis client / Qdrant client | 5.2.1 / 1.19.1 | Redis emulator and Qdrant in-memory integration PASS; server integration BLOCKED |
| Docker SDK / uv | 7.1.0 / 0.12.23 | local imports/resolution PASS; container execution BLOCKED |
| Crawl4AI / httpcore | 0.9.2 / 1.0.9 | actual static extraction and pinned-IP HTTPS fetch PASS |
| Open WebUI / Qdrant | 0.11.4 / 1.19.2 | digest-pinned manifests verified; container runtime BLOCKED |
| Redis / SearXNG / Python image | 7-alpine / latest / 3.12-slim | immutable digests in Compose/Dockerfiles; runtime BLOCKED |

## Model contracts

- Qwen/Qwen3-Coder-30B-A3B-Instruct revision b2cff646eb4bb1d68355c01b18ae02e7cf42d120: public, ungated, Apache-2.0; Qwen3MoeForCausalLM; 30,532,122,624 parameters, BF16 weights 61,066,575,656 bytes. Config context 262144, tokenizer metadata 1048576: use the conservative config bound, default 32768. Tool parser deliberately unset until real inference proves compatibility.
- BAAI/bge-m3 revision 5617a9f61b028005a4858fdac845db406aefb181: MIT, CPU FlagEmbedding dense 1024 + lexical sparse vectors.
- BAAI/bge-reranker-v2-m3 revision 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e: Apache-2.0, CPU CrossEncoder.
- Previous Dolphin URL returned HTTP 401 during metadata verification; availability/access was not established. This does not establish that the repository does not exist.

## Official sources

- https://docs.vllm.ai/en/stable/cli/serve/
- https://docs.astral.sh/uv/guides/integration/pytorch/
- https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct
- https://huggingface.co/BAAI/bge-m3
- https://huggingface.co/BAAI/bge-reranker-v2-m3
- https://docs.crawl4ai.com/core/self-hosting/
- https://qdrant.tech/documentation/search/hybrid-queries/
- https://api.qdrant.tech/api-reference/search/query-points/
- https://docs.openwebui.com/reference/env-configuration/

See lockfiles for transitive pins and cached JSON for exact registry digests. No measured GPU throughput, VRAM, OOM or parser claim is inferred from these sources.

## Active A100 40GB profile

Qwen/Qwen2.5-Coder-14B-Instruct, immutable revision aedcc2d42b622764e023cf882b6652e646b95671. Official HF API verified ungated BF16 14,770,033,664 parameters; safetensors total 29,540,133,960 bytes. Official config supports 32768 positions. Initial runtime: context 16384, batched tokens 8192, sequences 2, GPU memory utilization 0.92. This is a capacity plan, not measured inference performance. Real 32K remains a separate pending memory/context gate; no READY promotion by skipping it.

Sources: https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct and https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct/raw/main/config.json. Metadata: PROFILE_40GB_MODEL.json. The former 30B BF16 default is no longer the active profile.
