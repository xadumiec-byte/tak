# Fast cache strategy

The default design deliberately separates fast runtime model storage from persistent package caches.

- Model/Hugging Face cache: `/content/.cache/dark-champion/hf` on the Colab VM for fast model reads.
- `uv`/`pip` cache: may be persisted by setting `DARK_PERSIST_CACHE_ROOT` to a mounted private Drive directory.
- `scripts/prepare_model_cache.py` performs an idempotent Hugging Face snapshot download before vLLM starts. Existing complete cache objects are reused by `huggingface_hub`.
- `reports/MODEL_CACHE.json` records the requested model/revision and resolved cache path.
- Do not store tokens, `.env`, API keys or generated credentials in the persistent cache.

Recommended optional setup after mounting Drive:

```python
import os
os.environ["DARK_PERSIST_CACHE_ROOT"] = "/content/drive/MyDrive/dark-champion-package-cache"
```

Keeping model weights on `/content` avoids making vLLM load weights directly from a mounted Drive filesystem. If the Colab VM is destroyed, model weights may need to be transferred again; package caches can still survive. Use a persistent model cache only after measuring that it is faster in your actual Colab/Drive setup.
