# Testing — what actually exists

**The regression suite is not in this repository.** It lives on the `pytests` branch of
`LLNL/UEDGE` (`upstream/pytests`), and CI checks it out after building (`.github/workflows/build-test-wheel.yml:55-95`).
There are no unit tests of individual Fortran routines and no coverage measurement.

The repository holds one test case: `tests/deterministic_omp/`, the OpenMP Jacobian reproducer of AIUE-8 (deck, trimmed
data, `tests/deterministic_omp/tools/fingerprint.py`; see `tests/deterministic_omp/README.md`), with the bitwise
harness in `tests/deterministic_omp/harness/` (OpenMP vs serial: `cli.py`, with the test flow `cli.py flow`, see
`openmp-jacobian.md`; serial old vs new: `serial_check.py`). No CI job runs them yet.

## Serial old-vs-new bitwise check (required for Fortran, `.v` and `ppp/` changes)

Every PR that touches Fortran (`*.m`, `*.F90`, hand-written `*.f`), a `.v` file or `ppp/` must show that serial
results are **bitwise** unchanged against `v9-develop`, in the `--serial` build and in the default OpenMP build with
`ppp.OMPParallelJac = ppp.OMPParallelPandf1 = 0`. The pytests suite (`rtol=1e-5`) cannot show this.

```bash
python tests/deterministic_omp/harness/serial_check.py \
    --base-python BASE_SERIAL/bin/python --new-python NEW_SERIAL/bin/python \
    --base-omp-python BASE_OMP/bin/python --new-omp-python NEW_OMP/bin/python --jobs 4 --out DIR
```

Four venvs: base and change, each built `--serial` and default, from clean committed trees (the tool does not
build). It runs reproducer presets and pytests cases (D_only, D+C, D_mols, a 16x8 fulltest, drifts, slab and 20
one-switch unit variants; `--list`) once per build in fresh processes. Cases ending in `-itN` run N Newton iterations,
so `psetnk`, the ILU preconditioner, Krylov and the line search are covered. It compares every Jacobian, `sfscal`,
`suscal`, `yldot` and the `fnrm` sequence bit for bit.
- Exit 0: identical over the complete gate (both pairs, two different builds from clean committed trees with
  known sources, base on `origin/v9-develop`, `--cases all`).
- Exit 1: mismatch (the summary names the case and the first differing entry).
- Exit 2: harness error (a wrong build kind; same build, tree or clean commit; a record not on the serial path; an
  `-itN` case that did not iterate) or an incomplete gate (`RESULT: INCOMPLETE`; `--partial-ok` for a quick look).

Needs the pytests checkout (below). Paste the build lines and the `RESULT` line into the PR. Details:
`tests/deterministic_omp/README.md`.

## Suite structure (`upstream/pytests`)

```
pytests/fulltests/<case>/{input.py, conftest.py, test_<case>.py, gridue, *.h5 reference}
pytests/unittests/{D+C, D_mols, D_only, slab_D_only}/<case>/<variant>/{input.py, conftest.py, test_*.py, ...}
MakeTests.py      # regenerates reference solutions
```

Each test (`TestClass.test_reference`):
1. Silences output (`com.iprint = 0`), executes `input.py` to set up the case.
2. Sets `bbb.issfon=1`, `bbb.ftol=1e20` (evaluate only, no convergence) and runs `bbb.exmain()` from a stored,
   deliberately **perturbed** solution. The perturbation (`perturb_solution`, ±1 % random on
   `nis/ups/tes/tis/ngs/tgs/phis`) was applied to `solution.h5` by `write_data` when the reference was made; the test
   itself never calls it, so a test run is deterministic.
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

- `build-test-wheel.yml` builds with `--serial`, Python 3.11, `numpy==1.26.4`; it does not exercise OpenMP.
- `.github/workflows/build-test-omp.yml` (AIUE-57) tests the OpenMP paths: it builds the default OpenMP build
  (`pip install -v .`, Python 3.11, `numpy==1.26.4`) and runs `tests/deterministic_omp/ci/run_omp_ci.sh`, which runs
  the harness unit tests, a smoke test and the OpenMP test flow (`tests/deterministic_omp/README.md`, "CI").
  Triggers: `pull_request`, `push` to `v9-develop`/`main` only, and a nightly `schedule` (default branch only).
  PR set: `tebox1` (2, 4 threads, K=3, `jac`, one evaluation: locates the defect cell), `tebox` (2, 4 threads, K=5,
  both arms, `--itermx 3`) and `full` (2, 4 threads, K=2, `jac`, `--itermx 3`); nightly: `--all` one evaluation K=2
  and `--itermx 3` K=3. Gate: the `jac` arm, bitwise (`OMP_CI_JAC_TOLERANCE` is the switch for a future tolerance
  gate, which under `--itermx 3` must also cover `yldot`/`fnrm`); `jacrhs` is report-only.
  **Merge condition:** only after AIUE-56 (the OpenMP Jacobian fix) **and** once the gate can be green on that code,
  i.e. after decision 9 (a tolerance gate) or AIUE-61 (C2/M2 removed). The AIUE-56 build is still red under the
  bitwise gate; merged earlier, the job turns every push and PR red. Same steps locally:
  `PYTHON=<omp venv python> tests/deterministic_omp/ci/run_omp_ci.sh pr`.
- In `build-test-wheel.yml` the "Install pip dependencies" step runs `pip install forthon>=0.10.7 ...` unquoted: the
  shell redirects to a file named `=0.10.7`, so Forthon is installed unpinned. (`build-test-omp.yml` quotes it.)
- Non-`master` branches check out `pytests-develop`, which upstream does not have (only `pytests`) → test step fails on checkout.
- `@notest`/`@nowheel` commit tags are inert (no job `outputs:` on `check-requests`; `wheel` vs `wheels` mismatch).
- `build-basis.yml` runs BASIS level-1/level-2 tests in Docker (`fusionbillm/basisuedge`); skip with `#@nobasis`.
- `claude-review.yml` runs `/code-review` on PR open or `@claude-review` comment.
