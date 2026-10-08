"""Modal desktop launcher: start the AI stack in the cloud and open the UI locally.

Run from a local machine with Modal CLI authenticated and .env present:

    python scripts/modal_desktop.py            # deploy + wait + open browser
    python scripts/modal_desktop.py --no-browser
    python scripts/modal_desktop.py --stop     # stop GPU serve app, keep control VM

What it does (all reused from existing production modules):
  1. Ensures runtime secrets exist in Modal (from the six keys in .env).
  2. Deploys modal_app.py so `serve` (GPU) is available on the platform.
  3. Ensures the persistent CPU control VM (Redis/Qdrant/SearXNG/Crawl4AI/
     sandbox-broker/Open WebUI) via modal_production.ensure_control(desktop=True).
  4. Triggers `serve` once to wake the GPU container (vLLM + gateway boot).
  5. Starts ONE authenticated SSH session to the control VM with a dynamic
     SOCKS proxy on 127.0.0.1:3128 (modal_control.start_forwarder).
  6. Polls gateway /health and Open WebUI /health through the tunnel.
  7. Opens the default browser at http://127.0.0.1:3000 using the SOCKS proxy.

No auxiliary port is ever published publicly; access rides the same pinned-SSH
transport model already used by validation. The tunnel dies with this script.
"""
import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from modal_control import SOCKS_PORT  # single source of truth for the desktop proxy port

UI_URL = f"http://127.0.0.1:{os.environ.get('OPEN_WEBUI_PORT', '3000')}"
GATEWAY_HEALTH = "http://127.0.0.1:8088/health"
UI_HEALTH = UI_URL + "/health"


def ensure_secret():
    """Create/update the scoped Modal Secret from the excluded local .env.

    Modal has no secret-update API: rotation means deleting the old name and
    recreating it. Deleting a non-existent secret is tolerated; any other error
    propagates so the launcher never deploys against a stale credential set.
    """
    import modal
    from modal_control import SECRET_KEYS
    from runtime_config import read_env
    values = read_env(ROOT / ".env")
    missing = [k for k in SECRET_KEYS if not values.get(k) or values[k] == "generated-by-bootstrap"]
    if missing:
        raise SystemExit("Run scripts/bootstrap_env.py first; missing keys: " + ", ".join(missing))
    from modal.exception import NotFoundError
    from modal.secret import SecretManager
    payload = {k: values[k] for k in SECRET_KEYS}
    try:
        # Preferred path on modern Modal CLI (>=1.x): rotate the existing secret
        # in place. Handles are synchronized, so this call blocks until done.
        modal.Secret.from_name("dark-champion-max-runtime-v1").update(payload)
        print("[desktop] runtime secret updated in place.")
    except NotFoundError:
        SecretManager().create("dark-champion-max-runtime-v1", payload)
        print("[desktop] runtime secret created.")
    except Exception as error:  # noqa: BLE001 - fall back to delete+create rotation
        print(f"[desktop] secret update unavailable ({type(error).__name__}); rotating instead.")
        try:
            SecretManager().delete("dark-champion-max-runtime-v1", allow_missing=True)
        except Exception as delete_error:  # noqa: BLE001
            print(f"[desktop] secret delete skipped ({type(delete_error).__name__})")
        SecretManager().create("dark-champion-max-runtime-v1", payload)


