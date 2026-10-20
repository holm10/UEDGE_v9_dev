"""Harness of the yldot suite (epic AIUE-9, PRD section 6).

process.py is the parent side (Runner: forkserver or spawn children, timeouts, classified results); state.py is
the child side (the evaluation protocol). The environment pin of tests/yldot/__init__.py is repeated here for use
outside pytest.
"""
import os

os.environ["UEDGE_BANNER"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

from .process import CONFIGS, FAMILIES, FamilyError, Result, Runner, load_evaluation  # noqa: E402

__all__ = ["CONFIGS", "FAMILIES", "FamilyError", "Result", "Runner", "load_evaluation"]
