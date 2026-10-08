# Prompt for the reviewing AI

Review the entire Dark Champion MAX repository as a senior distributed-systems, LLM-inference, security, and research-agent engineer.

Do not praise the project. Try to break it.

Check:
- Docker Compose correctness.
- Open WebUI connectivity.
- vLLM OpenAI API compatibility.
- current model/runtime compatibility.
- Crawl4AI API schema.
- SearXNG JSON search configuration.
- SSRF, DNS rebinding, redirect, secret, and network-isolation risks.
- A100 80 GB VRAM feasibility.
- streaming and timeout behavior.
- research citation correctness and hallucination risks.
- prompt-injection risks from crawled web pages.
- dependency pinning and supply-chain risks.
- concurrency and resource exhaustion.
- persistence/restart behavior.
- observability.
- test coverage.
- whether every documented command can actually work.

Return findings ordered by severity. For every finding provide:
- affected file and line/function;
- failure scenario;
- exact recommended fix;
- patch/diff when possible.

End with one verdict only: BLOCK, REVISE, or READY FOR TEST.
