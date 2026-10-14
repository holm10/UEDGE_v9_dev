# Review: AIUE-5 PRD "Switch to pure Fortran build" (stage: prd, round 1)

- **PRD:** `docs/prds/AIUE-5-switch-to-pure-fortran-build.md` (untracked on `v9-agentic` @ 51e698c)
- **Reviewer:** uedge-reviewer (independent, adversarial)
- **Binding decisions checked against:** retire MPPL and BASIS; keep `.v` + Forthon; bit-identical results; `pip install` and wheels, OpenMP parity, input decks and HDF5 saves keep working; every comment carried over verbatim (comment-aware freeze + fidelity check).

## Verdict

**REVISE**

## Summary

The overall approach is sound and should not be rejected: freeze the sources once with the existing converter, then prove equivalence on the cpp-expanded token stream. I re-ran the real `setup.py` converter on all 52 files and checked its claims against the code. The PRD has a few load-bearing errors.

1. The comment-preservation requirements contradict each other. They also contradict what the converter does today:
   - some comments are turned into code;
   - some code is turned into comments;
   - 84 comment lines in 17 files are reordered by `MoveDecs` and `Elseifthen`.

   As written, the fidelity check cannot pass at the same time as the bit-identity requirement.
2. Emitting `#ifdef` inside the current rule chain is unsound, because `MoveDecs` and `Elseifthen` classify lines by column 6.
3. The claim "identical token stream, therefore identical object code" is false, because source line numbers are compiled into `.text`.
4. "Compare fnrm logs" cannot be measured with the existing suite.

The scope also has holes:
- most BASIS files are not covered;
- two `.m` files are never compiled;
- macOS `.gitignore` case-folding;
- the v8 to v9 cherry-pick backport stream;
- the branching policy for AI-layer edits;
- `get_packages.py`;
- the loss of the only CI coverage of grid generation in `flx`/`grd`.

All of these can be fixed in the PRD text.

## Findings

### Critical

**P1-C1. The comment-preservation requirements cannot all hold at once with bit-identical code. The fidelity check as specified is guaranteed to fail.**
*Location:* §4 "Carry every comment over verbatim"; §6 "Conversion approach" step 1 and "Comment preservation" requirements 1-3; §7.1b; §11 ("0 missing, 0 altered, counts equal").
*Evidence* (exact converter extracted from `setup.py:140-673` and run on all 52 files; scripts in "What was checked"):
1. **Comments that become code.** `grd/grdcomp.m:4245,4259,4279` (`break (2) # exit do_i1`) and `:4284` (`enddo # do_i1`):
   - Rule `("#","!")` runs first (`setup.py:634`).
   - Then `("break (2) ! exit do_i1","exit do_i1")` and `("enddo ! do_i1","enddo do_i1")` (`setup.py:638-639`) turn the comment text into code.
   - The reference output is `exit do_i1` and `enddo do_i1` (`grdcomp.F:4245-4284`).

   PRD §6 step 1 says "split code/comment before any rule runs; rules act on the code part only". Under that design these comments survive, `break (2)` stays as code, and ` break ` → ` exit ` then produces `exit (2)`. That is wrong code or a compile error. Requirement 1 ("nothing is deleted") cannot hold for these 4 comments without changing code.
2. **Code that becomes comments.** `("      call ruthere","c     call ruthere")` hits `bbb/pandf.m:552` and `bbb/oderhs.m:1078`. These are new comments with no `.m` counterpart, so "counts equal to the `.m`" fails.
3. **Comments that are reordered today.** `MoveDecs` and `Elseifthen` change the relative order of **84 full-line comment lines in 17 files** (measured: comment sequence of the `.m` vs the reference `.F`). Examples:
   - `bbb/turbulence.m:10-36`: `c ... Local variables:` ends up *above* `implicit none`, detached from the local declarations it labels. `c ... Common blocks:` is not moved at all.
   - `aph/aphrates.m:700-703`: the comment after a multi-line `elseif ... then` is emitted *before* the `elseif` (`Elseifthen` buffers continuation lines and returns comment lines immediately).
   - Which comments move depends on:
     - `in_uses`;
     - the character in `s[5]` (comments whose column 6 is non-blank are treated as "continuation lines");
     - the literal text `"Common block"` (92 such comments are never moved);
     - lower-case `c` only (`setup.py:256` tests `s[0] != "c"`).

   Requirement 3 says "keep their order ... move with it **as they do today**". Those two halves are mutually exclusive. The §7.1b check requires ordered lists that are equal per routine, so it fails on these 84 lines if the freeze reproduces today's layout.

