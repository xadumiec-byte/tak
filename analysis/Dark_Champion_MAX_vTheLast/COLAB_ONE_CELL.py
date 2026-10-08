# Dark Champion MAX vTheLast — one-cell Colab launcher
# Upload Dark_Champion_MAX_vTheLast_A100_40GB_REVISE.zip to /content first.
from pathlib import Path
import os, subprocess, zipfile, shutil

ZIP = Path("/content/Dark_Champion_MAX_vTheLast_A100_40GB_REVISE.zip")
ROOT = Path("/content/Dark_Champion_MAX_vTheLast")

if not ZIP.exists():
    raise FileNotFoundError(f"Upload {ZIP.name} to /content")

if not ROOT.exists():
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(ROOT)

matches = list(ROOT.rglob("WORK_COLAB_AUTOBUILD_PROMPT.md"))
if len(matches) != 1:
    raise RuntimeError(f"Expected one project root, found {len(matches)} prompt files")

project = matches[0].parent
os.chdir(project)
print("PROJECT:", project)

# Optional persistent cache:
# from google.colab import drive
# drive.mount("/content/drive")
# os.environ["DARK_PERSIST_CACHE_ROOT"] = "/content/drive/MyDrive/dark-champion-package-cache"

probe = subprocess.run(
    ["python", "scripts/detect_environment.py", "--require", "colab-a100-40gb"],
    check=False,
)
if probe.returncode == 2:
    raise SystemExit("Required Colab A100 is not assigned; stopping before expensive work.")
if probe.returncode != 0:
    raise RuntimeError(f"Environment detector failed: {probe.returncode}")

resume = Path("reports/RESUME_STATE.json")
if resume.exists():
    print("RESUME checkpoint found:", resume)

rc = subprocess.run(["bash", "scripts/colab_autobuild.sh"], check=False).returncode
if rc:
    raise SystemExit(f"Autobuild stopped at a failed gate, exit={rc}. Inspect reports/ and logs.")
print("Autobuild finished successfully.")
