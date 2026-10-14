# Review: AIUE-5 PRD "Switch to pure Fortran build" (stage: prd, round 4)

- **PRD:** `docs/prds/AIUE-5-switch-to-pure-fortran-build.md`, revision 5 (worktree `uedge-wt/AIUE-5`, branch `feature/v9-AIUE-5-planning` @ 4e531df; PRD untracked).
- **Inputs:** round-2 review and response (round 3 was stopped before it reported); the "Revision 5" note in `AIUE-5-prd-round2-response.md`.
- **Binding decisions checked against:**
  - retire MPPL and BASIS completely, keep `.v` + Forthon;
  - free-form `.F90` for the 50 MPPL-derived files only;
  - serial + OpenMP only, PETSc/PACT removed (incl. the 15 comment lines and `petscoptfile`/`petscopts`);
  - tolerant `hdf5_restore_dump`;
  - "unchanged" = same compiled program in both builds + exact `fnrm`/residuals, objects need not be byte-identical;
  - no comment information lost;
  - delete `bbb/s.m`, `flx/dvshdf5.m`;
  - `gengrid=1` test before the BASIS CI goes;
  - `branching.md` policy.

  I did not reopen any of them.

## Verdict

**REVISE**

## Summary

Revision 5 is a sound redesign, and the evidence strongly supports the two-stage approach. I ran the unmodified converter, merged the two builds, and converted all 50 files with `findent` 4.3.6. For **45 of the 50 files**, gfortran's `-fdump-fortran-original` parse tree of the free-form output is identical to the fixed-form reference in both the serial and the OpenMP build. Every difference in the other 5 files is a real defect, and the dump finds it. So the dump is form-independent on these sources, and stage 2 is tractable. Hollerith compiles in free form, and the headers are valid there too.

Three MAJOR problems remain:
- the parse-tree dump contains no `FORMAT` statements, so gate 1 cannot check the 256 FORMATs or any Hollerith count. 56 continued FORMATs will compile to different format strings unless their padding is reproduced;
- a stale generated `.F` beside a committed `.F90` is compiled in preference to it. The PRD removes both safeguards against this (the `clean` rule and the ignore pattern), which can make gate 2 pass vacuously;
- the comment gate shares its lexer with the converter, which leaves a common-mode blind spot. It has a concrete instance in the 5 comments that run past column 132.

All round-2 findings are resolved, moot or partially resolved. None is open as BLOCKER or MAJOR.

## Findings

### Blocker

None.

### Major

**P4-M1. Gate 1's primary check cannot see FORMAT statements. Continued FORMATs will compile to different format strings.**
*Location:* §7.2 ("The dumps must be identical, including character constants, labels, `FORMAT` contents …"; negative control "an altered Hollerith count"); §6.3 Hollerith row; §11 gate-1 criterion; decisions table, "Default results".

*Evidence:*
- **What the dump checks.** `gfortran -fsyntax-only -fdump-fortran-original` (GCC 15.2) has no source locations and is deterministic. I mutated a small test file in many ways:
  - **Detected:** label moves, DATA values, EQUIVALENCE, COMMON order, SAVE, NAMELIST order, PARAMETER values, statement functions, I/O specifiers (`err=`, `end=`, `status=`), STOP strings, ENTRY names, arithmetic-IF targets, inline format strings, BLOCK DATA, `intrinsic`↔`external`, character lengths.
  - **Not detected:** any change *inside a FORMAT statement*. A changed character constant, a changed edit descriptor and a changed Hollerith count all give an identical dump. FORMAT statements are not printed at all; a WRITE shows only `FMT=<label>`.
- **On the real sources.** In `svr/svrut1` I made two edits:
  - `58hizontally` → `57hizontally` (FORMAT 908);
  - `99i1` → `98i1` (FORMAT 902).

  Both give a dump identical to the unmutated file.
