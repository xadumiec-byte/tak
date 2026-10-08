# Active 40GB profile audit

Verdict: REVISE. User explicitly changed the target to the measured A100 40GB capacity.

The FASTCACHE archive lacked live_acceptance.py and its old bootstrap did not create the environment its autobuild required. Already tested canonical source, isolation, dependency locks and tests were restored from the prior workspace rather than redesigned. Cache/resume entry points remain.

Pinned official Qwen2.5-Coder-14B-Instruct BF16 replaces the oversized default. Initial context 16K, batched tokens 8192, two sequences, utilization 0.92. 47 local tests and compilation pass; no inference capacity or throughput is certified. GPU detection, auxiliary services, actual inference and every full live gate remain required. The 32K gate remains pending; no READY by skipping unsupported work.

Model metadata and sources: PROFILE_40GB_MODEL.json / VERSION_MATRIX.md. Full matrix is gated behind baseline acceptance. Sandbox, SSRF and auth isolation retained.

## Transfer checkpoint

Browser transfer blocked: file chooser requires Allow access to file URLs. User authorized the setting, but browser security policy rejects brave://extensions/ (only HTTP/HTTPS allowed). Manual setting change required. Colab editor transfer timed out; no confirmed autobuild or model execution.

47 local tests PASS. User explicitly authorized Allow access to file URLs; automatic browser security review rejects the internal Brave settings URL. No permission workaround attempted. Package ready for transfer; no READY or FINAL claim.

## Browser recovery checkpoint

Brave extension reconnected (browser 4). Colab tab 64786694 timed out during binding and recovery reload. File-upload permission cannot be verified while Colab is unresponsive. No autobuild/model execution confirmed. Stop repeating failed UI operations; user-side reload/reopen required.
