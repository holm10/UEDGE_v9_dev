# Review: AIUE-5 PRD "Switch to pure Fortran build" (stage: prd, round 5)

- **PRD:** `docs/prds/AIUE-5-switch-to-pure-fortran-build.md`, revision 6 (worktree `uedge-wt/AIUE-5`, branch `feature/v9-AIUE-5-planning` @ 4e531df; PRD untracked).
- **Inputs:** round-4 review (`AIUE-5-prd-round4.md`) and response (`AIUE-5-prd-round4-response.md`).
- **Binding decisions:**
  - retire MPPL and BASIS, keep `.v` + Forthon;
  - free-form `.F90` for the 50 MPPL-derived files only;
  - serial + OpenMP only, PETSc/PACT removed (incl. comment lines, `petscoptfile`/`petscopts`);
  - tolerant `hdf5_restore_dump`;
  - "unchanged" = same parsed program + exact numbers, and FORMAT strings that differ only in insignificant blanks count as the same program (new);
  - uniform 3-space indentation from a pinned converter (new);
  - no comment information lost;
  - delete `bbb/s.m`, `flx/dvshdf5.m`;
  - `gengrid=1` test before the BASIS CI goes;
  - AI-layer branch policy.

  I did not reopen any of them.

## Verdict

**APPROVE**

## Summary

Revision 6 resolves all three round-4 MAJOR findings, and I re-checked each fix myself.
- **FORMAT check.** I re-ran the proposed check on real sources: `-fdump-tree-original` format strings, with blanks outside character/Hollerith data removed and data blanks kept. It catches both round-4 mutations in `svr/svrut1` (`58h`→`57h`, `99i1`→`98i1`), a moved blank inside Hollerith data and a shifted Hollerith boundary. It accepts the padding-only free-form output and a blank-only change between descriptors. Across the 49 compilable files (637 format use sites) it passes with no false positives, provided TAB is treated as whitespace.
- **Stale `.F`.** The clean rule is kept, and gate 2 now uses a fresh worktree.
- **Comment gate.** The `.m` side now has an independent extractor.

Three new MINOR points remain, all about the new text:
- the FORMAT check must treat TAB as whitespace;
- 13 FORMATs, holding 39 of the 51 Hollerith descriptors, have no use site, so they never reach the tree dump;
- the stale-`.F` guard as worded conflicts with Phases 0-1 and `--noclean`.

No BLOCKER or MAJOR is open.

## Findings

### Blocker

None.

### Major

None.

### Minor

**P5-m1. The FORMAT check must treat TAB as insignificant whitespace, not only blanks.**
*Location:* §7.2 "FORMAT check"; decisions table, "Default results"; §11 FORMAT criterion.

*Evidence:*
- `api/fmombal.m` writes continued FORMATs with a tab after the column-6 marker, for example line 693: `     >\t' NOTE: RESULTS …'`. gfortran stores the TAB inside the format string. The tree dump shows `…1pe10.3,/,<padding>\t\' NOTE: …`.
- The free-form output has no tab there.
- With a spaces-only normaliser, 6 of the 9 `fmombal` format strings differ, and the check fails. With TAB treated as whitespace outside data, all 49 files pass.
- The difference is runtime-insignificant. A scratch program with `format(1pe10.3,` / `>\ti5,` / `>\t'|x')` printed byte-identical output to `format(1pe10.3,i5,'|x')`.
- The failure is loud, not silent. It is fixed-form layout inside a continued FORMAT, which is what the owner decision's parenthetical describes, but the decision says "blanks".

*Acceptance:* §7.2 (and the decision wording, if the owner agrees) says "blanks and tabs outside character/Hollerith data". The tree-dump `\t` escape is decoded before normalising. A tab *inside* character/Hollerith data stays significant.

**P5-m2. FORMATs with no use site never reach the tree dump, so "all 256 FORMATs" and "all 51 Hollerith descriptors" are not checkable as stated.**
*Location:* §7.2 ("256 FORMATs, including all 51 Hollerith descriptors, need their own check"); §11 ("all 256 FORMATs are identical apart from insignificant blanks").