- **Scope of the gap.** My lexer counts 256 FORMAT statements in the reference. All 51 Hollerith edit descriptors are in FORMATs (`svr/svrut1.m` 908, `svr/svrut4.m` 100-110). Only the `svrut4` ones reach the dump, and only because they are used through `ASSIGN`.
- **The padding problem.** gfortran stores the FORMAT text *including fixed-form padding to column 132*. In `-fdump-tree-original` the `svrut1` FORMAT 908 is passed as an 816-character string from the reference, but as a 388-character string from the free-form output. `wdf` shows the same effect.
  - My lexer finds 56 continued FORMATs in 10 files (`svr/nksol` 20, `grd/grdcomp` 16, `api/fmombal` 6, `svr/uoa` 4, `wdf/wdf` 4, `grd/grdwrit` 2, and one each in `oderhs`, `odesetup`, `flxcomp`, `svrut1`). Their compiled format constants will differ.
  - Free form *can* reproduce them: blanks before `&` are kept in the stored format. Verified: `(1x,        i5)` vs `(1x,i5)`.
  - The difference is runtime-equivalent, because blanks outside character/Hollerith descriptors are insignificant. I found no Hollerith or quoted string that spans a line break inside these 56.
  - Even so, the compiled program is not literally the same, and nothing in the PRD says which rule applies.
- **Cost of a stricter check.** `-fdump-tree-original` (needs `-c`) does contain the format strings. Once `common.line`, `common.filename` and the `In file '…', around line N` strings are normalised, it was form-independent on `svrut1`, `svrut4`, `wdf` and `aphread`. The only remaining differences were the padded strings and the FORMAT padding. It is one candidate for the complement.

*Acceptance:* the PRD:
- states that the parse dump omits FORMAT statements;
- adds a FORMAT-content check that does not depend on the converter's lexer (for example, tree-dump format strings with explicit normalisation, or gfortran-derived extraction), with the Hollerith-count and edit-descriptor negative controls run on real FORMATs;
- states the rule for the 56 continued FORMATs: (a) reproduce the padding, so the format constants are byte-identical, or (b) define "same program" to allow blank-only differences outside character/Hollerith descriptors.

*Note for the epic owner:* option (b) refines your definition of "same compiled program", so the choice between (a) and (b) is yours.

**P4-M2. A stale generated `.F` is compiled in preference to the committed `.F90`. The PRD removes both safeguards against this, which can make gate 2 vacuous.**
*Location:* §4 "Build and repository" ("`clean` stops deleting sources"; "the `*.F` pattern … is removed"); §6.1 row 2 ("removes build products only"); §7.5 (before/after "on the same machine"); §11 `git status --ignored` criterion.

*Evidence:*
- **Rule order.** For each source directory, Forthon's generated makefile lists `%.o: ../<dir>/%.F` (f90fixed) *before* `%.o: ../<dir>/%.F90` (f90free) (`Forthon/Forthon_builder.py:349-356`). GNU make uses the first pattern rule whose prerequisite exists, and the stems are equal. In a scratch test with `src/a.F` and `src/a.F90` side by side, make ran the **fixed** rule on `a.F`.
- **Where stale `.F` files come from.** Every pre-freeze build writes `<pkg>/<name>.F` into the source tree (`mppl2f90(targetdir=".")`). pip builds in-tree. Today, `Makefile.Forthon:71` (`find . -name \*.F -exec rm {} \;`) deletes those files before each non-`--noclean` build, and this PRD removes that rule.
- **macOS hides them.** This worktree has `core.ignorecase=true`. `git check-ignore -v --no-index bbb/pandf.F` reports `.gitignore:19:*.f`. So a stale `.F` stays ignored and invisible on macOS even after `*.F` is removed from `.gitignore`.
- **Consequences:**
  - In a developer tree that built before the freeze, edits to `.F90` are silently ignored.
  - Gate 2's "after" run on the same machine can link the "before" code, so it passes trivially.
  - The §11 `--ignored` check runs only on a fresh clone, so it never sees this.
  - Nothing tracked ends in `.F` (`git ls-files '*.F'` is empty), and `find -name` is case-sensitive on macOS. Keeping the deletion is therefore safe for the `.f` and `.F90` sources.

*Acceptance:*
- The build permanently removes or refuses `<pkg>/*.F` (for example, keep the `find -name '*.F'` deletion, or fail when `<pkg>/<x>.F` and `<pkg>/<x>.F90` both exist).
- Gate 2's "after" build runs in a fresh worktree or asserts that no `<pkg>/*.F` exists.
- A negative control: a stale `.F` with different content must not change the build.

