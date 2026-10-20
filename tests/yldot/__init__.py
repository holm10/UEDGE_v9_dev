"""yldot regression suite (epic AIUE-9, PRD 1343489).

Run it as `pytest tests/yldot`, never `pytest tests/`: tests/deterministic_omp is a separate suite with its own
top-level `harness` package (decision 15). This file makes the suite the package `yldot`, so its harness is
`yldot.harness` and the two never clash. Needs Python >= 3.11 (tomllib; CI runs 3.11) and h5py.

The environment is pinned here, before anything imports numpy or uedge: no PyPI version check on import
(src/uedge/_banner.py:42) and one thread for OpenMP and BLAS.
"""
import os

os.environ["UEDGE_BANNER"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