*Why it matters:* the comment rule is a binding owner decision. Bit-identity is another binding decision. The PRD has to say which layout wins where they interact, or the tickets cannot be implemented and the acceptance criterion cannot be met.

*Recommended PRD change:*
- (a) State explicitly that comments do not affect code. The freeze therefore places comments by the `.m` order, attached to the next code line, rather than by today's `MoveDecs` side effects. Recommended, because it fixes today's misattached headers.
- (b) Define an explicit, reviewed **exception list** with exact locations and counts:
  - the 4 `do_i1` comments consumed into code;
  - the 2 `ruthere` lines that become comments;
  - the `c!omp` / `cpetsc` / `c!nopdb` payload lines that change between comment and code.
- (c) Make the fidelity check's acceptance criterion "0 unexplained missing/extra/altered/reordered, with the exception list matched exactly", instead of plain equality.

### Major

**P1-M1. Making `Omp`/`Petsc`/`Nopdb` emit `#ifdef` inside today's rule order corrupts declaration blocks. The planned harness configurations cannot see it.**
*Location:* §6 "Conversion approach" step 1; §7.1; Risk table row 3 ("Freeze with the same rule order as today").
*Evidence:*
- `Nopdb`, `Petsc` and `Omp` run *before* `Elseifthen` and `MoveDecs` (`setup.py:654-660`).
- A rule that returns a multi-line string is seen by later rules as **one line**.
- `MoveDecs` classifies lines by `s[0]`, `s[5]` and `len(s)>6`:
  - `#ifdef X`, `#if de…` and `#endif` have a non-blank column 6, so they are saved as **continuation lines**;
  - `#else\n` has length 6, so it is treated as the **first executable statement** and flushes the saved declarations at that point.
- Simulation on `bbb/odesolve.m:58-60` with `cpetsc`/`cunipetsc` mapped to `#ifdef` in place of the `Petsc` rule:
  - output puts `#ifdef HAVE_PETSC / use PETSc_Snes_Param / #endif` at lines 59-61, *after* `implicit none` (line 56);
  - with `HAVE_PETSC` defined this is a compile error (USE after IMPLICIT);
  - today's `PETSC_DIR` path keeps the `use` among the other uses.
- The `c!omp if` at `bbb/oderhs.m:4656` sits directly after a declaration block (`ilut_interface`). It only comes out right because `#ifdef _OPENMP` happens to have a non-blank column 6.
- The harness (§7.2) checks only serial and OMP with PETSc and PACT off, so a broken PETSc or PACT mapping passes.

*Recommended PRD change:* the PRD must not prescribe "same rule order with `#ifdef`-emitting rules". Require instead one of:
- (i) Generate the `.F` once per configuration with the **unmodified** converter, then merge mechanically. For example, `diff -D _OPENMP ser.F omp.F` works with macOS and GNU diff; I tried it on `pandf`, `oderhs` and `odesetup`. Do it in nested passes for `HAVE_PETSC`, `PARALLEL` and `HAVE_PACT`.
- (ii) Map the conditionals *after* `MoveDecs`.

In both cases, add cpp-level equivalence configurations for PETSc on (± `PARALLEL`) and PACT on. These only need `gfortran -E`, not a PETSc install.

**P1-M2. The claim "identical cpp token streams, and therefore identical object code" is false. The object comparison as written will report differences, and it also misses some real ones.**
*Location:* §6 "Conversion approach" step 3; §7.2 "Secondary check".
*Evidence:*
- gfortran compiles source line numbers into `.text`, as the `line` field of every I/O statement, and into `-fcheck` messages.
  - Test: the same subroutine with one extra leading comment line gives `mov w3, #0x5` vs `mov w3, #0x6` in `objdump -d`.
  - The strings change from `At line 4 of file a.F` to `At line 5 of file b.F`.
- Every `#ifdef`/`#else`/`#endif` the freeze adds shifts every later line. That affects:
  - `pandf.F` from line 19;
  - `odesetup.F` from line 369;
  - `oderhs.F` from line 4656;
  - `odesolve.F` from line 58;
  - `nksol.F` from line 713.

  These files have many WRITE statements, so `.text` *will* differ even when the code is equivalent.
