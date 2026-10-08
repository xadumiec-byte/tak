import os
import time
from pathlib import Path

import urllib.request

def read_env():
    values = {}
    for line in Path(".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values

env = read_env()
checks = [
    ("Gateway", f"http://localhost:{env.get('GATEWAY_PORT', '8088')}/health"),
    ("Open WebUI", f"http://localhost:{env.get('OPEN_WEBUI_PORT', '3000')}"),
    ("SearXNG", f"http://localhost:{env.get('SEARXNG_PORT', '8080')}"),
    ("Qdrant", f"http://localhost:{env.get('QDRANT_PORT', '6333')}/healthz"),
    ("Crawl4AI", f"http://localhost:{env.get('CRAWL4AI_PORT', '11235')}/health"),
]

failed = False
for name, url in checks:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            print(f"OK   {name:12} {response.status} {url}")
    except Exception as exc:
        failed = True
        print(f"FAIL {name:12} {url} :: {exc}")
raise SystemExit(1 if failed else 0)
