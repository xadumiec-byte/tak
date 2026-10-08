from pathlib import Path
import secrets

path = Path(".env")
template = Path(".env.example")
if not path.exists():
    path.write_text(template.read_text())

text = path.read_text()
# Merge newly introduced defaults while retaining operator settings and existing secrets.
existing = dict(line.split("=",1) for line in text.splitlines() if line and not line.startswith("#") and "=" in line)
if existing.get("VLLM_MODEL") == "cognitivecomputations/dolphin-2.9.3-qwen2-32b":
    text = text.replace("VLLM_MODEL=cognitivecomputations/dolphin-2.9.3-qwen2-32b", "VLLM_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct")
    existing["VLLM_MODEL"] = "Qwen/Qwen2.5-Coder-14B-Instruct"
for line in template.read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=",1)
        if key not in existing:
            if key == "VLLM_MODEL_REVISION" and existing.get("VLLM_MODEL") != "Qwen/Qwen2.5-Coder-14B-Instruct": value = ""
            if key == "VLLM_VERIFIED_CONTEXT_LIMIT" and existing.get("VLLM_MODEL") != "Qwen/Qwen2.5-Coder-14B-Instruct": value = ""
            text += f"\n{key}={value}\n"
for key in ("DARK_API_KEY", "VLLM_API_KEY", "SANDBOX_API_KEY", "WEBUI_SECRET_KEY", "CRAWL4AI_API_TOKEN", "SEARXNG_SECRET"):
    marker = f"{key}=generated-by-bootstrap"
    if not any(line.startswith(key + "=") for line in text.splitlines()):
        text += f"\n{marker}\n"
    text = text.replace(marker, f"{key}={secrets.token_urlsafe(48)}")
path.write_text(text)
print("Environment initialized in .env")
