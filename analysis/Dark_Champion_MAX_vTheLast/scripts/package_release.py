import json
import zipfile
from release_manifest import ROOT,files,final_ready

state=json.loads((ROOT/'reports/WORK_STATE.json').read_text())
level=state['verdict']
if level=='READY':
    live=json.loads((ROOT/'reports/LIVE_ACCEPTANCE.json').read_text())
    if state.get('target')=='modal' and live.get('deployment_target')!='modal':
        raise SystemExit('FINAL gate rejected: Modal target requires Modal live evidence')
    if not final_ready(live):
        raise SystemExit('FINAL gate rejected: current source has no complete passing live acceptance')
    suffix='FINAL'
elif level=='A100_READY':suffix='A100_READY'
else:suffix='REVISE_2'
archive=ROOT.parent/f'Dark_Champion_MAX_vTheLast_{suffix}.zip'
paths=sorted(files())
manifest=ROOT/'reports/PACKAGE_CONTENTS.txt'
manifest.write_text('\n'.join(str(p.relative_to(ROOT)).replace('\\','/') for p in paths)+'\n',encoding='utf-8')
if manifest not in paths:paths.append(manifest)
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path in paths:z.write(path,str(ROOT.name+'/'+str(path.relative_to(ROOT)).replace('\\','/')))
with zipfile.ZipFile(archive) as z:
    if z.testzip() is not None:raise SystemExit('Archive integrity failure')
print(archive)
print('Archive integrity: PASS; final gate level: '+level)
