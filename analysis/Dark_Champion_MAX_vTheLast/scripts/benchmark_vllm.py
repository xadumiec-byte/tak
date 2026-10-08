"""Compatibility entry point for the canonical measured acceptance suite."""
from pathlib import Path
import runpy
if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('live_acceptance.py')), run_name='__main__')
