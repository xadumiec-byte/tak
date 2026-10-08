"""A missing or stale live gate must never authorize FINAL packaging."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import release_manifest
import hashlib
import json
from live_acceptance import GATES

def test_final_gate_requires_complete_current_evidence(monkeypatch):
    monkeypatch.setattr(release_manifest, 'source_hash', lambda: 'current')
    report = {'verdict': 'READY', 'source_hash': 'current',
              'gates': {name: {'status': 'PASS'} for name in GATES}}
    assert release_manifest.final_ready(report)
    report['gates'].pop('sandbox_network')
    assert not release_manifest.final_ready(report)

    report['gates']['sandbox_network'] = {'status': 'NOT TESTED'}
    assert not release_manifest.final_ready(report)
    report['gates']['sandbox_network'] = {'status': 'PASS'}
    report['source_hash'] = 'stale'
    assert not release_manifest.final_ready(report)
    report['gates'] = {}
    assert not release_manifest.final_ready(report)

def test_source_hash_uses_portable_case_sensitive_relative_order(monkeypatch, tmp_path):
    upper = tmp_path / 'B.py'; upper.write_bytes(b'upper')
    lower = tmp_path / 'a.py'; lower.write_bytes(b'lower')
    monkeypatch.setattr(release_manifest, 'ROOT', tmp_path)
    monkeypatch.setattr(release_manifest, 'files', lambda: iter([lower, upper]))
    expected = hashlib.sha256(b'B.pyuppera.pylower').hexdigest()
    assert release_manifest.source_hash() == expected

def test_modal_final_rejects_missing_stale_or_failed_production_evidence(monkeypatch,tmp_path):
    monkeypatch.setattr(release_manifest,'ROOT',tmp_path)
    monkeypatch.setattr(release_manifest,'source_hash',lambda:'current')
    report={'verdict':'READY','source_hash':'current','deployment_target':'modal',
            'gates':{name:{'status':'PASS'} for name in GATES}}
    assert not release_manifest.final_ready(report)
    (tmp_path/'reports').mkdir()
    path=tmp_path/'reports/MODAL_DEPLOYMENT_ACCEPTANCE.json'
    production={'status':'PASS','source_hash':'stale','gates':{n:{'status':'PASS'} for n in ['models','auth','completion']}}
    path.write_text(json.dumps(production));assert not release_manifest.final_ready(report)
    production['source_hash']='current';path.write_text(json.dumps(production))
    assert release_manifest.final_ready(report)
    production['gates']['auth']['status']='FAIL';path.write_text(json.dumps(production))
    assert not release_manifest.final_ready(report)
