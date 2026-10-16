# AIUE-60 plan amendment 1 review — response

Review: `docs/reviews/AIUE-60-plan-amendment1-review.md` (REVISE, 0 blockers / 4 major / 6 minor; design confirmed).

| Finding | Resolution | Where |
|---|---|---|
| LA1-M1 G-iotable "0 changed words" fails on correct code | Accepted. The gate is now differential: the amended build's before/after states of all 128 words must equal AIUE-56's in each of 2 repeats, and AIUE-56 must be repeatable (else ERROR). Controls run: AIUE-56 changes exactly {11: 0→1, 12: 0→1} in 2/2 repeats (repeatable); the pre-amendment build changes 62 words in 2/2 → FAIL | Plan Amendment 1 G-iotable; `AIUE-60-iotable-probe.py`; `AIUE-60-amendment1-controls.txt` |
| LA1-M2 negative controls lost on rebuild; size source | Accepted. Before any rebuild: the pre-amendment venv was copied to `venvs/AIUE-60-omp-pre` and its generated `*_p.F90` to `logs/AIUE-60/pre_amend_gen/`, and both negative controls were run on them (outputs committed). G-common takes the generated-source directory as an argument tied to the checked build and fails closed (ERROR) on a definer without a size or a missing `.so` | Plan Amendment 1; `AIUE-60-common-check.py`; controls file |
| LA1-M3 scripts not committed | Accepted. `AIUE-60-common-check.py` and `AIUE-60-iotable-probe.py` are committed with this response, with the control outputs (AIUE-56 PASS; pre-amendment FAIL; AIUE-56 iotable positive control) | `docs/reviews/` |
| LA1-M4 plan body / AI layer state the superseded design | Accepted. Row A4, B4, Task 1 (header, IMPLEMENT, VALIDATE), Default-results 4, Task 5 (rule-1 sentence rewrite plus the new invariant, also in `variables-forthon.md`), and the acceptance checklist (146/147/145 and the Amendment-1 gates) are updated or marked superseded | Plan |
| LA1-m1 pin `acctim`; TSan doesn't see the CAS | Accepted. The exact helper text is in the plan (no `Use`; directive directly above the assignment). New G-atomic gate: the generated `com/misc.F` has `c$omp atomic` directly above `acc = acc + dt`; `otool -tV` of the OpenMP `_acctim_` shows a CAS/LL-SC loop and the serial build a plain `fadd`. The TSan wording is corrected | Plan Amendment 1 |
| LA1-m2 load order, kinds, Linux | Accepted. The script parses the import order from `uedge/__init__.py` (includes `uedgeC` and `ncl`), sizes the block from the declared `kind=` of each copy variable, and uses `nm -S` on Linux (`nm -m` on macOS) | `AIUE-60-common-check.py` |
| LA1-m3 Probe S reachable units | Accepted: 145 → 146 pre-registered | Plan Amendment 1 |
| LA1-m4 timer semantics, timing flag | Accepted. Timers are thread-seconds summed over threads under OpenMP (plan, `openmp-jacobian.md`, PR; `com.v` doc strings stay at their base text). A >10 % timing flag is reported to the owner as a decision (accept, or guard the hot-path updates with `istimingon`); it doesn't block | Plan Amendment 1, Task 5 |
| LA1-m5 `aph.iflag_aph` no longer updated | Accepted. Recorded in the plan; it will be in the PR | Plan Amendment 1 |
| LA1-m6 Forthon text (2) | Accepted. Reworded (`split('(')[1].split(')')[0]`: a nested `(` truncates the bound); references **AIUE-71** | Plan Amendment 1 |
