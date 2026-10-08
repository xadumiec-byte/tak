import hashlib
import os
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','__pycache__','.pytest_cache','.pytest-temp','.run','.cache','model_cache','hf_cache','.huggingface','huggingface_cache'}
def files():
    for directory,subdirs,names in os.walk(ROOT):
        subdirs[:]=[n for n in subdirs if n not in EXCLUDED and not n.startswith('.venv')]
        for name in names:
            path=Path(directory)/name
            if name=='.env' or (name.startswith('.env.') and name!='.env.example') or path.suffix in {'.pyc','.zip','.tmp','.bin','.safetensors','.pt','.pth','.onnx'}:continue
            yield path
def source_hash():
    digest=hashlib.sha256()
    for path in sorted(files(), key=lambda p: p.relative_to(ROOT).as_posix()):
        relative=path.relative_to(ROOT)
        if relative.parts[0]=='reports' or path.suffix=='.md':continue
        digest.update(str(relative).replace('\\','/').encode());digest.update(path.read_bytes())
    return digest.hexdigest()

def final_ready(report):
    from live_acceptance import GATES
    gates = report.get('gates', {})
    complete = (report.get('verdict') == 'READY' and report.get('source_hash') == source_hash()
            and set(gates) == set(GATES)
            and all(g.get('status') == 'PASS' for g in gates.values()))
    if not complete:return False
    if report.get('deployment_target') == 'modal':
        try:deployment=json.loads((ROOT/'reports/MODAL_DEPLOYMENT_ACCEPTANCE.json').read_text())
        except (OSError,ValueError):return False
        required={'models','auth','completion'}
        return (deployment.get('status')=='PASS' and deployment.get('source_hash')==source_hash()
                and required <= set(deployment.get('gates',{}))
                and all(deployment['gates'][name].get('status')=='PASS' for name in required))
    return True
