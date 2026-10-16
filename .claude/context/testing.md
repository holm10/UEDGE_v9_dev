# Testing — what actually exists

**The regression suite is not in this repository.** It lives on the `pytests` branch of
`LLNL/UEDGE` (`upstream/pytests`), and CI checks it out after building (`.github/workflows/build-test-wheel.yml:55-95`).
There are no unit tests of individual Fortran routines and no coverage measurement.

The repository holds one test case: `tests/deterministic_omp/`, the OpenMP Jacobian reproducer of AIUE-8 (deck, trimmed
data, `tests/deterministic_omp/tools/fingerprint.py`; see `tests/deterministic_omp/README.md`), with the bitwise
OpenMP-vs-serial harness and test flow in `tests/deterministic_omp/harness/` (`cli.py flow`; see
`openmp-jacobian.md`). No CI job runs it yet.

## Suite structure (`upstream/pytests`)

```
pytests/fulltests/<case>/{input.py, conftest.py, test_<case>.py, gridue, *.h5 reference}
pytests/unittests/{D+C, D_mols, D_only, slab_D_only}/<case>/<variant>/{input.py, conftest.py, test_*.py, ...}
MakeTests.py      # regenerates reference solutions
```

Each test (`TestClass.test_reference`):
1. Silences output (`com.iprint = 0`), executes `input.py` to set up the case.
2. Sets `bbb.issfon=1`, `bbb.ftol=1e20` (evaluate only, no convergence) and runs `bbb.exmain()` from a stored,
   deliberately **perturbed** solution (`perturb_solution`, ±1 % on `nis/ups/tes/tis/ngs/tgs/phis`).
3. Cycles the equation switches (`isnion … isphion`) one at a time and compares the residual `fnrm` and
   case-setup variables against the reference with `rtol=1e-5`. A failure prints which equation/species diverged.
   This makes the suite a sensitive check of the **RHS residual (`pandf`)**, not of converged physics.

`conftest.py` chdirs into the case dir (same fixture as `pyexamples/input_example/conftest.py`).
`pytest --isolate` (pytest-isolate) is required: each test needs a fresh process because Forthon module state is global.

## Running locally

```bash
pip install . -C "--build-option=--serial"     # mirror CI
pip install pytest pytest-isolate
git fetch upstream pytests
git worktree add ../uedge-pytests upstream/pytests
cd ../uedge-pytests
pytest --isolate --tb=long pytests/unittests/D_only -s        # fastest
pytest --isolate --tb=long pytests/fulltests -s
```

Pick the suite that exercises your change (impurities → `D+C`, molecules → `D_mols`, slab geometry →
`slab_D_only`). Physics-neutral changes must pass **all** suites unchanged.

## When results change intentionally

New physics should be off by default, so references stay valid. If a reference must change (bugfix), regenerate
it with `MakeTests.py` on the `pytests` branch in a separate PR and explain the diff in the main PR.

## CI facts / quirks

- Builds with `--serial`, Python 3.11, `numpy==1.26.4`. OpenMP paths are not tested in CI.
- Non-`master` branches check out `pytests-develop`, which upstream does not have (only `pytests`) → test step fails on checkout.
- `@notest`/`@nowheel` commit tags are inert (no job `outputs:` on `check-requests`; `wheel` vs `wheels` mismatch).
- `build-basis.yml` runs BASIS level-1/level-2 tests in Docker (`fusionbillm/basisuedge`); skip with `#@nobasis`.
- `claude-review.yml` runs `/code-review` on PR open or `@claude-review` comment.
