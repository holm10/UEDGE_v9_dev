# Testing — what actually exists

**The regression suite is not in this repository.** It lives on a `pytests` branch. **v9 work uses `origin/pytests`**
(the holm10 fork): it holds v9's own references, regenerated for the v9 physics and listed with their reason in
`V9_REFERENCE_CHANGES.md` on that branch, for a later merge into LLNL's `upstream/pytests`. CI still checks out
LLNL's branch after building (`.github/workflows/build-test-wheel.yml:55-95`, quirks below).
There are no unit tests of individual Fortran routines and no coverage measurement.

The repository holds two test trees. `tests/deterministic_omp/` is the OpenMP Jacobian reproducer of AIUE-8 (deck, trimmed
data, `tests/deterministic_omp/tools/fingerprint.py`; see `tests/deterministic_omp/README.md`), with the bitwise
harness in `tests/deterministic_omp/harness/` (OpenMP vs serial: `cli.py`, with the test flow `cli.py flow`, see
`openmp-jacobian.md`; serial old vs new: `serial_check.py`). No CI job runs them yet.

`tests/yldot/` is the yldot suite (epic AIUE-9). Run it as `pytest tests/yldot` (never `pytest tests/`). One bullet
per component; a ticket that adds a component adds a bullet, one that changes a component edits only its bullet:

- **Families** `tests/yldot/families/<f>/`: `input.py` in normal form (it never loads a state), the grid,
  `reference_state.h5`, a seeded perturbed `base_state.h5` and `family.toml` (provenance, convergence norms, σ, seed,
  floors, `[evaluation]` W/P/timeout/Δt, owner-confirmed `[regions]`); the rate files once in `data/`. A measured
  family (AIUE-86) has W = P = 1, `child_reuse = false` (owner: one fresh child per evaluation; d_mols' `input.py`
  cannot run twice in one process) and a `[history]` table; an unmeasured one keeps the 2/2 placeholders.
  Both states are round-trip fixed points: re-saved after one `exmain`, so a further `exmain` changes no saved entry
  (AIUE-140: `convert` and `convsr_vo1` do not round-trip exactly, and `gridseq` re-saves the result).
  The five small families keep all their files in git; the three owner families (`large_dd2c`, `dnull_imp2`,
  `imp7`, AIUE-91) keep only `input.py` and `family.toml` there: their grid, `inputs.h5` and states are release
  assets of `yldot-data-v1`, gitignored, with their SHA-256s only in `references/<f>.manifest.json` (owner,
  2026-10-21). While all of a family's assets are absent, `conftest.py` skips every test parametrised over it except
  those marked `toml_only`; partly present or different files fail (`test_smoke.py::test_external_files`).
  The five small families also hold `sigma.h5`, the measured round-off spread σ_i per configuration (see
  Tolerances). Their reference files `references/<f>.h5` (the defaults, see Store) are release assets of
  `yldot-data-v2`, gitignored, named by `references/<f>.manifest.json` (AIUE-88); `fetch_data.py` fetches them.
- **Runner** `tests/yldot/harness/process.py` (package `yldot.harness`): every evaluation in an isolated child
  (forkserver preloading `uedge`, or spawn; HOME/cwd in an empty directory; timeouts; results
  `ok`/`error`/`crash`/`timeout`, `FamilyError` for a family defect). Importing the package pins `OMP_NUM_THREADS=1`
  for the process; an OpenMP run imports `uedge` first (`uedge-gotchas.md` → Test tooling, AIUE-147).
- **Protocol** `tests/yldot/harness/state.py`: PRD §6, the `steady` and `timestep` configurations returning `yldot` and
  `yldot_J`, and the `intake` configuration (`issfon=1` at `reference_state.h5`, no variant) returning `yldot` and
  `sfscal`; every configuration also returns `idx*`, `igyl`, the `is<eq>onxy` masks and the grid indices.
