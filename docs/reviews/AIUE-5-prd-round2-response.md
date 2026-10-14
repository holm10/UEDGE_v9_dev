# Response to review round 2: AIUE-5 PRD

PRD revision 4: `docs/prds/AIUE-5-switch-to-pure-fortran-build.md` on `feature/v9-AIUE-5-planning`.

## Owner decision taken because of this review (binding)

| Finding | Decision (epic owner, 2026-10-14) |
|---|---|
| P2-B1 / P2-M1 | Remove `bbb.petscoptfile` **and** `bbb.petscopts`. Make `hdf5_restore_dump` tolerant: it skips datasets for variables that no longer exist, prints a warning listing them, and gets a test that restores a pre-AIUE-5 full dump |

## Findings

| ID | Status | Where in rev. 4 |
|---|---|---|
| P2-B1 | Fixed by the owner's decision: tolerant restore plus an old-dump test. §10 corrected (HDF5 full dumps *do* contain both variables). New risk row: a partial restore hidden by the tolerance | Decisions, §4, §10, §11, §14 |
| P2-M1 | Fixed. `petscopts` (`bbb/bbb.v:158`, `petsc-uedge.F90:174`, `bas2py_rules.py:110`) is removed alongside `petscoptfile`. Deck incompatibility now names both | Decisions, §4, §7.4, §10 |
| P2-M2 | Fixed. The criterion is now a defined `git grep` scan against a reviewed allow-list (`tools/petsc_allowlist.txt`). The `svrpkg='petsc'` branches and `uedge_petsc*`/`outputstatspetsc` stubs are explicitly kept (out of scope, later cleanup) | §4, §11 |
| P2-M3 | Fixed. A minimal CI change is in scope: `build-test-wheel.yml` uses `pytests` for all branches, the grid directory is added to the matrix, and the case lands by PR on the LLNL/UEDGE `pytests` branch. The BASIS CI is deleted only once the case is green there | §4, §12 |
| P2-M4 | Fixed. Phase 0 removes only PETSc/PACT **build** paths. The converter's `Petsc`/`Nopdb` classes stay until the converter is deleted in the last Phase 1 PR. `mppl_freeze.py` carries a verbatim, hash-checked converter copy with `OMP`/`PETSC_DIR`/`PACT_DIR`/`PARALLEL` pinned | §4, §7.4, §12 |
| P2-M5 | Fixed. Prerequisite: the AI layer (drift tooling, `physics-models.md`) is merged into `v9-develop` before Phase 0. The process ticket moves to Phase 0 and strips code facts out of skills and agents into context modules, with neutral wording; rca, validate, prime and init-project are added. Freeze PRs then touch only `CLAUDE.md`/`.claude/context/`, and the drift check can be clean at every freeze PR | §4, §12 |
| P2-m1 | Fixed. `get_packages.py` `:159/:266/:466` filters, `:164/:521/:574` splits on `!`, `:484` keeps `#` | §4 |
| P2-m2 | Fixed. No `!*.F`; explicit in-tree build-output patterns instead, verified on macOS and Linux after a build | §4 |
| P2-m3 | Fixed. `.git-blame-ignore-revs` updated in a follow-up commit after each rebase-merge | §4 |
| P2-m4 | Fixed. `ParallelMatfac=1` added. Non-determinism fallback: pin `OMP_SCHEDULE=static` and chunking, else escalate to the owner; never loosen | §7.5 |
| P2-m5 | Fixed. One definition: following-code anchor | §6.3, §7.3 |
| P2-m6 | Fixed. Sentinel lines are compared as code, and the gate fails if a sentinel appears on one side only | §7.2 |
| P2-m7 | Fixed. "Phase 2"; `*/pck` (9) added; PACT block `setup.py:111-117` | §7.4 |
| P2-m8 | Fixed. The serial `c!omp` comment copies (the `#ifndef` side) are not kept; their content is the `#ifdef _OPENMP` code | §6.2 |
| P2-m9 | Fixed. `com/error.f` and `bbb/exmain.c` are covered by preprocessing-equivalence | §7.2 |
| P2-m10 | Fixed. "raises an error (Forthon's `bbbpy.error`)" | §10 |

Estimate updated: Phase 0 ~2 weeks, total ~4.5 weeks.

## Revision 5 (owner decision after revision 4)

The target is now **free-form `.F90`**. Only the 50 MPPL-derived files are converted; the hand-written `.f` files stay fixed form.

- **Two-stage conversion:** stage 1 builds the fixed-form reference exactly as revision 4 did (unmodified converter, `diff -D _OPENMP` merge, comment pass). Stage 2 converts it to free form.
- **Gate 1:** now compares gfortran parse trees across the two forms, with a token-comparison fallback.
- **Comment gate:** compares `.m` with `.F90` directly.
- **Simplifications:**
  - the `.gitignore` problem from P2-m2 and P1-M8 disappears, because `*.f`/`*.F` don't match `*.F90`;
  - the `clean` target never matched `.F90`.
- **Still apply unchanged:** all other round-2 resolutions.
- **Estimate:** ~6 weeks.
- **Round 3:** a delta review of revision 4 was stopped before reporting, because revision 5 supersedes it.
