from pathlib import Path
import subprocess
import sys

def test_secret_merge_is_idempotent_and_preserves_operator_key(tmp_path):
    root=Path(__file__).parents[1]
    (tmp_path/'.env.example').write_text((root/'.env.example').read_text())
    (tmp_path/'.env').write_text('DARK_API_KEY=operator-secret\nVLLM_MODEL=cognitivecomputations/dolphin-2.9.3-qwen2-32b\n')
    command=[sys.executable,str(root/'scripts/bootstrap_env.py')]
    subprocess.run(command,cwd=tmp_path,check=True,capture_output=True)
    result=(tmp_path/'.env').read_text()
    assert 'DARK_API_KEY=operator-secret' in result
    assert 'generated-by-bootstrap' not in result
    assert 'VLLM_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct' in result
    assert 'SANDBOX_API_KEY=' in result
    subprocess.run(command,cwd=tmp_path,check=True,capture_output=True)
    assert (tmp_path/'.env').read_text()==result