*Evidence:*
- `-fdump-tree-original` emits a format string only at each I/O statement that uses it (`dt_parm.N.format = &"…"`). It has no label, and FORMAT 908 in `svrut1` appears twice.
- `gfortran -Wunused-label` on the reference reports 13 FORMATs with no use site:
  - `svr/svrut4` 101-110 (10 statements);
  - `bbb/oderhs` 77;
  - `bbb/odesetup` 110;
  - `flx/flxread` 1050.
- The `svrut4` ones hold 39 of the 51 Hollerith descriptors, so the check sees only about 12 of them.
- These FORMATs are dead code, so the compiled program and numbers cannot change through them. That is why this is MINOR. But a converter edit inside one, such as a count or descriptor change that stays syntactically valid, is invisible to every gate. The parse dump omits FORMATs, and the tree dump omits unused ones.

*Acceptance:*
- The PRD states that the tree-dump check covers FORMATs with a use site.
- The Phase 0 scan lists the unreferenced ones.
- Those are either compared another way (for example the same normaliser applied to the FORMAT text, or a scratch harness that references them) or explicitly accepted as dead code, with §11 reworded to match.

**P5-m3. The stale-`.F` guard as worded fires on legitimately generated `.F` files in Phases 0-1, and its order relative to `clean` is unspecified.**
*Location:* §4 "Stale `.F` guard" ("`setup.py` refuses to build while any `<pkg>/*.F` exists"); §12 Phase 0 (guard delivered in Phase 0); §11 ("refuses a build with a planted `<pkg>/x.F`").

*Evidence:*
- `uedgeBuild.run` runs `make clean` (unless `--noclean`, documented at `README.md:86`), then `mppl2f90()`, which writes `<pkg>/*.F` in-tree for every package still in `dirlist` (`setup.py:753-761`). Until the last Phase 1 PR, every build therefore leaves `.F` files behind.
- The two possible placements fail differently:
  - **Before `clean`:** the guard refuses every second build.
  - **Between `clean` and `mppl2f90`:** the guard refuses every `--noclean` build from Phase 0 onward.
- Conversely, in a normal (cleaning) build, `clean` deletes the planted file before a later-placed guard sees it. The §11 criterion then depends on placement.
- The failure is loud and the fix is simple, so this is MINOR.

*Acceptance:* the PRD fixes two things:
- **Scope:** the guard fires on `<pkg>/x.F` only when `<pkg>/x.F90` exists, or only for packages no longer converted.
- **Position:** relative to `clean` and `mppl2f90`.

The negative control then states which build mode it exercises.

## Status of previous findings (round 4)