def deploy_app():
    """Push modal_app.py so the serve function exists on the platform.

    Windows note: Modal CLI prints unicode glyphs (e.g. U+2713) that cp1250/cp1252
    cannot encode; force UTF-8 stdio via PYTHONIOENCODING and tolerate residual
    decode errors instead of crashing the launcher.
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run([sys.executable, "-X", "utf8", "-m", "modal", "deploy", str(ROOT / "modal_app.py")],
                            cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace", env=env)
    if result.returncode:
        raise SystemExit("modal deploy failed:\n" + (result.stdout + result.stderr)[-2000:])


def wake_gpu(app):
    """Trigger one call so the GPU container starts vLLM + gateway inside serve()."""
    try:
        app["serve"].spawn()
        print("[desktop] GPU serve spawned; cold start (model load) can take ~10 min.")
    except Exception as error:  # noqa: BLE001 - spawn is best-effort, health poll decides
        print(f"[desktop] serve spawn skipped ({type(error).__name__}); relying on autoscaler.")


def wait_ready(timeout_s):
    """Poll gateway/UI health through the loopback SOCKS proxy until green.

    Prefers Python httpx (already a launcher dependency) so no external curl
    binary is required; falls back to `curl --socks5-hostname` when httpx is
    unavailable in the local interpreter.
    """
    def probe(url: str) -> str:
        try:
            import httpx
            try:
                response = httpx.get(url, timeout=8, proxy=f"socks5h://127.0.0.1:{SOCKS_PORT}",
                                     trust_env=False, follow_redirects=False)
                return str(response.status_code)
            except TypeError:  # older httpx uses proxies=
                response = httpx.get(url, timeout=8, proxies=f"socks5h://127.0.0.1:{SOCKS_PORT}",
                                     trust_env=False, follow_redirects=False)
                return str(response.status_code)
        except ImportError:
            result = subprocess.run(
                ["curl", "-s", "-o", os.devnull, "-w", "%{http_code}",
                 "--max-time", "8", "--proxy", f"socks5h://127.0.0.1:{SOCKS_PORT}", url],
                text=True, capture_output=True, encoding="utf-8", errors="replace")
            return result.stdout.strip() if result.returncode == 0 else "err"
        except Exception:
            return "err"

    deadline = time.monotonic() + timeout_s
    last = {}
    while time.monotonic() < deadline:
        codes = {label: probe(url) for label, url in (("gateway", GATEWAY_HEALTH), ("ui", UI_HEALTH))}
        last = codes
        # Gateway must answer 200; UI may answer 200 or redirect/401 before login.
        if last.get("gateway") == "200" and last.get("ui") in {"200", "302", "401"}:
            return True
        remaining = int(deadline - time.monotonic())
        print(f"[desktop] waiting... {last} left={remaining}s", flush=True)
        time.sleep(10)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="do not auto-open the browser")
    parser.add_argument("--timeout", type=int, default=1500, help="readiness deadline seconds")
    parser.add_argument("--skip-deploy", action="store_true", help="reuse current deployment")
    args = parser.parse_args()

    if "--stop" in sys.argv:
        subprocess.run([sys.executable, "-m", "modal", "app", "stop", "dark-champion-max"], check=False)
        print("[desktop] dark-champion-max stopped; control VM idles down after its own window.")
        return

    import modal
    from modal_control import local_keys, start_forwarder
    from modal_production import ensure_control

    values, private_key, public_key = local_keys(ROOT)
    # ensure_control() reads SECRET_KEYS from os.environ; hydrate them from .env.
    for key in values:
        os.environ.setdefault(key, values[key])
    os.environ["MODAL_CONTROL_PRIVATE_KEY"] = private_key
    os.environ["MODAL_CONTROL_PUBLIC_KEY"] = public_key

    if not args.skip_deploy:
        ensure_secret()
        deploy_app()

    app = modal.App.lookup("dark-champion-max", create_if_missing=True)
    print("[desktop] ensuring persistent control VM ...")
    try:
        control, route = ensure_control(ROOT, desktop=True)
    except Exception as error:  # noqa: BLE001 - surface redacted sandbox logs (modal_production already strips secrets)
        raise SystemExit(
            "[desktop] control VM bootstrap failed: " + str(error)[-2000:] +
            "\nInspect the 'dark-champion-control' sandbox logs at https://modal.com/dashboard.") from error
    print(f"[desktop] control VM ready (ssh {route['host']}:{route['port']})")

    wake_gpu(app)

    env = dict(os.environ)
    print(f"[desktop] starting pinned SSH + SOCKS tunnel on 127.0.0.1:{SOCKS_PORT} ...")
    transport = start_forwarder(env, route, ROOT)
    try:
        if not wait_ready(args.timeout):
            raise SystemExit("[desktop] readiness timeout; inspect reports/runtime logs on Modal.")
        print(f"[desktop] READY -> {UI_URL} (models: dark-general/dark-code/dark-reason/dark-max/dark-research)")
        print(f"[desktop] optional: export ALL_PROXY=socks5h://127.0.0.1:{SOCKS_PORT} for curl/API access")
        if not args.no_browser:
            # Plain http://127.0.0.1:3000 needs no proxy on the browser side;
            # add SOCKS only if you also want to reach other cloud ports.
            webbrowser.open(UI_URL)
        print("[desktop] press Ctrl+C to close the tunnel (cloud services keep their own lifetimes).")
        while True:
            if transport.poll() is not None:
                raise SystemExit("[desktop] SSH transport exited unexpectedly.")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n[desktop] closing tunnel.")
    finally:
        transport.terminate()
        try:
            transport.wait(timeout=10)
        except subprocess.TimeoutExpired:
            transport.kill()


if __name__ == "__main__":
    main()