- Comparing `.text` without relocations (`objdump -d` without `-r`) cannot see a changed call target.
- Data sections (DATA statements, format and string constants) are not compared at all.
- §7.2 step 3 says "collapse whitespace". Inside character literals that hides changes, including fixed-form padding for strings continued across lines, e.g. `aph/aphread.m:465-466` and `bbb/odesetup.m:1623-1624`.

*Recommended PRD change:*
- Drop "therefore identical object code".
- Make the token-stream diff the gate, with a string-preserving normaliser: whitespace is collapsed only outside literals, and continued literals are joined with the compiler's padding rules.
- Make the object check line-number-insensitive:
  - compare `-fdump-tree-original` (or `-optimized`) dumps with `line =` / location info normalised, or
  - compare `objdump -dr` plus `-s` data sections with a documented, mechanically filtered set of line-number immediates.
- State the expected differences per file in advance.

**P1-M3. The runtime success criteria cannot be measured, and the harness self-tests have no power to detect anything.**
*Location:* §11 ("zero change in reported `fnrm` (compare logs)"); §12 Phase 1 "Validation ... unchanged tree reports 52/52 equivalent. That's the self-test"; §7.1b self-test.
*Evidence:*
- In `origin/pytests` (e.g. `pytests/unittests/D_mols/nonog_mols/default/test_nonog_mols_default.py`), `fnrm` is printed only on failure (`{:.8e}`, 9 significant digits), and the comparison is `isclose(..., rtol=1e-5)`.
- Passing tests print no `fnrm`, so there is no log to diff.
- `testing.md` confirms `rtol=1e-5` and `com.iprint=0`.
- An "unchanged tree" self-test compares the old converter with itself. It cannot fail.

*Recommended PRD change:*
- Add a baseline script that records, for every case and every equation-switch cycle:
  - `float.hex(bbb.get_fnrm(bbb.dtreal))`;
  - a SHA-256 of `bbb.yldot[:neq]`.
- Run it before and after on the **same machine, compiler and flags**. Name the platform used for the "CI configuration" claim.
- Add **negative controls** to both tools, and require that each one is detected:
  - for the equivalence harness: a sign flip, a dropped `c!omp` line, `#ifdef` and `#ifndef` swapped;
  - for the fidelity checker: a reworded comment, a deleted comment, a moved comment, a `c`→`!` marker change, an inline comment moved to its own line.

**P1-M4. The OpenMP requirement is inconsistent with the binding "bit-identical" decision and is not testable as stated.**
*Location:* §1 MVP goal ("bit-identical ... in both serial and OpenMP builds") vs §9 ("OpenMP build must match its own pre-change results to round-off") vs §11 ("serial vs OpenMP ... agree to round-off").
*Evidence:*
- The pytests never set `ParallelPandf1`/`ParallelJac`/`Nthreads` (`openmp-jacobian.md`). Running the suites on an OpenMP build therefore exercises the serial paths, never `OMPPandf1Rhs` / `jac_calc_parallel`.
- The reductions in `ppp/omp_parallel.F90` may not reproduce bit-for-bit from run to run.

*Recommended PRD change:*
- Pick one OpenMP standard. Since the token streams are identical, it should be "bit-identical to its own pre-change build at fixed `Nthreads` and schedule", with a run-to-run determinism check on the baseline first.
- Name the case: a double-null or X-point case with `ParallelPandf1=1`, `ParallelJac=1`, `Nthreads=4`, `CheckPandf1=1`, `CheckJac=1`.

**P1-M5. Removing BASIS CI removes the only runtime coverage of `flx`/`grd` grid generation. The PRD does not replace it.**
*Location:* §4 "Remove BASIS"; §11; §14.
*Evidence:*
- `build-basis.yml` gates on the "All level 2 tests passed" output of BASIS.
- `builder/test/level_2` runs `flx`/`grd` mesh generation from `aeqdsk`/`neqdsk` and compares outputs with `pdbdiff -p 1e-8`.
- The pytests use `bbb.gengrid=0` (read `gridue`), e.g. `pytests/unittests/D_mols/nonog_mols/default/input.py:17`, and no pytests case contains an eqdsk file.
- `flx` (5 files), `grd` (5), `wdf` and `ncl` are converted and then verified only by the cpp harness.

