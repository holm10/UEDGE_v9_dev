# Review: AIUE-5 PRD "Switch to pure Fortran build" (stage: prd, round 2)

- **PRD:** `docs/prds/AIUE-5-switch-to-pure-fortran-build.md`, revision 3 (worktree `uedge-wt/AIUE-5`, branch `feature/v9-AIUE-5-planning` @ 4e531df, PRD untracked)
- **Inputs:** round-1 review `docs/reviews/AIUE-5-prd-round1.md`; response `docs/reviews/AIUE-5-prd-round1-response.md`; two mid-review scope changes from the epic owner (serial + OpenMP only; PETSc and PACT removed; `bbb.petscoptfile` removed outright, the "single documented exception to deck compatibility"; all 15 PETSc-only comment lines go with PETSc). Revision 3 contains both changes and is what I reviewed.
- **Binding decisions checked against:** retire MPPL and BASIS, keep `.v` + Forthon; unchanged results = identical preprocessed token stream (serial, OpenMP) and exact `fnrm`/residuals; no comment information lost (marker `#`→`!` and within-routine moves allowed, exact exception list); `pip`/wheels, OpenMP parity, input decks and HDF5 save files keep working; delete `bbb/s.m` and `flx/dvshdf5.m`; BASIS removal per inventory with a `gengrid=1` regression first; branch policy in `.claude/context/branching.md`.

## Verdict

**REVISE**

## Summary

Revision 3 fixes the core design problems from round 1. I re-ran the unmodified converter, and the serial/OpenMP `diff -D _OPENMP` merge round-trips under `gfortran -E` token-for-token for all three affected files. Deleting the 141 `cpetsc`/`cunipetsc` lines before conversion leaves the serial and OpenMP code unchanged. Of the 20 round-1 findings, 17 are resolved, 2 are partially resolved and 1 is moot.

The PETSc removal added in revision 3 rests on a false premise, though. `hdf5_dump` writes every package variable, `bbb/petscoptfile` included. I reproduced that `hdf5_restore_dump` aborts on any dataset whose variable no longer exists. So removing the variable breaks existing full-dump save files, which contradicts the HDF5 hard constraint. Five MAJOR problems remain:
- the sibling `petscopts` variable is not covered;
- the "no tracked file references PETSc or PACT" criterion can't be met without changing code tokens or deleting comments;
- the grid-generation case can't go "green in CI", because CI checks out a branch that doesn't exist;
- Phase 0 edits the live converter that Phase 1 and gate 1 still depend on;
- the per-PR drift-check criterion conflicts with the branch policy for skills that cite `bbb/*.m`.

## Findings

### Blocker

**P2-B1. Removing `bbb.petscoptfile` breaks existing HDF5 full-dump files. The PRD's claim that "HDF5 saves never contained `petscoptfile`" is false.**
*Location:* §10 "Python API / save files: unchanged. HDF5 saves never contained `petscoptfile`"; decisions table "Hard constraints … Sole exception"; §4 "Remove PETSc"; §7.4 PETSc row.
*Evidence:*
- `src/uedge/hdf5.py:188-224`, `hdf5_dump(file, packages=list_packages(objects=1), vars=None)`: writes **every** variable of every package (`list_package_variables` → `package.varlist()`, `src/uedge/uedge_lists.py:29-47`).
- `src/uedge/hdf5.py:263-320`, `hdf5_restore_dump` (its docstring calls it "the recommended way to restore"):
  - calls `pck.getpyobject(vt[2])` for every dataset;
  - on any exception it prints and **re-raises** (`:317-320`).
- Reproduced with the installed build (its `hdf5_dump`/`hdf5_restore_dump` code is identical to this worktree), script `h5test.py`:
  - `hdf5_dump(fn, packages=[bbb], vars=['petscoptfile','petscopts','ngrid'])` writes the datasets `['ngrid', 'petscoptfile', 'petscopts']`;
  - after adding one dataset for a variable that doesn't exist, `hdf5_restore_dump` fails with `AttributeError 'Forthon' object has no attribute 'removed_var_xyz'` ("Couldn't read hdf5 file").
- So every existing full dump becomes unreadable once `petscoptfile` is removed. `hdf5_save`/`hdf5_restore` (the `savedata` group) are not affected.

