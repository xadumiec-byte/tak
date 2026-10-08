# Modal migration — REVISE, live validation required

The `modal_app.py` deployment runs vLLM, the gateway, research API/worker,
CPU embeddings and CPU reranking on Modal. It reuses canonical runtime code
and both pinned dependency environments. The initial GPU remains A100 40GB
with Qwen2.5-Coder-14B and the existing 16K profile; 32K is not certified.

The bounded validation command now provisions the auxiliary stack in a Modal
CPU VM with Docker (`runtime="vm"`). Generated code remains in disposable,
non-root, read-only, networkless Docker containers. No auxiliary HTTP or Redis
ports are public: the GPU reaches them through authenticated SSH with the host
key obtained from trusted Modal exec. The static crawler remains on its internal
extraction network; SSH routes to its Docker-inspected private address.

GPU Sandboxes use gVisor; Docker runs only in the CPU VM. The GPU and control
VM are stopped at session end. Model weights and sanitized acceptance reports
persist in Modal Volumes. Local `.env`, SSH keys, virtualenvs and archives are
excluded from source upload. Only the required runtime keys enter scoped Modal
Secrets; their values must never enter reports.

## Current verified state

GPU account access is resolved. A real bounded probe measured A100-SXM4-40GB,
40960 MiB, driver 580.95.05. The dashboard now shows $30 in free credits.
No payment or purchase was performed by this build. Retain free-credit-only
operation and check remaining credit before each bounded cloud session.

Real CPU services and isolated Docker execution passed component checks.
The first vLLM start failed because FlashInfer could not find nvcc/CUDA_HOME.
The adapter now uses an official digest-pinned CUDA 13.0.2 devel image, with
Python 3.12 and the unchanged separate dependency locks. Optional hf_transfer
is disabled because the CPU lock does not include it. The model cache was
committed before releasing the failed GPU session.

## Deployment after account and service prerequisites

Install `requirements-modal.txt` in a separate `.venv-modal` environment. Authenticate
the CLI through `python -m modal setup`; creation of the API credential requires
the user's action-time authorization. Never paste credentials in chat or reports.

Run `scripts/bootstrap_env.py` locally if runtime keys are absent. The validation
entrypoint reads only the six required keys from the excluded `.env`, generates
an excluded SSH keypair under `.run`, and injects scoped ephemeral Modal Secrets.
It creates the VM, obtains its host identity through authenticated Modal exec,
and validates on the actual GPU. It cleans up the VM in a finally block.

Run the validation deployment first:

```powershell
.venv-modal\Scripts\python.exe -m modal run modal_app.py
```

The canonical baseline runs inside real Modal GPU hardware. Matrix is opt-in and
is run only after baseline succeeds:

```powershell
.venv-modal\Scripts\python.exe -m modal run modal_app.py --matrix
```

Serving deployment is a separate unfinished lifecycle gate. The current bounded
validation session does not certify a persistent production endpoint. Do not
publish serving until its control-VM routing and lifecycle are validated:


```powershell
.venv-modal\Scripts\python.exe -m modal deploy modal_app.py
```

Do not invoke serving while a validation container is active: each function has
its own one-container limit, not an app-wide shared limit. Deployment does not
certify readiness and it does not enforce a dollar spending cap. Verify remaining
free credits and restrict execution before every cloud run; stop when exhausted.
Web serving can generate continuing charges from requests, so free-credit-only
operation requires account-level billing limits or a bounded validation session.

Weights persist in `dark-champion-model-cache`; reports persist in
`dark-champion-validation/<current-source-hash>`. Secrets, PID records and model
cache are separate. Historical reports/PASS, local virtualenvs, archives, cached
weights and local credentials are excluded from source upload.

Gateway defaults remain loopback for existing deployments; only the explicit
Modal profile listens on `0.0.0.0` inside its container. Existing request auth is
retained. Research/embedding/reranker/vLLM stay local to that container.

## Verified sources (reuse, do not research twice)

- https://modal.com/docs/guide/gpu — A100 variants; payment-method prerequisite.
- https://modal.com/docs/sdk/py/latest/web_server — web-server decorator.
- https://modal.com/docs/sdk/py/latest/Image — controlled source upload.
- https://modal.com/docs/sdk/py/latest/App — container limits and idle scale-down.
- https://modal.com/docs/guide/volumes — persistent model/report storage.
- https://modal.com/docs/guide/secrets — separate secret injection.
- https://modal.com/docs/guide/sandboxes — VM Docker support; GPU gVisor limitation.
- https://modal.com/pricing — free allowance versus actual dashboard credit.

Only every mandatory current-source live PASS permits READY and FINAL packaging.
