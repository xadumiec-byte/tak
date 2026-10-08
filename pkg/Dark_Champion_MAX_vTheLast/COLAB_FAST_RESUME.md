# Colab fast restart / cache / resume

## Fast path
1. Upload `Dark_Champion_MAX_vTheLast_A100_RESUME.zip` to `/content`.
2. Paste the contents of `COLAB_ONE_CELL.py` into one Colab code cell.
3. The launcher aborts before heavy work unless `COLAB_A100` is detected.
4. `reports/RESUME_STATE.json` records completed gates and lets later runs skip safe completed setup work.
5. The benchmark matrix is never started until baseline live acceptance passes.

## Cache
By default caches live under `/content/.cache/dark-champion`, which accelerates repeated commands in the same VM.
For persistence across Colab VM resets, mount Drive and set `DARK_CACHE_ROOT` before autobuild, for example to a private project cache directory. Do not place `.env`, tokens or generated credentials in that cache.

## Resume
After a disconnect, rerun the one-cell launcher. It re-detects hardware, reads the checkpoint, reuses caches, restarts runtime services, and continues from the cheapest safe gate. Runtime-dependent gates are deliberately revalidated.

## Safety
A checkpoint never converts a failed live gate to PASS. Source changes are recorded. Final READY still requires the repository's live acceptance invariant.