*Note for the epic owner:* the PRD defect is the false claim. Underneath it, the decision to remove `petscoptfile` conflicts with your hard constraint "HDF5 save files keep working". That conflict is yours to resolve, not the author's.
*Acceptance:* the PRD states the real effect on `hdf5_dump` files and picks one of these:
- (a) keep `petscoptfile` (and `petscopts`, see P2-M1) as deprecated no-op variables, which was the owner's first instruction; or
- (b) bring a `hdf5_restore_dump` change into scope that skips unknown datasets with a warning, and list it as a deliberate Python-layer behaviour change. This must include a test that restores a pre-AIUE-5 full dump.

### Major

**P2-M1. `bbb.petscopts` is in exactly the same position as `petscoptfile`, and the PRD doesn't mention it.**
*Location:* §4 "Remove PETSc"; §7.4; §10; decisions table ("sole exception").
*Evidence:*
- `bbb/bbb.v:158`: `petscopts character*2048 /""/ +input`.
- Its only Fortran use is `svr/petsc-uedge.F90:174-175`, which is deleted.
- It is mapped at `pyscripts/bas2py_rules.py:110`. It is also written by `hdf5_dump` (reproduced, see P2-B1).
- If it stays, it is a dead PETSc input and violates the §11 "no PETSc references" criterion. If it goes, it is a second deck incompatibility, which contradicts "sole exception".

*Acceptance:* the PRD states the fate of `petscopts` (and `bas2py_rules.py:110`) consistently with P2-B1. It also states the decks/save-file exception list exactly.

**P2-M2. The success criterion "No tracked file references PETSc or PACT, apart from the release notes" (§11) can't be met without breaking decisions 2 and 3.**
*Location:* §11 functional requirements; §1 "PETSc and PACT support is removed".
*Evidence:* `git grep -i petsc` / `pact`, excluding the `cpetsc` lines, finds:
- **Active code** (removing it changes the token stream, which decision 2 forbids):
  - `svrpkg.eq.'petsc'` branches at `bbb/pandf.m:378,739`, `bbb/oderhs.m:1171,2713`, `bbb/odesetup.m:72,348,422,973,6823,6828`, `bbb/odesolve.m:298`, `ppp/omp_parallel.F90:1124,1305`;
  - the stub subroutines `uedge_petscInsertOpts`/`uedge_petscFinal`/`uedge_petscInit` (`bbb/odesetup.m:6849,6859,7497`);
  - the `outputstatspetsc` dummy, whose string is "I am in outputstats in a nopetsc build" (`bbb/odesolve.m:1679`);
  - the `pfread`/`pfopen`/... PDB stubs that the PRD itself keeps.
- **Ordinary comments.** Decision 3 forbids deleting these, and the exception class covers only `cpetsc`/`cunipetsc` lines:
  - `bbb/oderhs.m:4621`;
  - `bbb/odesetup.m:6290,6850,6861`;
  - `bbb/odesolve.m:342,1662-1667`;
  - `bbb/ext_neutrals.m:2602-2605` ("compiled if environment variable PACT_DIR is not defined");
  - `bbb/convert.m:192`/`odesetup.m:3712…` (the `mpivarsmod.F.in` notes).
- **Other files:**
  - `bbb/bbb.v:157-158,4083-4090`;
  - `com/mpivarsmod.F.in:5`;
  - `README.md:46-47`;
  - `README-FORTHON`;
  - `doc/manual/ue_man.tex:314-331`;
  - `*/pck` (`$Pact/bin/pact`);
  - `MANIFEST:11-12`;
  - `pyscripts/bas2py_rules.py:109-110`;
  - `.claude/context/mppl-fortran.md:37`, `.claude/agents/uedge-{implementer,reviewer}.md`.

*Acceptance:* replace the criterion with a defined scan, for example `git grep -il 'petsc\|pact_dir\|HAVE_PACT'`, with an explicit reviewed allow-list:
- code kept for token identity;
- comments kept per decision 3;
- docs to rewrite.

Alternatively, get an owner decision that widens the removal, stated as a token-stream change with its own justification.