- **Comparator** `tests/yldot/harness/compare.py`: maps every row to (equation, species, ix, iy, region) from those
  arrays only, checked as a bijection (`IndexTruthError`). Regions follow one of three rules, chosen by the
  `[regions]` source keys and checked against the live grid: single null (ixpt1, ixpt2, iysptrx), slab half mesh
  (nxcore, nxleg, nycore), or double null (`nxpt = 2`, upper X-point primary: ixlb, ixrb, ixpt1, ixpt2, iysptrx1,
  iysptrx2 per mesh half; guard also at the cut, ix = ixrb(1)+1 and ixlb(2); regions pf_upper, pf_lower,
  sol_between and four legs; owner, 2026-10-21, AIUE-91). The species in a label is Fortran's 1-based `ifld`/`igsp`.
  Then the PRD §7.4 per-entry tolerance (σ = 0 floors,
  `ToleranceEscalation`), the full-vector comparator and the first differing diagnostic in `pandf` order.
- **Variants** (PRD §7.2): `tests/yldot/harness/inputs.py` is the input inventory, read with Forthon's own `.v` parser
  (968 `+input`/`+maybeinput` variables; a line grep overcounts); `tests/yldot/harness/variants.py` holds the value
  rules, `plan()` and `apply()` (in the child: `d` read live, the applied value recorded exactly and replayable
  through `Runner.evaluate(..., variant=, replay=)`); `tests/yldot/overrides.toml` holds the additions, exclusions,
  explicit values, bounds, phase and configuration, each with a reason.
- **Store** (PRD §7.3): `tests/yldot/harness/store.py` writes and reads one HDF5 reference file per family
  (`create`, `open_store`): `FullVectorStore` (full default, variants as the rows that differ bitwise) or
  `SketchStore` (full default, per (equation, species, region) block k = 8 projections onto Rademacher signs from
  `PCG64.random_raw`, summed with `math.fsum`; `sketch_compare` with c = 6.5), both with the sparse Jacobian-flag
  difference; files written with `track_times=False` so the bytes are reproducible. `tests/yldot/harness/manifest.py`
  is the schema of `references/<f>.manifest.json`, the only record of the external files' SHA-256s (owner,
  2026-10-21). `open_store` checks the file SHA-256, the dataset set, the blocks and that the manifest's
  `guarded`, `unguarded` and variant SHA-256s and its variant set follow from the datasets; every read recomputes
  the dataset's SHA-256 (`StoreIntegrityError`).