*Recommended PRD change:* add a Python regression with `gengrid=1` that is run before and after and compared bitwise. Compare `gridue` and `com.rm/zm/psi`, using e.g. the inputs in `builder/test/Forthon_cases/Forthon_case2` (`aeqdskd3d`, `neqdskd3d`). Add it to Phase 1 baselines and to §11.

**P1-M6. The BASIS removal scope is incomplete.**
*Location:* §4 Technical; §7.4; §8 "BASIS" row; §11 ("No ... `Package`, `PackageMake` or `uedge.pack` file is left").
*Evidence:* tracked BASIS-only artefacts that the PRD does not mention:
- the `*/<pkg>.pack` files (9);
- root `Package`, `ProgramMake`, `Configure`, `Configure.sys`, `Dirlist`, `pck`, `dimvars`;
- `sptodp`, the m4/MPPL `define(...)` twin of `sptodp.h`;
- `builder/`: 136 files, with BASIS `std/` configs, `level_1`/`level_2` tests, and also the Python `Forthon_cases`;
- `dst/`, `idf/`, `psi/`, `std/` READMEs;
- `ncl/*.bas`;
- `uedge_executable/xuedge_static_V706_github.gz`;
- `README-Docker`, `README-FORTHON` (describes MPPL);
- `MANIFEST` (stale, lists `.m`, `localrules.py`, `convertor`);
- `com/glbwrlog.f` (BASIS-only, not in `Makefile.Forthon`);
- the non-`FORTHON` branches in `com/error.f:8,74` and `bbb/exmain.c:11,99,137`.

*Recommended PRD change:* add an explicit keep/delete/move inventory table for these, keeping `builder/test/Forthon_cases` (see M5) and `pyscripts/bas2py`. Make the §11 criterion refer to that table.

**P1-M7. Two `.m` files are converted but never compiled, yet they count toward "52/52".**
*Location:* §4 ("Convert each of the 52"); §7.2; §11.
*Evidence:*
- `bbb/s.m` (2,596 lines) is a stale near-copy of `bbb/ext_neutrals.m`: 82 diff lines, the same subroutine names, last touched in "Combines pandf1 into pandf1".
- `flx/dvshdf5.m` (762 lines) is commented out in `flx/Package:9` and uses `Use(hdf5_api)`, which no `.v` defines.
- Neither file is in `Makefile.Forthon`. Object and runtime checks cannot cover them.
- A frozen `s.F` added to the build later would duplicate symbols.

*Recommended PRD change:* get an owner decision, because deleting them conflicts with "no comment removed":
- either delete them (git history keeps them) with explicit owner sign-off;
- or freeze them and state that only the token and comment checks apply.

Then make the counts "50 built + 2 unbuilt", or whatever applies.

**P1-M8. On macOS, `.gitignore` `*.f` ignores the new `.F` sources.**
*Location:* §4 ("remove `*.F` from `.gitignore`"); §7.3 ("Keep `*.f`/`*.c`"); §11 ("`git status` clean").
*Evidence:*
- This repo has `core.ignorecase=true` (macOS default).
- In a scratch repo with `.gitignore` = `*.f`, `git check-ignore -v pandf.F` gives `.gitignore:1:*.f pandf.F`. The file is hidden from `git status` and only appears with `-c core.ignorecase=false`.
- On macOS, a new `bbb/foo.F` would need `git add -f`, and `git add -A` would silently leave it out. Linux CI would then fail.
- The "`git status` clean" criterion cannot see stale generated `.F` files.
- (Also: `.gitignore` has no "tracked exceptions"; tracked `.f` files are just force-added.)

*Recommended PRD change:*
- Add `!*.F` after `*.f`, or scope `*.f` to build outputs.
- Verify the change on macOS with `git check-ignore`.
- Phrase the cleanliness criterion as `git status --porcelain --ignored -- '*/'` showing no new `*.F`/`*.f`.

**P1-M9. The commit and mixed-tree plan has ordering hazards and contradicts itself on history.**
*Location:* §6 "History"; §12 Phase 2; §14 row 4.
*Evidence:*
- (a) `Makefile.Forthon:71` `find . -name \*.F -exec rm {} \;` runs on every default `pip install` (`setup.py:747-752`). The first per-package commit that tracks a `.F` gets that file deleted by the next build. The PRD lists the `clean` change as an unordered bullet; it must land in or before the first freeze commit.
- (b) §6 says to `git mv` *before* the conversion commit. Phase 2 says "each package is one commit: `git mv` ..., freeze ...".
  - A rename-only commit does not build, because raw MPPL ends up in `.F`.
  - `doc/workflow.md:206-209` asks for squash/one commit per PR, which merges the rename and the conversion.
  - With the current converter output, `git diff --no-index -M` already fails to detect `grd/grddriv.m→.F` as a rename (D+A), and `flx/flxdriv` is at R052, near the 50% default.
