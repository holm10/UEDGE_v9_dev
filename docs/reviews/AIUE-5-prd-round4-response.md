# Response to review round 4: AIUE-5 PRD

PRD revision 6: `docs/prds/AIUE-5-switch-to-pure-fortran-build.md` on `feature/v9-AIUE-5-planning`.

## Owner decisions taken because of this review (binding)

| Finding | Decision (epic owner, 2026-10-14) |
|---|---|
| P4-M1 FORMAT padding | Format strings that differ only in insignificant blanks count as the same program. Stage 2 does **not** write out fixed-form padding. A dedicated FORMAT check proves everything else is identical |
| P4-m2 indentation | One uniform indentation (3 spaces per block level), applied by the pinned converter |

## Findings

| ID | Status | Where in rev. 6 |
|---|---|---|
| P4-M1 | Fixed. The PRD states the parse-dump gap. A FORMAT check on `-fdump-tree-original` format strings (file/line normalised) runs independently of the converter, comparing with insignificant blanks removed and data blanks kept. Negative controls on real `svr/svrut1` FORMATs (Hollerith count, edit descriptor, a data blank). Owner decision on the padding | Decisions, §6.3, §7.2, §11, §14 |
| P4-M2 | Fixed. `clean` keeps deleting `<pkg>/*.F`. `setup.py` refuses to build while one exists. Gate 2's after-run uses a fresh worktree and asserts no `.F`. A planted-`.F` negative control | §4, §7.5, §11, §14 |
| P4-M3 | Fixed. The fidelity check extracts `.m` comments with its own line-based extractor (no column limit, no code shared with the converter's lexer). Input-side negative controls: truncation at column 132, a dropped indented comment-only line | §6.4, §7.3 |
| P4-m1 | Fixed. The ≤ 132 limit applies to code lines after cpp, checked by the tool. Comment lines keep their full text | §4, §6.3, §11 |
| P4-m2 | Fixed. `findent` is version-pinned and wrapped. Uniform 3-space indentation (owner decision). Re-indentation covered by `.git-blame-ignore-revs` | Decisions, §6.3, §14 |
| P4-m3 | Fixed. The 731 indented comment-only lines are in the taxonomy and in requirement 1 | §6.3, §6.4 |
| P4-m4 | Fixed. Both sides of gate 1 compile against the same Forthon modules built from the PR's `.v` | §7.2 |
| P4-m5 | Fixed. Split tokens are joined to the token fixed form meant (`external ticktock`) and listed for a follow-up ticket | §6.3 |
| P4-m6 / P2-m1 | Fixed. The free-form comment rule at `get_packages.py:162,519,572`, plus a before/after identity check on the generated pointer lists | §4, §11 |
| P4-m7 | Fixed. "The suffix selects free form" (no `-ffree-form`). Any non-blank, non-zero column-6 character counts as a continuation. AI layer marked merged (`0fac655`) | §4, §6.1, §6.3, §7.2 |
| P2-m6 follow-up (`c$$$` → `!$`) | Fixed. Comments starting with `$` become `! $…`, never `!$`, and are listed as an exception | §6.3 |