**P2-M3. The grid-generation regression cannot go "green in CI", so the precondition for deleting `build-basis.yml` can't be met as written. P1-M5 is therefore only partially resolved.**
*Location:* §7.4 last row; §7.5 "Grid generation"; §11 "`build-basis.yml` was removed only after the grid case was green"; §12 Phase 2; §4 out of scope ("Fixing CI quirks … the `pytests-develop` checkout").
*Evidence:*
- `.github/workflows/build-test-wheel.yml:58-66`:
  - selects `testbranch=pytests` only when the branch name contains `master`, and `pytests-develop` otherwise;
  - checks it out from `repository: LLNL/UEDGE` (`:88-92`).
- `git ls-remote --heads upstream` (llnl/UEDGE) lists `pytests`, `stale/pytests` and `v9-*`, but **no `pytests-develop`**. So on every `feature/v9-*`/`v9-develop` run the test job checks out a branch that doesn't exist.
- The matrix is a fixed list of directories (`:51`), so a new case runs only if it sits in one of them.
- The PRD says the case lands "on the `pytests` branch" without naming the repository. The fork's own `pytests` branch is never checked out by CI.
- The BASIS level-2 coverage would therefore be replaced by a test that no CI job runs. That defeats decision 6.

*Acceptance:*
- Bring the minimal workflow change into scope: test-branch selection for v9 branches, and a matrix entry or location for the grid case.
- Name the repository and branch that receive the case.
- Or redefine the precondition explicitly, e.g. a named local run recorded in the PR, and accept the CI coverage gap as an owner decision.

**P2-M4. Phase 0 edits the live converter that Phase 1 and gate 1 still depend on. The permanent freeze tool's converter isn't pinned.**
*Location:* §12 Phase 0, "Build-prerequisite PR: … PETSc and PACT build paths removed (… `setup.py` blocks …)"; §4 "the PETSc blocks in `setup.py` (`setup.py:41`, `setup.py:198-207`, …)"; §7.2 reference = "converter output from the **parent commit of the freeze**"; §7.1/§7.6 (tool kept permanently for backports).
*Evidence:*
- `setup.py:198-207` is `class Petsc`, part of the converter, and it is still instantiated at `setup.py:655` (`Petsc(),`). Deleting the block as listed leaves a `NameError` in every build until the last Phase 1 PR.
- Read loosely, "PACT build paths removed" also covers `class Nopdb` (`setup.py:190-196`, instantiated at `:654`). Nopdb is what activates the 28 `c!nopdb` stubs. Removing it makes them comments again (missing `pfread`/`pfopen`/`pfwrta`/`pfclos`).
- Gate 1 would **not** see that, because its reference is produced by the same modified parent-commit converter.
- Separately, `tools/mppl_freeze.py` must outlive `setup.py`'s converter for v8 backports. The PRD never says it carries a verbatim, version-pinned copy, or that it forces `OMP`/`PETSC_DIR`/`PACT_DIR`/`PARALLEL`. An ambient `PETSC_DIR` on a maintainer's machine would silently activate the `cpetsc` lines in a backport.

*Acceptance:* the PRD states that:
- `setup.py:140-673` stays byte-unchanged until it is removed whole in the last Phase 1 PR;
- the Phase 0 PR touches only `setup.py:41`, `:111-117` and `:706-727`/`:777`;
- `mppl_freeze.py` vendors the converter verbatim from the epic base commit (with a hash check) and pins the environment;
- gate 1's reference is produced by that pinned copy at the epic base.

**P2-M5. "The drift check is clean at every freeze PR" conflicts with the branch policy for skills that cite `bbb/*.m`. The drift checker isn't on the base branch.**
*Location:* §4 "Documentation and AI layer"; §7.7; §11 last criterion; §12 Phase 1 ("The AI-layer process ticket merges right after [the first PR]").
*Evidence:*
- `check_context_refs.py` scans `.claude/skills/*/SKILL.md` and `.claude/agents/*.md` (`DOC_GLOBS`). It reports `path:line` refs to missing files as BROKEN and backticked missing paths as MISSING.
- Skills cite `bbb/pandf.m:513`, `bbb/pandf_boundary.m`, `bbb/odesetup.m` (plan-feature `SKILL.md:61-62`); `bbb/pandf.m`, `bbb/odesetup.m` (rca `:51`); `bbb/convert.m` (validate `:70`); and `bbb/pandf_plasma_energy.m` (code-review `:95`).
- The `bbb` freeze PR renames these files but may not edit skills (`branching.md`: process files only on `feature/v9-ai-*`). Its drift check therefore can't be clean.
- A process ticket merged "right after the first freeze PR" (`wdf`) can't point at `bbb/*.F` either, because those files don't exist yet.
- The process-ticket list in §4 also omits `rca`, `validate`, `prime` and `init-project`. All of them mention `.m`/MPPL.
- `check_context_refs.py`, `.claude/context/refs.lock.json` and `physics-models.md` exist only on `feature/v9-ai-layer`: they are absent from `origin/v9-develop` and from this planning branch. Yet §7.7 and §11 depend on them.

