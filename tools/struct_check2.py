"""Compatibility entry point for workspace navigation structural assertions."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('struct_check.py')), run_name='__main__')