- (c) `git mv x.m x.F` fails with `fatal: destination exists` if a generated `.F` from an earlier build is present. Reproduced.

*Recommended PRD change:*
- Order the steps: `clean` fix and `.gitignore` fix first, then remove stale `.F`, then rename, then freeze.
- Prescribe the merge method for these PRs: a rebase-merge that keeps the rename commit and the freeze commit separate, not a squash.
- Add `.git-blame-ignore-revs` for the freeze commits.
- Document that rename-only commits do not build (use `git bisect skip`).

**P1-M10. The v8 to v9 backport stream is not addressed, and the tool it needs is scheduled for deletion.**
*Location:* §10 "Breaking for developers"; §7.1 "Lifetime"; §12 Phase 4 ("Equivalence tooling archived"); §14 row 5.
*Evidence:*
- `doc/workflow.md` §6: v8 (`develop`, MPPL) stays the default line, and fixes reach v9 **by cherry-pick only**.
- After AIUE-5, every v8 commit that touches `.m` hits modify/delete or rename+content conflicts on v9, for as long as v8 lives.
- The PRD covers only "open branches" and deletes `tools/mppl_freeze.py` at epic close.

*Recommended PRD change:*
- Keep the freeze tool (and the comment-aware lexer) as a supported tool.
- Document a backport procedure, e.g. apply the patch to the parent `.m`, freeze before and after, then apply the `.F` diff.
- Add it as a risk with an owner. Coordinate with the v8 maintainers.

**P1-M11. The AI layer and the tooling are out of step with the code during the epic. One more `.m` consumer is missed.**
*Location:* §7.5; §12 Phase 4.
*Evidence:*
- `.claude/context/branching.md` ("code-facts exception") requires AI-layer edits that describe changed code to ship **with the ticket that changes it**, "so the docs and the code never disagree on any branch". It names AIUE-5 and `mppl-fortran.md` as the example, using the `AI-layer: code-facts` trailer.
- The PRD defers all such edits to Phase 4. Between Phase 2 and Phase 4, the `CLAUDE.md` hard rule "Never edit generated `.F` files" forbids editing the new sources, and the skills (`execute`, `implement-fix`, `code-review`) tell agents to edit `.m`.
- `get_packages.py:159,266` reads `bbb/pandf_*.m` and `convert.m`, and splits on `#`, to generate the pointer lists in `ppp/omp_parallel.F90`. After the migration it finds no files.

*Recommended PRD change:*
- Each freeze ticket carries its matching code-facts AI-layer edit.
- The hard rule changes in the first freeze PR.
- Add `get_packages.py` (switch to `.F` and `!`), `README-FORTHON` and `.claude/skills/create-prd/SKILL.md` ("new `.m` files, `Package` registration") to scope.

**P1-M12. The lexer and fidelity-check spec is incomplete for constructs that exist in the sources, and the check can be fooled.**
*Location:* §6 "Recognising comments"; §7.1b.
*Evidence:* constructs the spec does not address:
- **String literals continued across lines** (6 pairs, e.g. `aph/aphread.m:465-466`, `bbb/griddubl.m:858-859`). The string state must carry over the continuation, or `'`, `#` and `!` get misclassified.
- **Existing `!` inline comments** (112 code lines, e.g. `api/fmombal.m:263`) and **`!` inside strings** (`aph/aphrates.m:1432`).
- **Tab-format lines**: 1,700 code lines have a tab in columns 1-6. `MoveDecs`/`Elseifthen` use `s[5]`, which is not column 6 there; e.g. `aph/aphrates.m:177` is classified as a continuation.
- **19 ordinary comments that begin with `c!`** in `ncl/ncl_driver.m`. The "`c!…`-style directive" wording is ambiguous.
- **PETSc-only comment lines**: `cpetsc*` (e.g. `bbb/odesolve.m:321`) and `cpetscc` (`svr/nksol.m:1083`).
- **Lower-case-only `c`** in the `MoveDecs` executable test (`setup.py:256`), which affects where `C` comments land.
- **Hollerith** constants (75, e.g. `svr/svrut4.m:2189`; none currently contain quotes).