*Acceptance:*
- A sequencing that satisfies both rules. For example, the process ticket makes skill and agent citations extension-neutral (routine names or `bbb/pandf.*`) **before** Phase 1. Or the `bbb` PR is stacked on and merged together with an AI ticket. Or the per-PR drift criterion is scoped to code-facts docs and the skills are fixed in a named follow-up.
- The complete list of process files.
- An explicit assumption that the AI-layer branch with the drift checker is merged into `v9-develop` before Phase 0.

### Minor

- **P2-m1** (`get_packages.py`, §4/§8). The PRD lists `:159,266`, but there is a third `.m` filter at `:466` (`get_pandf_vars`). The `#` splits at `:164,521,574` apply to Fortran sources, while `:484` parses `bbb.v` and must keep `#`. *Acceptance:* list every site, and add a check that the generated pointer lists are identical before and after.
- **P2-m2** (`.gitignore` `!*.F`, §4/§11). With `core.ignorecase=true` (macOS), `!*.F` also un-ignores every `*.f`. Reproduced: `git check-ignore -v` reports `.gitignore:2:!*.F s/gen.f`. The existing `*.F` at `.gitignore:2` must also go. *Acceptance:* state the intended `.f` behaviour on macOS and test it with `check-ignore` for both cases.
- **P2-m3** (§12 Phase 1). GitHub "Rebase and merge" rewrites the commit SHAs, so a `.git-blame-ignore-revs` entry added inside the PR is wrong after the merge. Add it in a follow-up commit.
- **P2-m4** (§7.5 OpenMP case). The case does not set `ParallelMatfac=1`, so the guarded `OMPilut` branch (`bbb/oderhs.m:4656-4664`) is never run by gate 2. The PRD also doesn't say what happens if the determinism check fails. `ppp/omp_parallel.F90:951` has a `REDUCTION(+:yldottot)`.
- **P2-m5** (§6.3 req. 3 vs §7.3). One section says the anchor is "immediately before the same code line" (the following code line); the other says "preceding-code anchor". Code lines themselves are reordered by `MoveDecs` (for example the 92 `Common block` comments stay with the `use` lines). Define one anchor, and state that relocations within a routine are reported, not failed, so that "unexplained" has a precise meaning.
- **P2-m6** (§7.2 normaliser). "Drop comments" makes gate 1 blind to OpenMP sentinels (`!$omp`, `!$ `, `c$omp`, `*$`), which are code under `-fopenmp`. The 50 sources contain none today (only `C$$$`/`c$$$`, which are not sentinels). *Acceptance:* gate 1 asserts that no sentinel appears in any `.F`, or treats sentinel lines as code in the OpenMP configuration.
- **P2-m7** (§7.4).
  - "Before Phase 3, a script lists…" should say Phase 2, the phase that removes BASIS.
  - The table names `pck` but not the 9 `*/pck` files (the scan catches them via `BASIS_ROOT`).
  - The PACT block is `setup.py:111-117`, not `:111-114`. Deleting `:111-114` leaves a dangling `else:`.
- **P2-m8** (§6.2). The `diff -D` merge keeps the serial `c!omp …` comment lines in an `#ifndef _OPENMP` branch. State whether this form or a code-only `#ifdef _OPENMP` form is intended. The comment gate and its exception list depend on the choice.
- **P2-m9** (§7.4, §12 Phase 2). "The token gate shows that the `FORTHON` build is unchanged" for `com/error.f` and `bbb/exmain.c`, but gate 1 is defined only for the 50 frozen files. *Acceptance:* extend gate 1 to these two files, using the C preprocessor with the build's `-D` flags for `exmain.c`.
- **P2-m10** (§10). Setting a removed variable raises `bbbpy.error: no such attribute`, not `AttributeError`. Verified: its MRO is `bbbpy.error → Exception`. Fix the release-note wording.