**P4-M3. The comment gate shares its lexer with the converter, so input-side lexer errors are invisible. The 5 comments past column 132 are a concrete case.**
*Location:* §6.4 "Lexer requirements (shared by the comment pass, stage 2 and the fidelity check)"; §7.3 (independent cross-check by counts; negative controls).

*Evidence:*
- Five comments in the `.m` sources extend past column 132:
  - `bbb/geometry.m:1129` (144 characters);
  - `bbb/oderhs.m:1105` (146) and `:1116` (143);
  - `bbb/odesetup.m:5373` (135);
  - `bbb/pandf_plasma_momentum.m:408`, an inline comment on a code line (141).
- A fixed-form lexer must ignore *code* beyond column 132. `findent -L132g` did exactly that and dropped `neutrals?` from the `pandf_plasma_momentum` comment.
- Suppose the fidelity check reads the `.m` with the same lexer. Then both sides carry the same truncated text, and the gate passes. The count cross-check is unchanged. Every listed negative control mutates the *output*, so none of them exercises an input-reading error.
- findent also rewrote `C$$$`/`c$$$` as `!$ $$` (8 lines in `bbb/odesetup`, `svr/nksol`). That alters the text but leaves the comment count unchanged.

*Acceptance:*
- The `.m`-side comment extraction is independent of the converter's lexer. Alternatively, the cross-check compares comment *text*, for example a per-routine multiset of whole comment text read with no column limit.
- Input-side negative controls are added: a comment past column 132 and a `c$$$` line. The 5 long comments become fixtures.

### Minor

**P4-m1. The line-length premise is version-dependent, and the 132-character criterion conflicts with the comment rule** (§4 "Line length"; §11 "No `.F90` line is longer than 132 characters").
- **GCC 15.2 enforces no limit by default.** A 264-character free-form line compiles without any diagnostic and is read in full (`x = 1.0 + 0…07.0` gives 8.0). The 132 limit (`-Werror=line-truncation`) applies only with an explicit `-ffree-line-length-132`, and then *after* cpp expansion: a 123-character raw line containing `Pi` failed.
- **Effects:**
  - the build will not catch a long line, so the §11 script is the only guard;
  - CI's older gfortran may behave differently.
- **Measured:** no code line exceeds 132 characters after cpp expansion, even with the layout preserved and `&` added. Long comments compile even with the explicit limit.
- **The conflict.** Keeping the 5 long comments (P4-M3) unchanged and inline breaks the ≤ 132 criterion.

*Acceptance:* apply the criterion to code lines after cpp expansion. Exempt comments, or list them as exceptions.

**P4-m2. The findent option needs an indentation policy and a version pin** (§6.3, §4 "Out of scope … no reformatting", §7.1 permanent tool, §8 tool dependencies).
- **Indentation.** `findent --indent=none` (`-i-`) disables the conversion entirely: the output is unchanged fixed form. findent therefore re-indents every line. That is a reformat, so the PRD should say whether it is acceptable.
- **Version pin.** Backports re-freeze through the tool, and its output depends on the findent version, so the version must be pinned like the converter copy.
- **Defect classes for the Phase 0 fixtures.** With findent the defects were:
  - the padding of the 6 continued strings;
  - one blank-insensitive token (P4-m5);
  - 8 `c$$$` lines turned into `!$` sentinels (caught by the secondary check, which matches P2-m6);
  - comment truncation at column 132 (P4-M3).

  Nothing else differed.

**P4-m3. The comment taxonomy omits indented comment-only lines** (§6.4 req. 1 and lexer list).
- 731 lines in the 50 files are comment-only but indented: 715 indented `#` and 16 indented `!`. An example is `bbb/pandf_boundary.m`, inside a continued `if`.
- They are neither "column-1 `#`" nor inline.

*Acceptance:* define them as full-line comments, so that the inline↔full-line control does not misfire.

**P4-m4. Gate 1 conflicts with the `.v` change in the `bbb` PR** (§12 Phase 1; §7.4).
- `petscoptfile` appears as a use-associated symbol in the parse dumps of every file that has `Use(UEpar)`. That is 10 converted files, among them `aph/aphrates`, `aph/aphread`, `bbb/oderhs` and `bbb/pandf_boundary`.
- A parent-commit reference compiled against the old modules can therefore never match.

*Acceptance:* state that both sides compile against the same module set, or move the `.v` removal into its own commit with its own gate run.