| ID | Status | Evidence (re-checked on revision 6) |
|---|---|---|
| P4-M1 | **Resolved** | §7.2 states that the parse dump omits FORMATs and adds a tree-dump check independent of the converter. The owner chose option (b) (decisions table, §6.3 row). **Experiment:** reference `svrut1` vs free form: PASS (raw strings differ in 2/9, normalised identical). `57h`: FAIL; `98i1`: FAIL; a moved data blank (`58h dependent`→`58hdependent `): FAIL; a shifted Hollerith boundary: FAIL; `(11x,  99 i1)`: PASS. All 49 compilable files PASS (637 use sites; raw differences in `fmombal`, `flxcomp`, `grdcomp`, `nksol`, `svrut1`, `uoa`, `wdf`, `odesetup` vanish after normalising). `bbb/oderhs` free form doesn't compile (the known `ticktock` defect). No FORMAT or WRITE is in an OpenMP-only branch, so a serial-only check is complete today. Residuals: P5-m1, P5-m2 |
| P4-M2 | **Resolved** (guard detail in P5-m3) | `clean` keeps the `*.F` deletion (`Makefile.Forthon:71`, safe: `git ls-files '*.F'` is empty). Gate 2's after-run uses a fresh worktree and asserts no `<pkg>/*.F` (§7.5), with a planted-`.F` negative control and a §14 row |
| P4-M3 | **Resolved** | §7.3 adds a separate line-based `.m` extractor with no column limit and no shared code. The input-side controls cover truncation at column 132 and a dropped indented line. I asked for a `c$$$` input control; the exact exception list covers it instead, because the 8 listed `! $$$` exceptions must each occur (§6.4 req. 4), so a misclassified `c$$$` fails. I accept this |
| P4-m1 | **Resolved** | §4 and §11 apply ≤ 132 to code after cpp, and comments keep their full text. Residual wording: `bbb/pandf_plasma_momentum.m:408` is a 71-character code part with a trailing comment (141 total), which must stay on its line (§6.4 req. 2). The length check should measure the code part only. It compiles with `-ffree-line-length-132 -Werror=line-truncation` (verified on a 138-character analogue) |
| P4-m2 | **Resolved** | Owner decision (3-space indentation). The converter is version-pinned (§6.3), and blame is covered. Residual: §4 "Out of scope: Reformatting … beyond the form change" should say "apart from the uniform indentation" |
| P4-m3 | **Resolved** | §6.3 row (731: 715 `#`, 16 `!`) and §6.4 req. 1 |
| P4-m4 | **Resolved** | §7.2: same module set built from the PR's `.v`. No `.m` code uses `petscoptfile`/`petscopts` (`git grep`: only `bbb.v:157-158`, `bas2py_rules.py:109-110`, `svr/petsc-uedge.F90`, which goes in Phase 0), so the parent reference compiles against the new modules |
| P4-m5 | **Resolved** | §6.3 row: `external ticktock`, listed for a follow-up ticket |
| P4-m6 / P2-m1 | **Resolved** | §4 lines verified: `get_packages.py:159,266,466` (`.m` filter), `:162,519,572` (column-1 `c` rule), `:164,521,574` (split on `#`), `:484` (`bbb.v`). The identity check is in §4 and §11 |
| P4-m7 | **Resolved** | "The suffix selects the form" in §4, §6.1 and §7.2. Column 6: "any non-blank, non-zero character" with 14 characters. AI layer merged (`0fac655`) |

## What was checked and how

All scratch work is in `$TMPDIR/aiue5r5/`, outside the repo, plus the round-4 artefacts in `$TMPDIR/aiue5r4/`:
- the unmodified-converter reference;
- findent 4.3.6 free form;
- Forthon modules with `ISZ=8`.

I did not build or install UEDGE and did not run the regression suites.

- **FORMAT check (P4-M1).**
  - Wrote `scripts/fmtcheck.py`. It extracts `.format = &"…"` strings from `-fdump-tree-original` (location strings normalised as in round 4), decodes the escapes, and removes whitespace outside quoted strings and Hollerith data. The Hollerith count is parsed from the compiled string on each side independently.
  - Ran it on `svrut1` against 5 mutants:
    - the two round-4 mutants;
    - a data-blank move;
    - a Hollerith boundary shift;
    - a descriptor-blank change.
  - Ran it on all 50 files, serial.
  - Re-ran with spaces only, to find the TAB case. Then checked the TAB's runtime effect with a scratch fixed-form program.
- **Coverage.**
  - Ran `gfortran -fsyntax-only -Wunused-label` on all 50 reference files to list FORMATs without a use site.
  - Checked `svrut4` FORMATs 100-110 against their uses (`write (indfmt,100)` at `svrut4.m` ~2199; the others are duplicated as character constants assigned to `ix`, which gate 1 covers).
  - Ran a serial vs OpenMP converter-output diff for `oderhs`, `odesetup` and `pandf`: no I/O lines in OpenMP-only code.
- **Stale `.F` (P4-M2).** Read `setup.py:36-60,686-772` (order of `clean` → `mppl2f90` → `make`), `Makefile.Forthon:64-76`, `README.md:86`, and ran `git grep noclean`.
- **Line length (P4-m1).** Measured `bbb/pandf_plasma_momentum.m:408` and compiled a free-form code line with a trailing comment to 138 characters, under the default flags and under `-ffree-line-length-132 -Werror=line-truncation`.
- **Other claims:** `git grep -i 'petscoptfile\|petscopts'`, the `get_packages.py` line numbers, and the §15 review-history counts.
- **Changed text read in full:** the decisions table, §1, §4, §6.1-§6.4, §7.1-§7.5, §8, §11, §12, §14 and §15. No other BLOCKER/MAJOR issue found.
