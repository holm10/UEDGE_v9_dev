# Fix the non-deterministic OpenMP Jacobian (epic AIUE-8)

**Branch:** `bugfix/v9-openmp-determinism-fix` → `v9-develop`. It combines the AIUE-8 tickets AIUE-46, 47, 49, 50, 52,
53, 54, 55, 56, 57, 58, 60, 61, 62 and 64. Each one was reviewed and approved on its own ticket branch, then merged
here with `--no-ff`.

## Summary

The default OpenMP build gave a different Jacobian on every run: it differed from serial and from run to run. In the
owner's reproducer, the Te rows were corrupted by up to 1e43. This branch finds the causes, fixes them, makes the
OpenMP Jacobian reproducible, and adds tests and a CI job so the problem cannot come back unseen.

- **Root cause C1, fixed (AIUE-56).**
  - `OMPJacBuilder` copied the master's `+threadprivate` arrays to the workers before their scalar bounds.
  - Forthon's `OmpCopyPointer<var>` copies the section `(1:n)` using the worker's own copy of `n`. For the 12 `api`
    `Imslwrk` spline arrays that bound is threadprivate, so on the first Jacobian of a session the workers copied
    one element and kept zeros.
  - The `isimpon=7` impurity radiation then evaluated empty tables in the Te residual.
  - Fix: the scalars are now copied first (`ppp/omp_parallel.F90`).
- **Remaining races, fixed (AIUE-60).**
  - `+threadprivate` added to per-call state written inside `pandf`: `areapl`, `TimingPandfOn`, `com.nfsp`, the `com`
    timers, `emcoef` no longer in `copyin`, the `fmombal` SAVE arrays, and the limiter and spline scratch.
  - Clip index fixed: the parallel Jacobian clipped with `sfscal` of the column; it now uses the row, as serial does
    (`ppp/parallel.F90`).
  - The Forthon `--omp` common block `/ompcommonscalarcopy/` invariant (bbb first and largest) is now documented and
    checked (`openmp-jacobian.md`; `tests/deterministic_omp/ci/common_check.py`).
- **Deterministic Jacobian, the new OpenMP default (AIUE-61, decision 9 = option F, owner-approved).**
  - The columns are split into fixed contiguous chunks: `NchunksJac = min(OMPJacNchunksFixed, max(1,
    neq/OMPJacMinChunkLen))`, defaults 64 and 300. Every chunk starts from a fresh full `pandf`.
  - The OpenMP Jacobian is therefore reproducible and the same for any thread count.
  - On (emulated) Linux x86-64 it is bitwise equal to serial. On macOS arm64 a round-off difference remains (C2; see
    Limitations).
  - The old partition is still available with `OMPJacFixedChunks=0`.
- **Linux OpenMP link (AIUE-64).**
  - On Ubuntu 24.04 and Debian 12 the default OpenMP build did not import: `undefined symbol: GOMP_parallel`.
  - `setup.py` now links the Forthon extensions with `-fopenmp` on Linux. No `LDFLAGS` is needed.
- **Raw-Jacobian capture hook (AIUE-47).** Off by default (`bbb.jaccapture=0`). It records the raw finite-difference
  Jacobians of `jac_calc` and `jac_calc_parallel` for the harness.
- **Test tooling** (`tests/deterministic_omp/`):
  - the reproducer case (AIUE-46);
  - a fresh-process bitwise harness with localisation to equation and cell (AIUE-49);
  - the test flow with per-arm verdicts (AIUE-52);
  - the serial old-vs-new bitwise check (AIUE-53);
  - shared-state and OmpCopy scanners (AIUE-50);
  - Linux Docker tooling (AIUE-62).
- **CI job `.github/workflows/build-test-omp.yml` (AIUE-57).**
  - It builds the default OpenMP build on `ubuntu-latest` and runs `tests/deterministic_omp/ci/run_omp_ci.sh`.
  - The Jacobian arm gates bitwise against serial, with the AIUE-56 C1 bound on the scaled `post_exmain` Jacobian as a
    backstop and the common-block check.
  - The parallel-RHS arm is report-only.
  - Triggers: pull request, push to `v9-develop`/`main`, nightly, manual.
- **RCA and characterisation:** `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` and its data (AIUE-54, 55, 58, 62).

## Defaults that changed

- **The OpenMP Jacobian partition (owner-approved, AIUE-61).**
  - `OMPJacFixedChunks=1` is the new default; the old dynamic one-column chunks are `OMPJacFixedChunks=0`.
  - OpenMP Jacobians and OpenMP runs give different (now reproducible) numbers from before.
  - New `ppp` variables: `OMPJacFixedChunks`, `OMPJacNchunksFixed`, `OMPJacMinChunkLen`, `OMPJacChunkReset`.
- **Serial results are bitwise unchanged.**
  - This covers both the `--serial` build and the OpenMP build with `OMPParallelJac = OMPParallelPandf1 = 0`.
  - Evidence: AIUE-53 serial check against `v9-develop`, 42 cases including Newton iterations, both pairs.