**P4-m5. `external tick tock` (`bbb/oderhs.m:69`) declares the symbol `ticktock`.** Fixed form ignores blanks, so this statement does not declare `tick` and `tock` external.
- It is the only blank-insensitivity hazard in about 49k statements.
- To pass gate 1, stage 2 must write `external ticktock`.

*Acceptance:* record it in the freeze report, plus a follow-up ticket, so that nobody "fixes" it inside a freeze PR.

**P4-m6. `get_packages.py` and free form** (§4; continues P2-m1).
- Its comment rule `line[0].lower() == 'c'` (`:162`, `:519`, `:572`) is a fixed-form rule. In free form it would skip any code line that starts with `c` in column 1. Whether that happens depends on the indentation policy (P4-m2).
- The before/after identity check on the generated pointer lists, which P2-m1 asked for, is still missing.

**P4-m7. Wording.**
- For gfortran, Forthon adds no `-ffree-form`: the suffix selects the form, and `-ffree-form` appears only in the g95 branch (`compilers.py:305`). This affects §4, §6.1 and §7.2.
- The column-6 continuation marker is not just `.`. The reference uses 14 different characters: `.` (4,386), `&` (429), `*` (407), `>` and `+` (129 each), digits, `,` and `$`.
- §4 says the AI layer "is being merged". It now has been (`v9-develop` @ 0fac655).

## Status of previous findings (round 2)

