# Architecture

Current release level: REVISE. Live integration remains unverified.

```text
Open WebUI -> authenticated Gateway -> native vLLM (A100)
                                  -> bounded Agent -> authenticated Sandbox Broker
                                                       -> disposable networkless runtime
                                  -> Research API -> Redis Streams -> Worker
Worker -> pinned-IP public HTTP fetch -> static Crawl4AI extractor
       -> canonical URLs/content hashes/chunks
       -> BGE-M3 dense+sparse -> named Qdrant vectors -> RRF -> BGE reranker
       -> context compiler -> synthesis -> citation validation
```

Canonical addresses: scripts/runtime_config.py. Native mode uses loopback or explicit external endpoints; Docker mode uses service DNS. Auxiliary deployment is local Docker or an explicitly provisioned private control host.

State owner: Redis stream delivery plus hash owner token. RUNNING completion/ack is a single fenced Lua transaction. Heartbeats renew pending delivery ownership. Cancellation/lease transfer blocks stale writes. Qdrant metadata includes job_id, attempt_id, document_id, chunk_id, canonical_url, title, content_hash, chunk_index. Retrieval filters both job and attempt, so a late indexing request cannot contaminate the winning attempt.

Persistent Redis AOF and Qdrant/UI volumes live on the auxiliary host. New hybrid collection suffix is _hybrid_v1; previous dense-only collections are not silently reused or deleted.

The context compiler measures the complete prompt, bounds sources/chunks, reserves completion tokens and reports its estimator. Retrieved JSON is evidence data under a separate system policy. Citation IDs resolve to actual selected chunks; invalid IDs fail synthesis.

Broker alone owns Docker access. Generated code receives no host mounts, broker keys or network. Each container has independent limits/lifetime; parent/descendant cleanup remains an actual Docker acceptance gate.

Development plane: Codex edits/tests/packages. Runtime plane: repository services run independently with no Codex dependency.
