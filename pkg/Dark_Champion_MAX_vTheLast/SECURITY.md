# Security boundaries

Release level: REVISE. Local tests establish contracts; full containment and live model behavior remain explicit acceptance gates.

- vLLM and native internal services bind loopback. Only the intended authenticated UI may be exposed through a private/TLS access layer.
- Gateway bearer key and broker bearer key are independent, generated at bootstrap. Crawler has its own token. Existing operator secrets are preserved. No .env is packaged.
- Generated code runs only in a fresh non-root, networkless container with read-only root, 64MB tmpfs, 512MB memory, one CPU, 64 PIDs, dropped capabilities and no-new-privileges.
- The trusted broker has Docker socket access and therefore must remain private, authenticated and separately audited. Clients cannot select images, mounts, commands or isolation parameters. It is not a low-privilege service merely because the execution container is constrained.
- Runtime pipe capture is bounded; timeout/output overflow kills the process group. Broker forcibly removes the container, also on cancellation. Real network/PID/memory/filesystem/descendant enforcement is still BLOCKED until Docker testing.
- Public crawling validates DNS at the socket connection, pins the checked IP and checks redirects individually. All returned DNS addresses must be global. Credentials, private/link-local addresses, arbitrary ports, compressed responses and oversized bodies are rejected.
- Crawl4AI only extracts sanitized static HTML on an internal network; scripts, frames, forms and media are removed. Browser/JavaScript fetching is not enabled.
- Search/crawl concurrency, request/domain budgets, worker recovery attempts, evidence size and context are bounded. Failed fetches never become evidence.
- Retrieved text remains untrusted JSON evidence. Behavioral prompt-injection resistance requires the actual model gate; structural separation alone is not reported as model immunity.
- Job/attempt filters and owner fencing prevent cross-job/stale-worker data leakage. Citation existence is verified; existence does not by itself prove every factual claim is supported.
- Container digests/model revisions are pinned from official metadata. GPU compatibility and complete transitive installation must still be tested in the target runtime.