How the check can be fooled:
- It compares "text without marker", so a `c`→`!` or `C`→`c` marker change, a full-line comment becoming inline (or the reverse), and whitespace normalisation all pass.
- The same recognizer runs on both sides, so a lexer bug cancels out.

*Recommended PRD change:*
- Add these constructs to the lexer spec and to the fixtures.
- Make the fidelity record `(routine, kind, marker, exact text)` and compare all four fields.
- Add an independent cross-check, so that a bug in the shared lexer cannot cancel out. For example, use a second, minimal implementation (column-1 marker count plus unquoted `!` count) whose totals must match the main checker's on both sides.

### Minor

**P1-m1. Inventory and line references are inaccurate.**
- `break`→`exit` matches 58 lines, not 85. The 85 are any line containing `break`.
- The only `(Size4)` is in a comment (`bbb/oderhs.m:1064`), so there is nothing to bake in.
- `Use(` is on 3,137 lines in 41 files.
- I count about 28.6k full-line comment lines by the column-1 rule, not ~26.7k.
- I cannot reproduce "~2,250 comment lines" with the tokens. I find about 50 token hits plus 382 comments with an extra `#`.
- `Makefile.Forthon:61` should be `:51`, and `:73` should be `:71`.
- The "bake in" list leaves out:
  - `grdproc` (3 `ifelse([WORDSIZE]` sites in `grd/grdread.m` and `grd/grdwrit.m`);
  - the `do_i1` rules;
  - the removal of `, allot` from `external` statements (`wdf/wdf.m:72,338`).
- Two of the "latent bugs" (§4 out-of-scope, §13) do not exist:
  - there is no `#` inside any code string literal;
  - `c!nopdbfloat` is correct, because `float→real` runs before `Nopdb`.

Make the fidelity tool compute the counts instead of hard-coding them.

**P1-m2. PETSc mapping and environment hazard.**
- Nothing defines a `PARALLEL` macro for `cunipetsc`; §7.3 only adds `HAVE_PETSC` and `HAVE_PACT`.
- Deriving `HAVE_PETSC` automatically from an ambient `PETSC_DIR` keeps a hazard: HPC users often have `PETSC_DIR` set, which turns on PETSc-only code that `Makefile.Forthon` doesn't link (`PETSC-COM` is empty).

Make PETSc an explicit opt-in, or document the hazard.

**P1-m3. Harness flags.**
- Use `-fopenmp` in the `-E` step rather than `-D_OPENMP`. `-fopenmp` defines `_OPENMP 201511` (verified); `-D_OPENMP` defines it as 1.
- Use the exact flags Forthon adds:
  - `-ffixed-line-length-132` (`Forthon/compilers.py:614`);
  - `-DFPSIZE`;
  - `-DISZ`;
  - `-fdefault-real-8`.

  Ideally, take them from the build log.

**P1-m4. Reference ref.** Compare against the exact parent commit of each freeze, not a moving `v9-develop`. Declare a `.m` code-freeze window on `v9-develop`, so that `.m` PRs merged mid-epic are not silently left behind.

**P1-m5. Converter state is shared across files.**
- The `M2F.subrules` instances are class-level, so state is shared across all files in `os.listdir` order. That order differs between APFS and ext4.
- `bbb/oderhs.m` ends with `MoveDecs.in_uses=1`, which leaks into the next file.
- I verified that converting each file with fresh state gives identical output to the batch run, for all 52 files in both serial and OMP.

Require fresh state per file in `mppl_freeze.py`, and record this check in the PR.

**P1-m6. Process.**
- The PRD sits untracked on `v9-agentic`, an AI branch. `create-prd`/`branching.md` place PRDs on `feature/v9-AIUE-5-planning`.
- The review path convention is `docs/reviews/AIUE-5-prd-round<N>.md`; this file uses the name the caller asked for.
- The estimates (2-3 days for Phase 1) look optimistic given M1-M3 and M12.
- "Tested locally with Forthon 0.10.10 and gfortran 15.2" (§8) cannot be verified, because nothing has been built yet.

**P1-m7. `Makefile.Forthon` `nclpydep`** has no `touch $@` and no `compydep` prerequisite. Fix it while editing that rule.

