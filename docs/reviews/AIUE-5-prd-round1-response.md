# Response to review round 1: AIUE-5 PRD

PRD revision 2: `docs/prds/AIUE-5-switch-to-pure-fortran-build.md` on `feature/v9-AIUE-5-planning`.

## Owner decisions taken because of this review (binding)

| Finding | Decision (epic owner, 2026-10-14) |
|---|---|
| P1-C1 comments | No comment **information** may be lost. Byte-identical layout is not required: the marker may change, and comments may move within their routine. Text the converter would alter is restored. Information that ends up in another form goes on a reviewed exception list |
| P1-M2/M3/M4 "bit-identical" | Same compiled code (identical preprocessed token stream in every configuration) **and** same numbers (exact `fnrm` and residual hashes before vs after, same machine; OpenMP at fixed threads). No object-file comparison |
| P1-M5/M6 BASIS | Remove BASIS completely per an explicit inventory. Add a grid-generation regression first |
| P1-M7 uncompiled files | Delete both `bbb/s.m` and `flx/dvshdf5.m` (`s.m` has 2 unique comments out of 358, both commented-out code) |

## Findings

| ID | Status | Where in rev. 2 |
|---|---|---|
| P1-C1 | Fixed. The comment requirement is redefined by the owner. The comment pass restores text and position. Exact exception list (`do_i1` ×4, `ruthere` ×2, conditional payloads). The check fails on unlisted differences and on listed exceptions that didn't occur | Decisions table, §6.3, §7.3 |
| P1-M1 | Fixed. The unmodified converter runs per configuration with fresh state, then a `diff -D` merge. A per-configuration round-trip check. Gate 1 covers serial, OpenMP, PETSc, PETSc+`PARALLEL` and PACT | §6.2, §7.2 |
| P1-M2 | Fixed. The object-code claim is dropped. A string-preserving normaliser. No object comparison (owner decision) | §7.2 |
| P1-M3 | Fixed. `numeric_baseline.py` uses `float.hex(fnrm)` + SHA-256(`yldot`) per case and switch cycle on a named machine. Negative controls for every tool. The reference is the parent commit, not a self-comparison | §7.2, §7.3, §7.5, §12 Phase 0 |
| P1-M4 | Fixed. One standard: bit-identical at fixed `Nthreads=4` on a named X-point case with the parallel switches on, after a determinism check | §7.5, §9 |
| P1-M5 | Fixed. A `gengrid=1` case from `builder/test/Forthon_cases/Forthon_case2` lands on `pytests` first. `build-basis.yml` is deleted only after it's green | §7.4, §7.5, §12 |
| P1-M6 | Fixed. Full keep/delete/move inventory, plus a scan script before Phase 2 | §7.4 |
| P1-M7 | Fixed. Both files are deleted in a labelled commit; counts are now 50 frozen + 2 deleted | Decisions, §4, §8, §11 |
| P1-M8 | Fixed. `!*.F` plus `git check-ignore` on both OSes. The cleanliness criterion uses `--ignored` | §4, §11, §14 |
| P1-M9 | Fixed. Ordering: the build-prerequisite PR (`clean`, `.gitignore`) lands first. Three commits per package PR (stale `.F` removal + rename, freeze, code-facts). Rebase-merge. `.git-blame-ignore-revs`. Bisect-skip note | §4, §12 |
| P1-M10 | Fixed. The freeze tool is permanent, with a `backport` mode. Procedure in `doc/workflow.md`. Risk owner. Agreed with the v8 maintainers in Phase 0 | §7.1, §7.6, §14 |
| P1-M11 | Fixed. Code-facts updates ship in each freeze PR (`CLAUDE.md` hard rule in the first PR; drift check clean per PR). Skills and agents form one `feature/v9-ai-*` ticket merged right after the first freeze PR, because the branch policy forbids skill edits on ticket branches. `get_packages.py` and `README-FORTHON` are in scope | §4, §7.7, §12 |
| P1-M12 | Fixed. The lexer requirements list every construct named (tabs, continued strings, `!` in code and strings, Hollerith, `c!` comments, `cpetsc*`, case). The record now includes kind, marker and anchor. Independent count cross-check | §6.3, §7.3 |
| P1-m1 | Fixed. Counts are recomputed by the tool; the round-1 figures are quoted. Makefile refs `:51`/`:71`. `grdproc`, `do_i1` and `, allot` included. The two nonexistent "latent bugs" are removed | §4, §8 |
| P1-m2 | Fixed. PETSc and PACT are explicit opt-in build options. `PARALLEL` is defined by the option. Release note | §4, §10 |
| P1-m3 | Fixed. `-fopenmp`, with the exact Forthon flags taken from the build log | §7.2 |
| P1-m4 | Fixed. Reference = parent commit of each freeze. `.m` code-freeze window | §7.2, §10, §14 |
| P1-m5 | Fixed. Fresh rule state per file is required | §6.2, §7.1 |
| P1-m6 | Fixed. The PRD has moved to `feature/v9-AIUE-5-planning`; the review is saved as `…-prd-round1.md`. Estimate raised to ~4 weeks. The unverifiable "tested with" claim is removed | — |
| P1-m7 | Fixed. `nclpydep` `touch $@` and `compydep` prerequisite | §4 |

## Revision 3 (owner decision after revision 2)

Only the serial and OpenMP builds are kept. PETSc and PACT are removed completely. Effects:
- **P1-M1 and P1-m2 are moot for PETSc/PACT.** There is one merge (`diff -D _OPENMP`), and gate 1 checks two configurations.
- **PETSc lines:** the `cpetsc`/`cunipetsc` lines (inactive in today's builds) are deleted, along with their 15 PETSc-only comment lines, as an owner-approved exception class.
- **PACT stubs:** the `c!nopdb` stubs (active in today's builds) become plain code.
- **Deck compatibility:** `bbb.petscoptfile` stays as a deprecated no-op.
- **Revision 3 follow-up (owner):** `bbb.petscoptfile` is removed rather than kept as a no-op. It's used only in `svr/petsc-uedge.F90` and the `bas2py` mapping. A deck that sets it now raises an error; this is the single documented exception to deck compatibility. All 15 PETSc-only comment lines are removed with PETSc.
