"""Launcher regressions: secret rotation API, env hydration, curl-free readiness."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "scripts" / "modal_desktop.py"


def _source() -> str:
    return DESKTOP.read_text(encoding="utf-8")


def test_launcher_parses():
    ast.parse(_source())


def test_secret_rotation_uses_supported_api():
    source = _source()
    # The old call passed name= to Secret.from_dict, which raises TypeError on modal 1.x.
    assert "Secret.from_dict(" not in source.replace("from_dict({k", ""), \
        "modal_desktop must not call Secret.from_dict(..., name=...)"
    assert "SecretManager()" in source and ".create(" in source
    assert "NotFoundError" in source, "missing-secret path must be handled explicitly"


def test_environment_hydration_before_control():
    tree = ast.parse(_source())
    main = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    lines = _source().splitlines()

    def line_of(name: str) -> int:
        for node in ast.walk(main):
            if isinstance(node, ast.Call):
                func = node.func
                label = getattr(func, "id", None) or getattr(func, "attr", None)
                if label == name:
                    return node.lineno
        raise AssertionError(f"{name}() not found in main()")

    assert line_of("local_keys") < line_of("ensure_control"), \
        "os.environ must be hydrated from .env before ensure_control reads SECRET_KEYS"


def test_readiness_probe_prefers_httpx_over_curl():
    source = _source()
    tree = ast.parse(source)
    wait = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "wait_ready")
    body = ast.unparse(wait)
    assert "import httpx" in body, "health polling must not require the external curl binary"
    assert "socks5h://" in body


def test_requirements_pin_modal_and_socks_support():
    requirements = (ROOT / "requirements-modal.txt").read_text(encoding="utf-8")
    assert "modal==" in requirements
    assert "httpx" in requirements and "socks" in requirements
