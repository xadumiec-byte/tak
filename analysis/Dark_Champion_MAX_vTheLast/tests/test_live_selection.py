import asyncio
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import live_acceptance as live

def test_focused_skips_unselected_operations_and_cannot_certify_ready(monkeypatch,tmp_path):
    monkeypatch.setattr(live,'ROOT',tmp_path);monkeypatch.setattr(live,'source_hash',lambda:'test-source')
    (tmp_path/'reports').mkdir()
    audit=live.Audit(['citations'])
    assert 'research_lifecycle' in audit.selected
    async def forbidden():raise AssertionError('Unselected operation executed')
    asyncio.run(audit.check('benchmark',forbidden))
    assert audit.results['benchmark']['status']=='NOT TESTED'
    audit.results={name:{'status':'PASS','detail':'test-only'} for name in live.GATES}
    result=audit.write()
    assert result['verdict']=='REVISE'
    assert (tmp_path/'reports/LIVE_ACCEPTANCE_FOCUSED.json').exists()
    assert not (tmp_path/'reports/LIVE_ACCEPTANCE.json').exists()

@pytest.mark.parametrize('names',[[],['misspelled']])
def test_focused_invalid_gate_selection_rejected(names):
    with pytest.raises(ValueError):live.Audit(names)
