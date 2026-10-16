# AIUE-64 implementation – response to review round 1

Review: `docs/reviews/AIUE-64-implementation-round1.md` (REVISE, 0 BLOCKER / 1 MAJOR / 3 MINOR) on `a738e92`.
All four findings are fixed in records and text only. No code changed, and I ran no builds or runs.

The commit that adds this response changes only docs and the plan. That makes the `AIUE-64-*` builds stale for
`serial_check.py`, but M3 already ran on builds of `1e8eb78` with a clean tree, before any later commit. The product
tree is still the `1e8eb78` one, so M3 stands.

| Finding | Response | Where |
|---|---|---|
| I1-M1 M4 not green and missing from the record | **Fixed.** I added an M4 row and an "M4 in detail" section, marked as deviating from the pre-registered expectation and identical on base. It covers: the 5 `D_only` failures by name and the `ValueError`; the base comparison (identical `FAILED` lists and fnrm lines, fnrm lines quoted verbatim); the `RuntimeError: diff in rhsnk` with rows 272 (1.17e-11) and 428 (4.38e-9) verbatim; the 3 alternating repeats on fix and base, identical; the two one-off exits (133, `gtimeout` SIGTRAP, with its crash report quoted; 139, once, no crash report found); and the attribution "consistent with AIUE-58 R1 (RHS check; Jacobians identical; both rows Ti rows at (ix=2,iy=1) and (ix=14,iy=1) by the 13-per-cell ordering), not shown". New small text files back the row: `validate/d_only.txt`, `validate/omp_check.txt`, `validate/one_off_exits.txt` and `validate/build_smoke.txt`, plus `scripts/omp_check.py` and `scripts/omp_repeat.sh`. The same text is ready for the PR description in `docs/reviews/AIUE-64-pr-notes.md`. | `docs/rca/AIUE-8-data/linux/aiue64/README.md`, `.../validate/`, `docs/reviews/AIUE-64-pr-notes.md` |
| I1-m1 macOS "before" build commit | **Fixed.** The README says the macOS "before" build is at `1adea93`, whose product tree is identical to `4faed39`; the `git diff` is quoted and was re-checked as empty. | README, Commits |
| I1-m2 Amendment sentence; 5× chosen after the diagnostic | **Fixed.** The pre-registered amendment text is kept as written. A post-run note under it says that "no region during `exmain`" was inaccurate (control workers gained 5.3 ms and 6.0–10.3 ms; the margin covers it), and that the 5× factor was picked after the diagnostic had shown rough magnitudes. The README's L5 row carries both caveats and the ratios (10.1×, ≥ 8.0×). | Plan L5 (post-run note); README L5 row |
| I1-m3 Log-line checks rest on uncommitted logs | **Fixed.** `build_log_line.txt` records `grep -c` of the new log line in each of the 14 build logs (Linux and macOS), with the matching line where present. The README has a row for it and says the logs are not committed. | `.../aiue64/build_log_line.txt`; README |