- **Tools** `tests/yldot/tools/`: `make_base_state.py` (`check`, which also reports `fixed_point`; `make`, which
  re-saves both states after one `exmain` and refuses one that is not a fixed point); `intake_check.py` (per-row
  scaled residuals at `reference_state.h5`, tables for the owner, no automatic flag); `measure_history.py` (`run`:
  W and P from exmain/pandf repeats in fresh processes, the -1 → +1 → -1 flag sequence, steady +1 vs -1 with the
  `ishosor = 0` counterfactual, a reuse sequence in one process, child costs and the sweep estimate, as a TOML
  fragment; `check`: family.toml's W, P against W+1, P+1 and the flag rules; exit 4 = defect, 3 = owner);
  `fetch_data.py` (`gh release download` of a manifest's `yldot-data-v<N>` assets into the gitignored `.data/<tag>/`,
  refusing any SHA-256 mismatch, then a relative symlink at each manifest path; `--check` verifies only);
  `release_data.py` (the release command: checks the files, the tag number (no remote git tag either) and the
  target, prints `gh release create`; publishes only with `--publish`, which the owner runs or approves);
  `measure_roundoff.py` (`collect`, run with each build's own python or in the Linux image: per family and
  configuration two fresh processes, pickled `yldot`/`yldot_J` and index arrays with the build record; `--omp N` adds
  the `ffun` RHS with the `ppp` OpenMP flags set in the `post` hook; `analyze`: the pairs `same_build:<label>`,
  `o0_vs_o3`, `mac_vs_linux` (serial, they feed σ and rtol), `debug_vs_o3` and the OpenMP rows (report only), the
  floor report, the AIUE-81 re-check; `--write` writes the files below; exit 4 = a nonzero same-build spread, 3 = owner);
  `make_references.py` (`generate --from-commit SHA`: builds SHA `--serial` and writes each family's steady and
  `timestep` defaults, Jacobian-flag difference, diagnostics and σ_i with the manifest's provenance; `--platform
  linux` (default) in the pinned image through `linux/generate.sh`, the only release-grade path, `--platform host` a
  temporary worktree and venv, a preview with `release: null` (owner, 2026-10-22, AIUE-88); default families: those
  with `sigma.h5`; refuses a `tests/yldot` that differs from SHA (references/ excepted), a `sigma.h5` that differs
  from `tolerances.toml` and a family whose manifest names other release assets; `--write` installs the files and
  manifests and opens each with `open_store`).
- **Tolerances** (PRD §7.4, §7.7; AIUE-87): `tests/yldot/tolerances.toml`, generated by `measure_roundoff.py analyze
  --write`: `k`, `rtol_eq` per equation (100 × the largest block-normalised spread over the serial pairs, floored at
  1e-14) with its source, the build records, the pairs, the raw spreads, the floor-report counts, the owner's answers
  and the findings; `families/<f>/sigma.h5` (`/<config>/sigma`, `/<config>/source` = the serial pair that set σ_i, -1
  where σ_i = 0). The Linux side is `tests/yldot/linux/` (Ubuntu 24.04 amd64 by digest, exact apt and pip pins;
  `collect.sh` builds a `git archive` of one commit; `generate.sh`, run from the mounted `tests/`, does the same for
  `make_references.py`). macOS `-O3` is the outlier the serial pairs measure.
- **Build flags** (PRD §8) `tests/yldot/tools/build_flags.py`: runs `setup.py` per option set on `linux` and `darwin`
  without building (Forthon's `FCompiler`, `setup()`, `os.system`, the `make` calls, `mppl2f90`, `check_output` and
  `build.run` stubbed; `argv` as pip passes `-C "--build-option=--<opt>"`) and records the `--fargs`/`--cargs` strings,
  `OMPFLAGS`, make's `LDFLAGS`, `OMP` and other changed environment variables, and the uedgeC link and compile
  arguments and macros; it needs setuptools, which a venv of Python >= 3.12 lacks until installed. Not covered: what
  reaches Forthon's real `FCompiler` and its own flags, `-g`/`-t`/`-F`, `--noclean`, `--parallel`, PETSc.
  `tests/yldot/test_build_flags.py` pins that table (27 cases: the default, `--serial`, `--debug`, `--checkbounds`,
  `--noopt`, `--coverage`, combinations, the two refusals, a preset `LDFLAGS`) to `v9-develop`'s, checks that
  `--coverage` changes only its own build, and edits a copy of `setup.py` seven ways to show each is caught. An
  intended flag change updates its `EXPECTED`, with the reason in the PR.
- **Tests** (the whole suite: 308 tests, 3 of them the owner families' `test_history` skips, in about 300 s, serial
  build, Darwin arm64, 2026-10-22, AIUE-88; about 250 s of that
  are the three owner families' `test_states`, `test_index_truth` and `test_history` runs):
  `tests/yldot/test_smoke.py` the smoke test, `tests/yldot/test_compare_unit.py` the
  comparator's unit tests, `tests/yldot/test_inventory.py` index truth per family, `tests/yldot/test_inputs.py` the
  input inventory, overrides and value rules, `tests/yldot/test_variant_apply.py` variant application and replay,
  `tests/yldot/test_states.py` both states of every family are round-trip fixed points, `tests/yldot/test_history.py`
  `measure_history.py check` per family (about 3 s each) and the measured families' `[evaluation]` keys,
  `tests/yldot/test_store_unit.py` the store, manifest, `fetch_data.py` and `release_data.py` (sketch known-answer
  vector; fakes for `gh` and `git`),
  `tests/yldot/test_build_flags.py` the build options' flags (about 2 s, no build),
  `tests/yldot/test_roundoff_unit.py` `measure_roundoff.py analyze` on synthetic collections,
  `tests/yldot/test_make_references_unit.py` `make_references.py` (its child on `d_only` twice, the same bytes; its
  refusals and the git/docker commands with fakes; the manifests that hold data),
  `tests/yldot/test_tolerances.py` `tolerances.toml` against `sigma.h5` and a live evaluation per family.

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

## Fast iteration: subset while working, full matrix once

Builds and test matrices were the longest waits of epic AIUE-8 (one ticket 5.7 h, a cost study 2.1 h). While working:

- **Iterate on a subset**: one case (the reproducer preset or the one pytests case the change touches) at **two
  thread counts** (e.g. 1 and 4 for OpenMP work), and the one suite the change can affect.
- **Run the full matrix once**, at the end (`validate`, the serial bitwise check, the OpenMP flow), not after every
  edit. A failure there sends you back to the subset with the failing case added.
- **Prefer CI for heavy matrices**: push the branch and let `build-test-omp.yml` run its PR set (about 12 min on
  native `ubuntu-latest`) instead of an emulated or many-thread local matrix; quote its result.
- **Reuse builds**: one base venv per build kind (`--serial`, default OpenMP) per branch point, built once from a clean
  committed `origin/v9-develop` tree and shared by the tickets based on it (read-only: never reinstall into it); each
  ticket worktree keeps its own venv for its own build and rebuilds only when its sources changed. Name base venvs by
  their commit, `uedge-wt/venvs/base-{serial,omp}-<sha>`, so a stale one is visible; build a new pair when
  `v9-develop` moves past it.
- **Compared builds use one install mode.** Builds whose results or logs are compared (base vs ticket venvs, the
  serial bitwise check, a build-log diff) must differ only in the source tree:
  - the same interpreter: create the venv with the Python named in the base venv's `pyvenv.cfg` (`home`/`version`;
    pyenv 3.13.12 so far), not whatever `python` resolves to;
  - the same build dependencies, installed in the venv (`forthon`, `numpy`, `setuptools`, `h5py`, at the versions
    `pip list` shows in the base venv), and `pip install -v --no-build-isolation .` (plus `-C
    "--build-option=--serial"` for the serial kind). Without `--no-build-isolation`, pip builds in an isolated
    environment with unpinned Forthon, numpy and setuptools. Put the venv's `bin` first on `PATH` (activate it, or
    `export PATH=<venv>/bin:$PATH` in the build script) even when calling `<venv>/bin/pip` directly: the build runs
    `Forthon3` from `PATH` (`Makefile.Forthon:8`), and otherwise picks up another Python's (seen: a pyenv 3.14 shim,
    `No module named 'setuptools'`);
  - the same `CC` (and `CFLAGS`) as the base venv was built with. On macOS the OpenMP build needs an OpenMP-capable
    compiler: a libomp clang (`CC=$(brew --prefix llvm)/bin/clang`) or `CC=gcc-15 CFLAGS="-std=gnu17
    -Wno-error=incompatible-pointer-types"`, which built `base-omp-0480272`. Record the one used next to the base
    venv. The serial build has not needed a `CC` since AIUE-109 (62ac2b1).
- **Probing initialisation without a solve** (grid-change interpolation, `ueinit` checks): after the restore and the
  input changes, `bbb.ifexmain = 1; bbb.allocate(); bbb.ifexmain = 0; bbb.ueinit()`. A Python `allocate()`
  (`ifexmain = 0`) sets `nxold`/`nyold` to the current size, reallocates `Interp` and sets `isimesh = 1`
  (`bbb/odesetup.m:523-528`, AIUE-141). The next `ueinit` then copies the saved state as it is: a restore after the
  allocate is used for the current mesh, and the last `gridseq`'s old-mesh data are dropped. To interpolate after a
  same-mesh allocate (e.g. one made to set wall arrays), set `bbb.isimesh = 0` after it (owner, 2026-10-21). Without
  that, a mesh change with no restore stops with `variable nis=0, no saved solution for interp` (probed through
  `exmain`, nonog 8x4 → 16x8, AIUE-141; before AIUE-141 the recipe above stopped with `ERROR: ni <= 0`, d3dHsm
  8x4 → 16x8 in base-a8446eb-serial).
  Going through `exmain` instead runs the Newton solve (`itermx = 0` means nksol's default of 200 iterations,
  `svr/nksol.m:973`), and after a converged solve `gridseq` overwrites the `Interp` meshes.
- Raw outputs (logs, per-case tables, `.npz`/`.hdf5` dumps) go to `.claude/work/<KEY>/` or a scratch directory and
  are summarised on the ticket page; they are never committed.
- **The OpenMP flow's output directory**: `tests/deterministic_omp/ci/run_omp_ci.sh` writes `./omp-ci-out/` (ignored by
  `.gitignore`) and refuses to start if it exists. Set `OMP_CI_OUT` to a new path in `.claude/work/<KEY>/` for each run,
  e.g. one for the base and one for the ticket build.

### Bisecting old commits on macOS

Every commit before AIUE-109 (62ac2b1) passes `-fopenmp` to the C compiler, even with `--serial` (which `setup.py` has
had since d32c88b, 2025-01), so Apple clang fails the link. With `CC=gcc-15`, gcc 15's C23 default makes the pointer
assignments in `bbb/exmain.c:71,117` hard errors. Build each bisect step with

```bash
CC=gcc-15 CFLAGS="-std=gnu17 -Wno-error=incompatible-pointer-types" OMP_NUM_THREADS=1 \
    pip install -v --no-build-isolation .     # add -C "--build-option=--serial" from d32c88b on
```

(as a script file: the permission check refuses `VAR=… cmd` prefixes, `CLAUDE.md` → Gotchas). Mark a step whose build
fails `git bisect skip`; without these flags a whole range is skipped and the bisect stalls at "N revisions left".

## Suite structure (`pytests` branch)

```
pytests/fulltests/<case>/{input.py, conftest.py, test_<case>.py, gridue, *.h5 reference}
pytests/unittests/{D+C, D_mols, D_only, slab_D_only}/<case>/<variant>/{input.py, conftest.py, test_*.py, ...}
MakeTests.py              # regenerates whole test directories (re-perturbs every case)
tools/rereference.py      # origin/pytests only: regenerates one case's reference, keeping its stored state
V9_REFERENCE_CHANGES.md   # origin/pytests only: every reference that differs from LLNL's, and why
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
git fetch origin pytests
git worktree add --detach ../uedge-pytests origin/pytests   # an existing checkout: git -C ../uedge-pytests checkout --detach origin/pytests
cd ../uedge-pytests
pytest --isolate --tb=long pytests/unittests/D_only -s        # fastest
pytest --isolate --tb=long pytests/fulltests -s
```

Pick the suite that exercises your change (impurities → `D+C`, molecules → `D_mols`, slab geometry →
`slab_D_only`). Physics-neutral changes must pass **all** suites unchanged. On LLNL's `upstream/pytests` the cases
listed in `V9_REFERENCE_CHANGES.md` fail for v9 by design; don't use it for v9 work.

## Known failures on `v9-develop`

`validate` marks a failure listed here ⚠️ pre-existing without a base re-run; anything else is the change's until a
base run shows otherwise. Remove an entry when its fix merges. Before scoping a ticket about a failing test, run
**every** suite on a base venv of the branch point and record here what is red there.

Last full run: all suites on a serial build of the AIUE-132 change (same-mesh restart copies, on `v9-develop` c82a515)
against `origin/pytests` f695acd (2026-10-21): 157 passed (D_only 125, D+C 1, D_mols 27, slab_D_only 1, fulltests 3).
- **Failures:** none.
- **Passes with a warning:** none. The D_only `nonog/icnucx` warning seen before ("Fnrms outside of tolerances, but
  similar") came from the second exmain interpolating onto the same mesh, fixed by AIUE-132.

## When results change intentionally

New physics should be off by default, so references stay valid. If a reference must change (a bug fix, or an owner
decision on a physics default), regenerate that case with `tools/rereference.py <case dir>` on `origin/pytests`, in a
separate PR to that branch, add the case to `V9_REFERENCE_CHANGES.md` (old and new `fnrm`, the change that moved it,
who decided it), and explain the diff in the main PR. Not `MakeTests.py`: it rebuilds the whole directory and
re-perturbs every case with unseeded random numbers, so every reference in it would move.

## CI facts / quirks

- `build-test-wheel.yml` builds with `--serial`, Python 3.11, `numpy==1.26.4`; it does not exercise OpenMP.
- `.github/workflows/build-test-omp.yml` (AIUE-57) tests the OpenMP paths: it builds the default OpenMP build
  (`pip install -v .`, Python 3.11, `numpy==1.26.4`; no `LDFLAGS` since AIUE-64) and runs
  `tests/deterministic_omp/ci/run_omp_ci.sh`: harness and CI unit tests, a smoke test, the common-block check
  (`tests/deterministic_omp/ci/common_check.py`), the OpenMP test flow, the C1 bound
  (`tests/deterministic_omp/ci/jac_bound.py`) and `tests/deterministic_omp/ci/report.py`
  (`tests/deterministic_omp/README.md`, "CI"). Triggers: `pull_request`, `push` to `v9-develop`/`main` only, and a
  nightly `schedule` (default branch only). PR set: `tebox1` (2, 4 threads, K=3, `jac`, one evaluation),
  `tebox` (2, 4 threads, K=5, both arms, `--itermx 3`), both Te-box flows with `OMPJacMinChunkLen=1` (25 chunks),
  `up1` (4 threads, K=3, `jac`, one evaluation) and `full` (2, 4 threads, K=2, `jac`, `--itermx 3`); nightly:
  `--all` one evaluation K=2, Te box 25 chunks at 2/4/8 threads, and `--all` `--itermx 3` K=3. Gate: the `jac` arm,
  bitwise, plus the C1 bound on the scaled `post_exmain` Jacobian and the common-block check; `jacrhs` is
  report-only (epic AIUE-70). `OMP_CI_JAC_TOLERANCE` (≤ 1e-6, empty in the workflow) is a tolerance mode for macOS
  replays. Merges with or after `bugfix/v9-openmp-determinism-fix`, once its first native PR run is green within
  20 min. Same steps locally: `PYTHON=<omp venv python> tests/deterministic_omp/ci/run_omp_ci.sh pr`; in the Ubuntu
  image: `tests/deterministic_omp/linux/run_ci_replay.sh`.
- In `build-test-wheel.yml` the "Install pip dependencies" step runs `pip install forthon>=0.10.7 ...` unquoted: the
  shell redirects to a file named `=0.10.7`, so Forthon is installed unpinned. (`build-test-omp.yml` quotes it.)
- Non-`master` branches check out `pytests-develop`, which upstream does not have (only `pytests`) → test step fails on checkout.
- `@notest`/`@nowheel` commit tags are inert (no job `outputs:` on `check-requests`; `wheel` vs `wheels` mismatch).
- `build-basis.yml` runs BASIS level-1/level-2 tests in Docker (`fusionbillm/basisuedge`); skip with `#@nobasis`.
- `claude-review.yml` runs `/code-review` on PR open or `@claude-review` comment.
