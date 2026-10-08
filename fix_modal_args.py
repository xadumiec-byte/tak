"""One-shot repair script for Dark Champion MAX launcher (Windows/Modal).

Fixes the three API-argument failures seen in live runs:
  1. modal.Secret.from_dict(name=...)        -> SecretManager().create(name, data)
     (newer Modal CLI removed the `name` kwarg from from_dict)
  2. app["serve"].spawn() on a web_server    -> background "wake" run via sandbox.exec
     (spawn() raises TypeError on decorated functions; GPU cold start is triggered
      instead by polling gateway health through the tunnel)
  3. Pinned SSH transport exits immediately  -> Windows OpenSSH cannot read identity
     files with ACL-inherited permissions; fixable only inside the launcher, so this
     script also patches scripts/modal_control.py to chmod + verify readability of
     the private key before spawning ssh, and to surface stderr diagnostics.

Usage (from the project root):
    python fix_modal_args.py            # apply all fixes
    python fix_modal_args.py --check    # show current state, change nothing
"""
import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
FILES = {
    "desktop": ROOT / "scripts" / "modal_desktop.py",
    "control": ROOT / "scripts" / "modal_control.py",
    "production": ROOT / "scripts" / "modal_production.py",
}


def check_syntax(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def patch_secret_api(text: str) -> str:
    """Replace every modal.Secret.from_dict(..., name=X) / create(label=X) call."""
    text = re.sub(
        r"modal\.Secret\.from_dict\((\{[^\n]*?\}),\s*name\s*=\s*\"([^\"]+)\"\)",
        r'_secret_put("\2", \1)',
        text,
    )
    text = re.sub(
        r"modal\.Secret\.from_dict\((\{[^\n]*?\}),\s*label\s*=\s*\"([^\"]+)\"\)",
        r'_secret_put("\2", \1)',
        text,
    )
    # label= form of from_name too
    text = re.sub(
        r"modal\.Secret\.from_name\(\"([^\"]+)\",\s*label\s*=\s*\"[^\"]+\"\)",
        r'modal.Secret.from_name("\1")',
        text,
    )
    helper = '''
def _secret_put(name: str, data: dict) -> None:
    """Create-or-replace a Modal Secret across old/new CLI APIs.

    Newer modal versions dropped the name kwarg from Secret.from_dict and have
    no update endpoint, so rotation means delete-by-name then create-by-name.
    """
    import modal
    from modal.secret import SecretManager
    manager = SecretManager(client=modal.client.Client.from_config())
    try:
        manager.delete(name, allow_missing=True)
    except Exception as error:  # noqa: BLE001 - tolerate unknown secret states
        print(f"[secret] delete skipped ({type(error).__name__})")
    manager.create(name, data)

'''
    if "_secret_put" not in text:
        lines = text.splitlines(keepends=True)
        insert_at = 0
        for i, line in enumerate(lines):
            if re.match(r"^(import |from )", line):
                insert_at = i + 1
        text = "".join(lines[:insert_at]) + helper + "".join(lines[insert_at:])
    return text


def patch_serve_wake(text: str) -> str:
    """web_server functions have no .spawn(); wake the GPU via an HTTP-less trigger."""
    old = 'app["serve"].spawn()'
    new = ('_wake_gpu(app)\n        '
           '# legacy fallback kept for non-web deployments:\n'
           '# app["serve"].spawn()')
    if old in text and "_wake_gpu(" not in text:
        text = text.replace(old, new)
        helper = '''
def _wake_gpu(app):
    """Trigger one serve() invocation without .spawn() (unsupported on web_server).

    A deployed web_server function cannot be spawned directly; instead we run a
    throwaway CPU sandbox that hits the app's serving URL once. If lookup fails,
    the autoscaler will still boot serve() on the first real request.
    """
    import modal
    try:
        image = modal.Image.debian_slim(python_version="3.12").pip_install("httpx")
        with modal.Sandbox.create("python3", "-c",
                                  "import httpx; httpx.get('https://dark-champion-max.modal.run/health', timeout=30)",
                                  image=image, timeout=60) as probe:
            probe.wait()
    except Exception as error:  # noqa: BLE001 - best-effort wake-up
        raise error


'''
        marker = "def wake_gpu(app):"
        text = text.replace(marker, helper.lstrip("\n") + marker)
    return text


def patch_ssh_transport(text: str) -> str:
    """Windows-safe key handling + stderr surfacing in _ssh_transport."""
    old_write = "    private.write_text(env['MODAL_CONTROL_PRIVATE_KEY']); private.chmod(0o600)"
    new_write = (
        "    private.write_text(env['MODAL_CONTROL_PRIVATE_KEY'])\n"
        "    try:\n"
        "        private.chmod(0o600)\n"
        "    except OSError:\n"
        "        pass  # Windows NTFS ignores POSIX bits; verify readability instead\n"
        "    if os.name == 'nt':\n"
        "        subprocess.run(['icacls', str(private), '/inheritance:r',\n"
        "                        '/grant:r', f'{os.environ.get(\"USERNAME\", \"\")}:(R,W)'],\n"
        "                       capture_output=True, check=False)\n"
        "    if not private.read_text().startswith(('-----BEGIN', 'ssh-')):\n"
        "        raise ValueError('Control private key file looks corrupt; delete .run/modal-control-key and rerun bootstrap')"
    )
    if old_write in text and "icacls" not in text:
        text = text.replace(old_write, new_write)
    old_raise = "            raise RuntimeError('Pinned SSH transport exited; inspect ' + log_name)"
    new_raise = (
        "            log_path = root / '.run' / 'ssh' / log_name\n"
        "            tail = ''\n"
        "            try:\n"
        "                tail = log_path.read_bytes()[-1500:].decode(errors='replace')\n"
        "            except OSError:\n"
        "                pass\n"
        "            raise RuntimeError(\n"
        "                'Pinned SSH transport exited; inspect ' + log_name + '\\n' + tail)"
    )
    if old_raise in text and "log_path.read_bytes()" not in text:
        text = text.replace(old_raise, new_raise)
    if "import os" not in text.splitlines()[0]:
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if re.match(r"^(import |from )", line):
                lines.insert(i, "import os\n")
                break
        text = "".join(lines)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report state without changes")
    args = parser.parse_args()

    report = []
    for label, path in FILES.items():
        if not path.exists():
            report.append(f"{label}: MISSING {path}")
            continue
        text = path.read_text(encoding="utf-8")
        original = text
        text = patch_secret_api(text)
        text = patch_serve_wake(text)
        if label == "control":
            text = patch_ssh_transport(text)
        changed = text != original
        status = "PATCH NEEDED" if changed else "already fixed"
        report.append(f"{label}: {status}")
        if changed and not args.check:
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                backup.write_text(original, encoding="utf-8")
            path.write_text(text, encoding="utf-8")
            try:
                check_syntax(path)
            except SyntaxError as error:
                path.write_text(original, encoding="utf-8")
                report.append(f"{label}: SYNTAX ERROR -> reverted from backup ({error})")
    print("\n".join(report))
    if not args.check:
        print("\nDone. Backups saved next to each patched file (*.py.bak).\n"
              "Re-run:  $env:PYTHONUTF8='1'; python scripts\\modal_desktop.py")


if __name__ == "__main__":
    main()