- No input or save-file change.

## Known costs and limitations

- **Cost on small and mid-size problems.**
  - A fixed chunk costs one full `pandf`, and small problems get few chunks.
  - Problems up to about neq 5 000 at 8 threads may build the Jacobian up to about 2× slower than
    `OMPJacFixedChunks=0`. Below neq 600 there is a single chunk and the build is about 3× slower (D_only default case:
    0.047 s against 0.016 s per Jacobian).
  - Knobs: a smaller `OMPJacMinChunkLen`, or `OMPJacFixedChunks=0`.
  - The full problem (neq 44 352, 64 chunks) is within about 1–3 % of before (AIUE-61 G7).
  - Tuning is AIUE-73.
- **The parallel RHS (`OMPParallelPandf1=1`) is not fixed by this branch.** It is report-only in CI.
  - Known defects: AIUE-58 R1–R4, and AIUE-74, an out-of-bounds write in `MakeXptChunks` on small grids (heap
    corruption, random SIGTRAP/SIGSEGV).
  - All of it is epic AIUE-70. Do not rely on `OMPParallelPandf1=1`.
- **macOS arm64 (C2).** The OpenMP Jacobian is deterministic and thread-count independent there. It still differs from
  serial at round-off: full problem 12 275 Te-row entries, worst 4.59e-9 × row max; Te box with 25 chunks 2 entries,
  5.6e-10. That is well inside the C1 bound of 1e-6. Local macOS replays of the CI script use
  `OMP_CI_JAC_TOLERANCE=1e-6` (one-evaluation flows only).
- **D_only regression tests.** The `upstream/pytests` D_only references fail in some cases on both the base and this
  branch, identically per file (AIUE-61 G9a: OpenMP 121/4, serial 120/5). These failures already existed and come from
  stale references; the owner decided they are not a concern for this branch.
- **Linux evidence is emulated.** All Linux runs used Rosetta-emulated x86-64 in Docker; native hardware has not been
  run.
- **The nightly CI set is not validated on Linux yet.** Bitwise equality was shown for the Te box, `full` and `up` only,
  so a red first nightly is not necessarily a regression. The owner decides; running `workflow_dispatch` with
  `set: nightly` right after the merge answers the question early.

## Validation (records on this branch)

- Merge validation: `docs/reviews/omp-determinism-merge-validation.txt`. It covers:
  - builds and warning counts (unchanged against base);
  - the AIUE-53 serial check: AGREE, 42 cases, complete gate;
  - unit tests;
  - full-problem determinism, Jacobian hash `8761cd9e36658ee1`, and 2/4/8-thread identity;
  - C1 bound on the scaled matrix;
  - common-block and `/iotable/` checks;
  - capture hook;
  - after AIUE-57, the CI replay in Ubuntu 24.04: `OMP CI RESULT: PASS`.
- Per-ticket validation: `docs/reviews/AIUE-<N>-validation.txt`, and the review reports and responses in
  `docs/reviews/AIUE-<N>-*`.
- CI job:
  - `docs/reviews/AIUE-57-validation.txt` §9: replay PASS, pre-fix negative control FAIL, seeded race FAIL,
    tolerance-mode controls;
  - reviews `docs/reviews/AIUE-57-rework-*`.
- RCA: `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`.

## Merge condition

- **The first native `ubuntu-latest` run of `build-test-omp.yml` on this PR must be green and inside the 20-minute
  budget.**
  - If it is over budget, cut the `pr` set in this order: drop `up1`, then Te box K 5 → 3, then `full` at 4 threads only.
  - If native x86-64 shows round-off differences like C2, the owner decides; the tolerance mode cannot rescue the
    `--itermx` flows.
- Copy the job's measured wall time and verdict into this description.

## Follow-ups (not in this PR)

- AIUE-65 / AIUE-66 (epic): the Linux-only mismatch in `up` rows next to the inner plate (M3). It is absent with the
  fixed partition; the investigation remains open.
- AIUE-68: remove the `isjacreset` extra `pandf` evaluation in the OpenMP Jacobian, or make it optional.
- AIUE-69: OpenMP safety on non-default paths: double-null X-point, coupled wall sources, `isimpon=5`, and the PETSc
  clip index.
- AIUE-70 (epic): correctness of the parallel RHS (`OMPParallelPandf1`).
- AIUE-71: Forthon `--omp`: the `/ompcommonscalarcopy/` block shared across packages, and the `ProcessDim`
  nested-parenthesis bug (upstream).
- AIUE-73: tune `OMPJacMinChunkLen` for mid-size problems.
- AIUE-74: parallel RHS out-of-bounds write in `MakeXptChunks` on small grids.
- AIUE-75: the serial `pandf` reads `ng(ix,iy,2)` with only one gas species (out of bounds in
  `pandf_plasma_energy`).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
