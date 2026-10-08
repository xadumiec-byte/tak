import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

@pytest.mark.parametrize('timeout,expected',[(False,125),(True,124)])
def test_bounded_pipe_reader_and_group_cleanup(monkeypatch,timeout,expected):
    spec=importlib.util.spec_from_file_location('isolated_runner_test',Path(__file__).parents[1]/'services/sandbox/runner.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    process=MagicMock(pid=42)
    process.wait.return_value=0
    selector=MagicMock()
    selector.get_map.return_value={1:True}
    selector.select.return_value=[(SimpleNamespace(fd=1,data='stdout'),1)]
    kills=[]
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**k:process)
    monkeypatch.setattr(runner.selectors,'DefaultSelector',lambda:selector)
    monkeypatch.setattr(runner.os,'read',lambda *a:b'x'*4096)
    monkeypatch.setattr(runner.os,'killpg',lambda *a:kills.append(a),raising=False)
    monkeypatch.setattr(runner.signal,'SIGKILL',9,raising=False)
    if timeout:
        ticks=iter([0,2]);monkeypatch.setattr(runner.time,'monotonic',lambda:next(ticks))
    result=runner.execute('not executed; process is mocked',1)
    assert result['exit_code']==expected
    assert len(result['stdout'])+len(result['stderr'])<=runner.LIMIT
    assert kills==[(42,9)]
    process.stdout.close.assert_called_once()
    process.stderr.close.assert_called_once()