## Verified as correct (no action)

- **`_OPENMP` matches the `OMP` environment variable on every build path:**
  - default `pip install` (`-fopenmp` in FARGS, plus Forthon `--omp` adds it, `compilers.py:644-645`);
  - `--serial` (all three removed, `setup.py:734-738`);
  - `--debug`;
  - cibuildwheel (default OpenMP);
  - direct `make -f Makefile.Forthon` (serial, consistent).
- **Forthon** does not preprocess or read the sources itself, and it picks fixed form from the `.F` suffix (`Forthon_options.py:63`).
- **Case-folding:** no `.m` base name collides with a `.f` in the same directory.
- **cpp in traditional mode** (gfortran 15.2):
  - keeps `/* */`, `//`, `'`, `??=` and `##` in comments;
  - does not treat an indented `#` as a directive;
  - *does* expand macros inside comments (`Pi`, and `float`→`real` from `sptodp.h:44`). That is harmless for code, but the fidelity check must run on raw source, not on `-E` output.
- **Reference output sanity:**
  - all 52 reference `.F` files preprocess without warnings;
  - no `__LINE__`/`__FILE__`;
  - no code past column 132;
  - no `#` in column 6;
  - no column-1 `#` that looks like a cpp directive;
  - no `c#include`/`c#else` traps;
  - no non-`Use` code line containing `Use`.

## What was checked and how

- Extracted the exact converter section of `setup.py` (lines between the "CONVERSION OF MPPL FILES" banners) and exec'd it on a copy of the tree with `OMP=TRUE` and `OMP=FALSE`. Wrote the reference `.F` to a temporary directory.
  - Only `bbb/oderhs.F`, `bbb/odesetup.F` and `bbb/pandf.F` differ between the two configurations.
- Per-file fresh-state conversion compared with the batch run, plus end-of-file stateful-rule inspection (state leak in `oderhs.m` found, no effect).
- Comment-order comparison: the `.m` comment sequence, after the stateless per-line rules, against the reference `.F`. Result: 84 lines out of order, 17 files.
- Simulated `#ifdef` emission in the existing rule chain on `bbb/odesolve.m`, which misplaced `use PETSc_Snes_Param` after `implicit none`.
- `diff -D _OPENMP` merge of the serial and OMP outputs (`pandf`, `oderhs`, `odesetup`).
- gfortran 15.2 `-cpp -E` tests:
  - comments containing `/*`, `'`, `##`, `??=`, `Pi`, `float`;
  - an indented `#define`;
  - `-dM -fopenmp` shows `_OPENMP 201511`.
- Object test showing line numbers in `.text` (`objdump -d`) and in `-fcheck` strings.
- `git check-ignore` with `core.ignorecase=true` (`*.f` hides `pandf.F`); `git mv` onto an existing ignored `.F` (fails).
- `git diff --no-index -M` similarity between each `.m` and its reference `.F`: `grddriv` not detected as a rename; `flxdriv` R052.
- Scans of all 52 `.m` files:
  - tabs;
  - strings continued across lines;
  - `!` already in code;
  - Hollerith;
  - `c!` comments;
  - `elseif` without `then` followed by a comment;
  - `Use(...)` lines with parentheses in the comment;
  - decl-prefixed executables (`dataDir=` in `aph/aphread.m:24`);
  - `C$$$` lines.
- Inventory recount with the same patterns as the converter.
- Read:
  - `Makefile.Forthon`, `.gitignore`, `MANIFEST(.in)`, `pyproject.toml`;
  - both workflows;
  - the Forthon `compilers.py`/`Forthon_builder.py` excerpts;
  - `get_packages.py`;
  - `doc/workflow.md`;
  - `.claude/context/{architecture,mppl-fortran,testing,openmp-jacobian,branching}.md`;
  - `.claude/hooks/change_kind.py`;
  - `create-prd/SKILL.md`;
  - an `origin/pytests` test and input file;
  - `builder/test/level_{1,2}/do-test`;
  - `bbb/Package`, `flx/Package`, `com/Package`, `svr/Package`.
- Not done: no UEDGE build or regression run (not needed for a PRD review). The PRD's Forthon/gfortran "tested" claim was not reproduced.
- Scripts: `$TMPDIR/aiue5/scripts/{runconv,perfile,comment_order,scan,inventory,sim_ifdef}.py`, outside the repo.
