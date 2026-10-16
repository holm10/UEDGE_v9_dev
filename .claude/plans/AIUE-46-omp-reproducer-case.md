# Feature: AIUE-46 — Commit the OpenMP reproducer case

## Summary
**Type**: Python/Build (test data and tooling; no Fortran)
**Complexity**: Low
**Default results**: Unchanged (no product code touched)
**Packages / files**: `tests/deterministic_omp/**`, `.claude/context/testing.md`, `CLAUDE.md`
**Branch / worktree**: `feature/v9-AIUE-46-omp-reproducer-case` @ `../uedge-wt/AIUE-46` (base: `origin/v9-develop`)

## Problem and solution
The owner's reproducer lives untracked in a local `tests/deterministic_omp/`, with an 11.7 MB save file, scratch
output and a hard-coded, commented-out rate path. Commit a trimmed, self-contained copy that every later AIUE-8
ticket (harness, serial check, CI) can run from a clean checkout.

## Decisions
- **Layout:** `case/` holds the deck, the data and the owner's scripts (they `import input_mod4` from the working
  directory, so they must sit next to it); `tools/` holds the trim and fingerprint scripts; `README.md` at the top.
- **Rate files:** `ehr2.dat` and `C_rates.adas` are already tracked in `builder/test/Forthon_cases/Forthon_case5/`
  (byte-identical to the owner's copies). The deck points there by default, relative to its own file, with the
  override `UEDGE_OMP_RATES_DIR`. No download or new data. This corrects PRD §6.3/§7.1 ("the repo does not bundle").
- **Trim:** keep only what the deck and `hdf5_restore` read (see `tools/trim_case_data.py` docstring). `gridue.hdf5`
  and `mist.dat` stay as they are. Total 4.5 MB (target ≤ 5 MB), so no Git LFS.

## Tasks
1. CREATE `case/` with the deck, data, owner scripts. VALIDATE: `ls`, sizes.
2. UPDATE `case/input_mod4.py`: rate directories, with existence and length checks (`aphdir`/`apidir` are
   `character*120`). VALIDATE: Te-box run from inside the tree without the variable; run with a bad directory fails.
3. CREATE `tools/trim_case_data.py`, `tools/fingerprint.py`. VALIDATE: original vs trimmed fingerprints and printed
   `fnrm` lines identical for full problem, Te box, `itermx=3` (`docs/reviews/AIUE-46-validation.txt`).
4. CREATE `README.md`, `.gitignore`.
5. Code facts (`AI-layer: code-facts`): `testing.md` line 3, `CLAUDE.md` regression-tests comment.

## Acceptance criteria (ticket)
- [ ] Trimmed data bitwise equal to original (serial yldot, Jacobian, fnrm) — task 3
- [ ] Runs from a clean checkout with only the documented environment, `python -I`, empty `HOME` — task 2
- [ ] Committed size reported — validation file
- [ ] Code facts updated — task 5
