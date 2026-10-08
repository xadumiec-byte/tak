"""Only a measured A100 80 GB may satisfy the target environment gate."""
import importlib.util
import unittest
import tempfile
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('environment_capacity', Path(__file__).resolve().parents[1] / 'scripts/detect_environment.py')
detector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(detector)

class CapacityTests(unittest.TestCase):
    def test_modal_requires_measured_capacity_and_modal_identity(self):
        with patch.object(detector.platform, 'system', return_value='Linux'), patch.dict(detector.os.environ, {'MODAL_TASK_ID':'test-task'}, clear=True):
            for name, memory, expected in [('NVIDIA A100-SXM4-40GB',40960,'MODAL_A100_40GB'), ('NVIDIA A100-SXM4-80GB',81920,'MODAL_A100'), ('NVIDIA A100',None,'MODAL_GPU_OTHER'), ('NVIDIA H100',81920,'MODAL_GPU_OTHER')]:
                with self.subTest(name=name, memory=memory), patch.object(detector, 'gpu', return_value={'available':True,'name':name,'memory_mb':memory}):
                    self.assertEqual(detector.detect()['classification'], expected)

    def test_40gb_permission_does_not_weaken_80gb_requirement(self):
        measured = {'classification':'COLAB_A100_40GB', 'gpu':{'memory_mb':40960}}
        with tempfile.TemporaryDirectory() as directory, patch.object(detector, 'detect', return_value=measured), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            for requirement, expected in [('colab-a100',2), ('colab-a100-40gb',0)]:
                with patch.object(detector.sys, 'argv', ['detect_environment.py','--require',requirement,'--report',str(Path(directory)/'environment.json')]):
                    self.assertEqual(detector.main(),expected)

    def test_capacity_and_gpu_identity(self):
        with patch.object(detector.platform, 'system', return_value='Linux'), patch.dict(detector.os.environ, {'COLAB_RELEASE_TAG':'test'}):
            for name, memory, expected in [('NVIDIA A100-SXM4-40GB',40960,'COLAB_A100_40GB'), ('NVIDIA A100-SXM4-80GB',81920,'COLAB_A100'), ('NVIDIA A100',None,'COLAB_GPU_OTHER'), ('NVIDIA H100',81920,'COLAB_GPU_OTHER')]:
                with self.subTest(name=name, memory=memory), patch.object(detector, 'gpu', return_value={'available':True,'name':name,'memory_mb':memory}):
                    self.assertEqual(detector.detect()['classification'],expected)

if __name__ == '__main__':
    unittest.main()