## Status of previous findings

| ID | Status | Evidence (re-checked) |
|---|---|---|
| P1-C1 | **Resolved** | The owner redefined the requirement (information, not layout). §6.3 has a restore-text pass, an exact exception list (`do_i1` ×4, `ruthere` ×2, `c!omp`, `c!nopdb`, the PETSc class), and a gate that fails on unlisted differences and on unused exceptions. Remaining precision issues are P2-m5 and P2-m8. Comment restoration can't change code tokens through macros: the only function-like macros are in `forthonf2c.h`/`llnltyps.h`, which no `.m` includes, and gate 1 runs on the final file anyway |
| P1-M1 | **Resolved** | Re-ran the unmodified converter per file with fresh state. Only `bbb/pandf`, `oderhs` and `odesetup` differ between `OMP=FALSE` and `OMP=TRUE` (simple line-for-line hunks). `diff -D _OPENMP` (Apple/FreeBSD diff) → `gfortran -E` with and without `-fopenmp` is **identical** to each configuration's converter output for all 3 files, with no cpp diagnostics. The PETSc/PACT nesting question is moot after revision 3 |
| P1-M2 | **Resolved** | The object-code claim is dropped, and there is a string-preserving normaliser with continued-literal joining (§7.2). See P2-m6 for the sentinel gap |
| P1-M3 | **Resolved** | `numeric_baseline.py` records `float.hex(fnrm)` and SHA-256 of `yldot[:neq]` on a named machine, with negative controls for every tool. `bbb.yldot` (`bbb/bbb.v:1164`) and `get_fnrm` (`:3817`) exist |
| P1-M4 | **Resolved** | One standard (bit-identical at fixed `Nthreads=4`, after a determinism check). The switches exist (`bbb/bbb.v:4129-4130`, `ppp/ppp.v:9,14,15`). See P2-m4 |
| P1-M5 | **Partially resolved** | The case is defined, and the Forthon_case2 inputs `aeqdskd3d`/`neqdskd3d` exist (`mhdgeo=1`; `gengrid` defaults to 1, `bbb/bbb.v:3079`). But CI can't run it (P2-M3) |
| P1-M6 | **Resolved** | The §7.4 inventory matches `git ls-files`, and the content scan catches the rest (`*/pck`, `README_Uedge_vers`, `README.md`). See P2-m7 |
| P1-M7 | **Resolved** | Owner decision: delete both in their own commit. 50 files are frozen (`ls */*.m` minus the two = 50) |
| P1-M8 | **Resolved** (side effect in P2-m2) | `!*.F` makes `.F` visible on macOS. Re-checked with `check-ignore` in a scratch repo |
| P1-M9 | **Resolved** | Prerequisite PR first, then a stale-`.F` removal plus a rename-only commit, the freeze commit, and a code-facts commit. Rebase-merge and bisect-skip are specified. See P2-m3 |
| P1-M10 | **Resolved** | The tool is permanent with a `backport` mode, and the procedure goes in `doc/workflow.md` with a named owner. Converter pinning is in P2-M4 |
| P1-M11 | **Partially resolved** | Code-facts ship per PR, and the `CLAUDE.md` hard rule changes in the first PR. But the drift criterion conflicts with the skill branch policy, the process list is incomplete, and the checker is not on the base branch (P2-M5). The `get_packages.py` sites are incomplete (P2-m1) |
| P1-M12 | **Resolved** | §6.3 lexer requirements list every construct I raised. The record is `(routine, kind, marker, text, anchor)`, with an independent count cross-check |
| P1-m1 | **Resolved** | `Makefile.Forthon:51` (`nclpydep`) and `:71` (`find . -name \*.F`) verified. Counts 17 / 141 / 28 / 15 re-counted (`c!omp` 11+1+5; `cpetsc`/`cunipetsc` 65+2+66+8; `c!nopdb` 28; `cpetsc*`/`cpetscc` 14+1) |
| P1-m2 | **Moot** | PETSc removed (revision 3) |
| P1-m3 | **Resolved** | `-fopenmp`; Forthon flags taken from the build log |
| P1-m4 | **Resolved** | Parent-commit reference plus a code-freeze window. Converter pinning is in P2-M4 |
| P1-m5 | **Resolved** | Fresh state per file is required. My re-run used fresh state per file |
| P1-m6 | **Resolved** | The PRD is on `feature/v9-AIUE-5-planning`, with an estimate of about 4 weeks |
| P1-m7 | **Resolved** | `nclpydep` `touch $@` and `compydep` (§4) |

