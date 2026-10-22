"""Compatibility entry point for isolated real workspace rendering checks."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('workspace_check.py')), run_name='__main__')
