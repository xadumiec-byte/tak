import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import modal_control as control

@pytest.mark.parametrize('state',['/tmp','/state'])
def test_persistent_storage_rejects_unmounted_or_unapproved_paths(state,monkeypatch):
 monkeypatch.setattr(Path,'is_mount',lambda _:False)
 with pytest.raises(ValueError):control.persistent_config({},state)

def test_persistent_storage_keeps_sandbox_isolation(monkeypatch):
 monkeypatch.setattr(Path,'is_mount',lambda _:True)
 monkeypatch.setattr(Path,'mkdir',lambda *a,**k:None)
 data={'services':{n:{'volumes':['old']} for n in ['redis','qdrant','open-webui']}}
 sandbox={'network_mode':'none','read_only':True,'cap_drop':['ALL']}
 data['services']['sandbox-runtime']=sandbox.copy()
 result=control.persistent_config(data,'/state')
 assert result['services']['sandbox-runtime']==sandbox
 assert result['services']['redis']['volumes']==[str(Path('/state')/'redis')+':/data']

@pytest.mark.parametrize('rows,expected',[
 ('20 10 sshd: root\n',True),
 ('11 10 sshd: root [priv]\n12 11 sshd: root@notty\n',True),
 ('20 1 sshd: root\n',False),
 ('20 10 sshd: root [priv]\n',False),
 ('11 10 sshd: unknown [preauth]\n',False)])
def test_only_owned_authenticated_transport_keeps_vm_alive(monkeypatch,rows,expected):
 monkeypatch.setattr(control.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=rows))
 master=SimpleNamespace(pid=10,poll=lambda:None)
 assert control.authenticated_transport(master)==expected
