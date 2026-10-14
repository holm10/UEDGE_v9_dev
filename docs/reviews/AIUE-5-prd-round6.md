# Review: AIUE-5 PRD "Switch to pure Fortran build" (stage: prd, round 6, confirmation only)

- **PRD:** `docs/prds/AIUE-5-switch-to-pure-fortran-build.md`, revision 7 (worktree `uedge-wt/AIUE-5`, branch `feature/v9-AIUE-5-planning` @ 4e531df; PRD untracked).
- **Inputs:** round-5 review (`AIUE-5-prd-round5.md`, APPROVE with 3 MINOR) and response (`AIUE-5-prd-round5-response.md`).
- **Scope of this round:** confirm the revision-7 edits for P5-m1, P5-m2, P5-m3 and the P4-m1/P4-m2 wording residuals, and check that they introduce no BLOCKER or MAJOR. The owner's binding decisions were not reopened, and no other material was re-audited.

## Verdict

**APPROVE**

## Summary

Revision 7 resolves P5-m1, P5-m2 and both P4 wording residuals as asked.
- **P5-m1:** the FORMAT check now treats tabs as insignificant whitespace.
- **P5-m2:** the 13 unused FORMATs get a source-level comparison, and §11 now matches what can be checked.
- **P5-m3:** the guard's position and scope are now fixed correctly: after `clean` and `mppl2f90()`, before `make`, and only for an `x.F` that has an `x.F90` twin. This fits the real `setup.py` order and the `Makefile.Forthon` clean rule. One part of the round-5 acceptance is still open: the negative control does not state which build mode it uses. §14 also still uses the old wording. Both are small, so I mark P5-m3 partially resolved and do not raise a new finding.

No new BLOCKER or MAJOR problem.

## Findings

### Blocker

None.

### Major

None.

### Minor

No new MINOR findings (out of scope for this round). The residual on P5-m3 is described under "Status of previous findings".

## Status of previous findings

| ID | Status | Evidence (checked on revision 7) |
|---|---|---|
| P5-m1 | **Resolved** | The decisions table "Default results" row now says "insignificant whitespace (blanks or tabs outside character/Hollerith data, such as fixed-form padding and tab-formatted continuations inside continued FORMATs)". §7.2 removes "whitespace (blanks **and tabs**) that is insignificant under the Fortran format rules", cites `api/fmombal.m:693`, and keeps blanks inside character/Hollerith data. A tab inside data is still kept, because the rule removes only *insignificant* whitespace. §11 says "insignificant whitespace". Decoding the tree-dump `\t` escape is not mentioned, but any working implementation has to do it. **Note for the main session:** the author reworded a binding owner decision ("blanks" became "blanks or tabs"). The response says the owner is told about this. The owner should confirm the wording explicitly before publication. This is a decision record, not a PRD defect |
| P5-m2 | **Resolved** | §7.2 lists the 13 unused FORMATs (`svr/svrut4` 101-110, `bbb/oderhs` 77, `bbb/odesetup` 110, `flx/flxread` 1050; 39 of the 51 Hollerith descriptors). It compares them at source level, `.m` text from the independent extractor vs `.F90`, under the same whitespace rule. §11 now says "all used FORMATs (via the tree dump) and the 13 unused ones (at source level)". Soundness: I read all 13 statements (`svrut4.m:2190,2221-2223,2248-2253`, `oderhs.m:4633`, `odesetup.m:7200`, `flxread.m:285`). Each is a single line with no continuation and no MPPL-substituted token (`#`, `float`, `break`). So a Hollerith-aware normaliser on the source text, the same algorithm as on the compiled strings, compares them directly. The OpenMP-branch fact is recorded, and the check now fails if a FORMAT/WRITE ever appears inside `#ifdef _OPENMP` |
| P5-m3 | **Partially resolved** | **Position and scope: resolved.** §4 places the guard after `clean`, after `mppl2f90()` and before `make`, and it fires only on `<pkg>/x.F` next to `<pkg>/x.F90`. This matches `setup.py:753-770` (clean at 755, `mppl2f90()` at 761, `make` at 770). `mppl2f90()` output for unconverted packages never has a `.F90` twin, so normal and `--noclean` builds are unaffected, as §4 and §11 state. **Residual 1 (build mode of the control):** in a normal build, `make clean` runs `find . -name \*.F -exec rm {} \;` (`Makefile.Forthon:71`). That deletes a planted `x.F` before the guard runs, so the §11 refusal control can fire only in a `--noclean` build or with the file planted after `clean`. §11's "(normal and `--noclean` builds)" grammatically belongs to the "does not fire" half, so the round-5 request that the control state its build mode is not met. The failure is loud (the control would simply not trigger), so this is not a new finding. **Residual 2:** the §14 row "A leftover generated `.F` …" still reads "`setup.py` refuses to build while one exists", which conflicts with the narrower §4 rule. §4 is authoritative. **Advisory:** "tracked `x.F90`" should be implemented as "an `x.F90` exists in the source tree", not through `git ls-files`. Builds from an sdist or other non-git tree must still work. Suggested one-line fixes: §11 "…refuses a `--noclean` build with a planted…", and the §14 mitigation text aligned with §4 |
| P4-m1 (wording residual) | **Resolved** | §4: "the **code part** of each line (excluding a trailing `!` comment) is wrapped to ≤ 132 characters after cpp expansion". §11: "No `.F90` line has a code part longer than 132 characters after cpp expansion … comments keep their full text". This covers `bbb/pandf_plasma_momentum.m:408` (a 71-character code part plus a trailing comment) |
| P4-m2 (wording residual) | **Resolved** | §4 out-of-scope now reads "Reformatting or modernizing beyond the form change and the uniform 3-space indentation" |

## What was checked and how

- Read the round-5 review and response, and the revision-7 text of:
  - the decisions table and revision history;
  - §4 "Build and repository" and "Out of scope";
  - §7.2 and §7.5;
  - §11, Phase 0 of §12, §14 and §15.
- `sed -n 60,76p Makefile.Forthon`: the `clean` rule deletes every `*.F` under the tree unless `NOCLEAN`.
- `grep -n` on `setup.py`: order `make clean` (755) → `mppl2f90()` (761) → `make` (770), and the `noclean` handling (689-709, 753).
- Read the 13 unused FORMAT statements in the `.m` sources to confirm that a source-level comparison is feasible.
- Listed `.github/workflows/` (only `build-test-wheel.yml` builds with `pip install .` / cibuildwheel), for the "tracked" advisory.
- No experiments were re-run. None of the fixes depends on new experimental evidence; the round-5 FORMAT-check experiments already cover the tab rule.