| ID | Status | Evidence (re-checked on revision 5) |
|---|---|---|
| P2-B1 | **Resolved** | Owner decision: tolerant `hdf5_restore_dump` (`src/uedge/hdf5.py:264` verified), with an old-dump test (§4), a §11 criterion and a §14 risk row. §10 now says that full dumps contain both variables |
| P2-M1 | **Resolved** | `petscopts` is removed together with `petscoptfile` (`bbb/bbb.v:157-158`, `pyscripts/bas2py_rules.py:109-110` verified). The deck exception names both |
| P2-M2 | **Resolved** | §11 is now a defined `git grep -niE 'petsc\|pact_dir\|nopdb'` scan against `tools/petsc_allowlist.txt`. The kept branches and stubs are listed (`ppp/omp_parallel.F90:1124,1305` verified) |
| P2-M3 | **Resolved** | The CI change is in scope (`pytests` for every branch, a matrix entry, the case PR'd to LLNL/UEDGE `pytests`). `git ls-remote` shows that `pytests` exists |
| P2-M4 | **Resolved** | The Phase 0 PR removes only the build paths (`setup.py:41`, `:111-117`, `:707-727`, `:777` verified). `Petsc`/`Nopdb` (`:190-207`) stay until the converter is deleted. `mppl_freeze.py` carries a hash-checked copy with the environment pinned |
| P2-M5 | **Resolved** | The AI layer is now merged (`v9-develop` 0fac655, which has `check_context_refs.py`). The process ticket is in Phase 0 and covers every skill and agent that cites `.m`/MPPL. *Note (not a new finding):* `commit` `SKILL.md:22` ("generated `.F` files") and the prose in `physics-workflow.md:9` and `branching.md:14` will become stale, and the drift check does not catch prose |
| P2-m1 | **Partially resolved** | All sites are listed. The identity check is missing, and there is a new free-form issue (P4-m6) |
| P2-m2 | **Moot** | There is no `!*.F` any more, and `*.F`/`*.f` do not match `*.F90` (verified with `check-ignore`). A related new risk is in P4-M2 (`*.f` hides `.F` on macOS) |
| P2-m3 | **Resolved** | `.git-blame-ignore-revs` goes in a follow-up commit after the rebase-merge |
| P2-m4 | **Resolved** | `ParallelMatfac=1` is set, and the non-determinism procedure is "pin, otherwise escalate" |
| P2-m5 | **Resolved** | A single following-code anchor; relocations are reported. See P4-m3 for the taxonomy gap |
| P2-m6 | **Resolved**, and shown to be necessary | findent turned `c$$$` into `!$ $$`. The serial build compiled it, and the OpenMP build rejected it. The secondary sentinel check catches this |
| P2-m7 | **Resolved** | The Phase 2 scan, `*/pck` (9) and `setup.py:111-117` are all fixed |
| P2-m8 | **Resolved** | The serial `c!omp` copies are dropped. In the merged reference they are only the `#ifndef` comment blocks |
| P2-m9 | **Resolved** | The preprocessing check for `com/error.f` and `bbb/exmain.c` is in §7.2 |
| P2-m10 | **Resolved** | `bbbpy.error` |

## What was checked and how

All scratch work is in `$TMPDIR/aiue5r4/`, outside the repo. I did not build or install UEDGE and did not run the regression suites.

- **Stage 1.**
  - Ran the unmodified `setup.py` converter on all 50 files, with fresh state per file, for `OMP=FALSE` and `OMP=TRUE` (script `runconv.py`).
  - Only `bbb/oderhs`, `bbb/odesetup` and `bbb/pandf` differ between the two builds.
  - Dropped the 141 `cpetsc`/`cunipetsc` lines, then merged with `diff -D _OPENMP`. The reference has 90,202 lines.
- **Modules for the parse dumps.**
  - Generated the Forthon wrappers for all 9 packages with `Forthon.wrappergenerator`, then made `.mod` files with `gfortran -fsyntax-only`, serial and `-fopenmp`.
  - The flags must include `-DISZ=8 -fdefault-integer-8`, since Forthon's `intsize` is 8. With `ISZ=4`, 16 files fail with spurious kind mismatches.
- **Stage 2 trial.**
  - Installed `findent` 4.3.6 (pip) in a scratch venv. Converted with `findent -ifixed -ofree -L132g`.
  - Ran `-fsyntax-only -fdump-fortran-original` (Forthon f90fixed/f90free flags) on both forms, in both builds.
  - All 50 references parse.
  - 45 files give identical dumps in both builds. The 5 that differ are `aphread`, `griddubl` and `odesetup` (padded strings), `oderhs` (`ticktock`), and `odesetup`/`nksol` under OpenMP (sentinels).
  - Warning counts are equal on the two sides.
  - No Hollerith diagnostics appear in free form.
- **Gate-1 completeness.** Wrote mutation batteries on synthetic fixed and free files and on the real `svrut1`. Also ran `-fdump-tree-original` on 4 real files, with location strings normalised.
- **Scans with my own fixed-form lexer on the reference:**
  - 49,355 statements, of which 3,366 are continued;
  - 6 continued character contexts, the same set as the PRD's;
  - 256 FORMATs, 56 of them continued;
  - 51 Hollerith descriptors, none spanning a line;
  - 2 comment lines inside continued statements and 8 inline comments on non-final continuation lines;
  - 1,656 tab-formatted code lines and no tab-digit continuations;
  - no code past column 132;
  - no code line over 132 characters after cpp expansion with layout preserved;
  - no `__LINE__`/`__FILE__`;
  - no converter-rewritten token inside a code string.
- **Line length.** Free-form tests with GCC 15.2, with and without `-ffree-line-length-132`, before and after cpp expansion, and for long comments.
- **Build and git:**
  - read `Forthon/compilers.py` (linux/macosx gfortran) and `Forthon_builder.py` (rule order);
  - scratch `make` test for rule precedence;
  - `git check-ignore -v --no-index` with `core.ignorecase` on and off;
  - `git ls-files '*.F'`;
  - `MANIFEST.in`;
  - `build-test-wheel.yml`.
- **Re-verified file:line claims:**
  - `hdf5.py:264`;
  - `bbb.v:157-158`;
  - `bas2py_rules.py:109-110`;
  - `setup.py:41`, `:111-117`, `:140`, `:190`, `:205-207`, `:673`, `:707-728`, `:777`;
  - `Makefile.Forthon:51`;
  - `svrut4.m:2189`;
  - `aphread.m:465-466`;
  - `grdcomp.m:4245`;
  - `pandf.m:19-25`, `:552`;
  - `oderhs.m:1078`, `:4656`, `:4702`;
  - `odesetup.m:369`;
  - `omp_parallel.F90:1124`, `:1305`;
  - `sputt.m:6`;
  - counts: 52 `.m` files (93,663 lines), and per package 17/5/2/7/4/5/8/1/1.
- **AI layer.** Main checkout `v9-develop` @ 0fac655: `.claude/hooks/check_context_refs.py` and `change_kind.py`, plus greps of the skills, agents and context modules for `.m`/MPPL.
