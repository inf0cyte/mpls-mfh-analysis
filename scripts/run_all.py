"""Run the full pipeline: pull permits, look up zoning and assessor records, then analyze.

Usage:  python scripts/run_all.py
"""
import runpy
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for step in ["pull_permits.py", "pull_zoning.py", "pull_assessor.py", "analyze.py", "net_units.py"]:
    print(f"\n===== {step} =====", flush=True)
    sys.argv = [step]
    runpy.run_path(str(HERE / step), run_name="__main__")
