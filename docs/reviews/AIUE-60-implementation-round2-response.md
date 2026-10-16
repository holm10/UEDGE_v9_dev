# AIUE-60 implementation review round 2 — response

Review: `docs/reviews/AIUE-60-implementation-round2.md` (APPROVE, 0/0/2 optional minors). Both minors and the optional
plan cleanups are done; no rebuilds.

| Finding | Resolution | Where |
|---|---|---|
| I2-m1 rule-5 heading / checklist 4 say "only in `bbb`" | Reworded to the actual invariant: no threadprivate scalars in a package loading before `bbb`, no later block larger than `bbb`'s; `api` (12 scalars, 96 B) named as an allowed later, smaller block; new scalars go in `bbb`. Drift check OK | `openmp-jacobian.md` rule 5, `variables-forthon.md` checklist 4 (code-facts commit) |
| I2-m2 common check fails open on a stripped ELF `.so` | ELF path uses `nm -D -S` (dynamic symbols); a nonzero `nm` exit or empty listing is ERROR; "no definer at all" is ERROR. Re-run on the existing venvs: AIUE-60-omp PASS, AIUE-60-omp-pre FAIL, AIUE-56-omp PASS, AIUE-60-serial ERROR (no definer) | `AIUE-60-common-check.py`, `AIUE-60-common-check-r2.txt` |
| Optional plan cleanups | Task 4 passed-args now states 137 → 135 before and 137 → 145 after Amendment 1; G-common sizes are "each sized by its declared `kind=`" instead of "× 8 B" | Plan |