Scope-change checks requested by the coordinator:
- **`cpetsc` lines active today?** No. Both builds run with `PETSC_DIR` unset, and no line starts with an upper-case or indented variant. Deleting all 141 lines from the `.m` copies before conversion gives **code-identical** `gfortran -E` output (comment lines stripped) for `odesolve`, `odesetup` and `nksol`, serial and OpenMP. They are lower-case `c` comment lines, so they can never trigger the `MoveDecs` flush (`setup.py:263` tests `s[0] != "c"`).
- **`c!nopdb` and `MoveDecs`.** The stubs are already code in today's output: `Nopdb` runs before `MoveDecs` (`setup.py:654-660`). Making them unconditional reproduces the `OMP=*`, `PACT_DIR`-unset output exactly. The only hazard is the Phase 0 edit in P2-M4.

## What was checked and how

- **Converter.** Extracted the converter section of `setup.py` (between the "CONVERSION OF MPPL FILES" banners) and exec'd it in a fresh namespace for each of the 50 compiled files. Ran 12 environment combinations (OMP × PETSc{off,on,on+PARALLEL} × PACT) before the scope change; only serial and OpenMP are used in the conclusions. Script: `$TMPDIR/aiue5r2/scripts/runconv.py`.
- **Round trip.** `diff -D _OPENMP` merge of serial vs OpenMP for `pandf`, `oderhs`, `odesetup`. Ran `gfortran -E -cpp -DFORTHON -ffixed-line-length-132 -fdefault-real-8 [-fopenmp]` (GCC 15.2.0) on the merged file and on each configuration's output, dropped line markers and blank lines, then compared: identical, with no diagnostics.
- **PETSc deletion equivalence.** Script `nopetsc.sh`: removed the `cpetsc`/`cunipetsc` lines from copies of the `.m` files, converted, preprocessed, stripped comments, and compared with the reference: identical in both builds.
- **Scans:**
  - OpenMP sentinels in the 50 `.m` (none);
  - upper-case or indented PETSc/OMP prefixes (none);
  - function-like macros in included headers (none in `mppl.h`, `sptodp.h`, `com.h`, `bbb.h`, `api.h`);
  - existing `c!ifdef`/`c!else`/`c!endif` (none);
  - `grdproc` sites (no comments swallowed);
  - `git grep` for PETSc/PACT/`petscopt` across the repo;
  - BASIS artefacts via `git ls-files`.
- **HDF5.** Ran `hdf5_dump` and `hdf5_restore_dump` against the installed uedge (pyenv `uedev`, code identical to the worktree) with a missing-variable dataset: the restore aborted. Script `h5test.py`. Also checked how Forthon handles setting an unknown attribute (`Forthon.h` `Forthon_setattro` → `ErrorObject`; observed `bbbpy.error`).
- **git.** `.gitignore` negation under `core.ignorecase=true` and `false` in a scratch repo. `git ls-remote --heads upstream` for the pytests branches.
- **Read:**
  - `.github/workflows/build-test-wheel.yml` and `build-basis.yml`;
  - `Makefile.Forthon`;
  - `setup.py:25-130`, `:140-673`, `:700-780`;
  - `get_packages.py`;
  - `src/uedge/hdf5.py` and `uedge_lists.py`;
  - `bbb/odesetup.m:6845-7510`, `bbb/ext_neutrals.m:2598-2634`;
  - `.claude/context/branching.md`; `check_context_refs.py` (main checkout, `feature/v9-ai-layer`); skill and agent files for `.m` citations.
- **Not done:** no UEDGE build or regression run (not needed for a PRD review). All scratch scripts are under `$TMPDIR/aiue5r2/` (outside the repo).
