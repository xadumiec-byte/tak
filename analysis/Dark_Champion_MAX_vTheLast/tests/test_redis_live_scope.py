import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from redis_live_recovery import control_command, RecoveryUnavailable

@pytest.mark.parametrize('env', [{}, {'DARK_DEPLOYMENT':'modal'},
    {'DARK_DEPLOYMENT':'local','DARK_ACCEPTANCE_SESSION':'true'}])
def test_fault_requires_explicit_isolated_acceptance(env,tmp_path):
    with pytest.raises(RecoveryUnavailable):
        control_command(env,'print(1)',tmp_path)

def test_fault_requires_pinned_identity(tmp_path):
    env={'DARK_DEPLOYMENT':'modal','DARK_ACCEPTANCE_SESSION':'true'}
    with pytest.raises(RecoveryUnavailable):control_command(env,'print(1)',tmp_path)
    directory=tmp_path/'.run/ssh';directory.mkdir(parents=True)
    (directory/'identity').write_text('test-only')
    (directory/'known_hosts').write_text('[test.modal.host]:1234 ssh-ed25519 test-only\n')
    command=control_command(env,'print(1)',tmp_path)
    assert 'StrictHostKeyChecking=yes' in command
    assert 'IdentitiesOnly=yes' in command
    assert 'root@test.modal.host' in command
    (directory/'known_hosts').write_text('[test.modal.host]:99999 ssh-ed25519 test-only\n')
    with pytest.raises(RecoveryUnavailable):control_command(env,'print(1)',tmp_path)
