# Review guide

Read reports/WORK_STATE.json, NEXT_ACTIONS.md and FINAL_AUDIT.md. The prior release candidate audit is retained in BASELINE_AUDIT.md.

Current code includes Redis Streams, named dense/sparse Qdrant RRF, CPU embeddings/reranker, token budgeting, citation mapping and a disposable sandbox broker. Do not use older review notes describing these as absent.

Review boundaries: native vs Docker/external addresses; broker's privileged Docker socket; no host code execution; fetcher DNS/TLS/redirect pinning; static extractor network policy; atomic queue ownership/ack/cancellation; attempt-scoped indexing/retrieval; context and citation failure behavior.

Local fixtures/emulators do not establish Linux/container containment, GPU compatibility, checkpoint generation quality, browser UI streaming or restart durability. Use scripts/live_acceptance.py --restart --matrix in the target environment and review every status. READY requires all gates and evidence tied to the current source hash.
