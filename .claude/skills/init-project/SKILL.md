---
name: init-project
description: Set up UEDGE from a fresh clone — Python environment, Fortran/OpenMP toolchain, pip build (serial and OpenMP), smoke test, and the regression-test worktree. Use on a new machine or a clean checkout.
---

# Initialize UEDGE locally

Source of truth: `README.md` (install section), `setup.py`, `pyproject.toml`, `CLAUDE.md` → *Build & validation
commands*. Check them if anything below disagrees.

## 1. Python environment

Use a dedicated venv/conda env (UEDGE installs compiled modules into it):

```bash
python -m venv .venv && source .venv/bin/activate     # or conda create -n uedge python=3.11
python -m pip install --upgrade pip
python -m pip install "forthon>=0.10.7" numpy h5py
python -m pip install matplotlib scipy scikit-image   # optional: plotting extra (ueplot)
```

CI uses Python 3.11 and `numpy==1.26.4`; match that if results must be comparable to CI.

## 2. Compiler toolchain

- **gfortran** with OpenMP support (`gfortran --version`).
- **Linux:** system gcc/gfortran is usually enough.
- **macOS:** `brew install gcc libomp llvm`; Apple clang lacks OpenMP, so point `CC` at an OpenMP-capable clang
  and link libomp:
  ```bash
  export CC=$(brew --prefix llvm)/bin/clang
  export LDFLAGS="-L$(brew --prefix libomp)/lib"
  ```
  (CI does the same in `build-test-wheel.yml`.)

## 3. Build

```bash
pip install -v .                                    # OpenMP build (default)
pip install . -C "--build-option=--serial"          # serial, as CI tests
pip install . -C "--build-option=--debug"           # bounds/FPE checks for debugging
```

Build failures: read the first error in the verbose log; errors point at generated `.F` files — fix the `.m`.

## 4. Smoke test

```bash
cd /tmp && python -c "import uedge; from uedge import bbb; print(bbb.uedge_ver)"
```

Run from outside the repo so the installed package (not `src/`) is imported. Watch for a `.uedgerc.py` in
`$HOME` or the cwd — it runs on import.

## 5. Regression tests (optional, needed for `validate`)

```bash
git remote get-url upstream || git remote add upstream https://github.com/LLNL/UEDGE.git
git fetch upstream pytests
git worktree add ../uedge-pytests upstream/pytests
pip install pytest pytest-isolate
cd ../uedge-pytests && pytest --isolate --tb=short pytests/unittests/D_only -s
```

## 6. Claude Code hooks

The project hooks run through `uv` — install it (`brew install uv` or `pipx install uv`) or every tool call will
log a hook error.

## Report

Python/numpy/Forthon versions, compiler and OpenMP status, which builds succeeded, `uedge_ver`, and test result.
