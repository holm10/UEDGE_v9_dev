# Response to the AIUE-57 rework plan review, round 1 (REVISE 0/2/8)

Report: `docs/reviews/AIUE-57-rework-plan-round1.md`. Plan: `.claude/plans/AIUE-57-omp-ci-job.md`, Amendment 1,
new subsection "Revision 1". Decisions relayed by the main session: keep the tolerance mode, keep `up1`, V6 with the
`ppp` field emptied (documented), docstring-only note on `AIUE-56-c1-gate.py`; revise, then implement directly (the
implementation review covers the revision).

| Finding | Response |
|---|---|
| L1-M1 | Accepted. The common-block check never stops the script; its code goes to `report.py --common-code`, shown in the headline block and folded into the exit code (`max`). Package-dir lookup failure = exit 2. Unit test: common FAIL + flows PASS → exit 1 with a FAIL headline. V6c runs inside V6. |
| L1-M2 | Accepted. Unit tests (i) Jacobian-only, deterministic, bound FAIL → FAIL; (ii) missing `bound.json`/group/run → exit 2. New V8b: tolerance below the measured macOS C2 deviation → exit 1. |
| L1-m1 | Accepted. Tolerance mode recomputes the gated exit code from adjusted verdicts, keeping ERROR/iteration/bound-2/common codes. Tolerance capped at 1e-6. |
| L1-m2 | Accepted. Plan and README state that in `--itermx` flows the bound sees only the last, permuted Jacobian. V6 outcomes pre-registered per group (bound for `tebox`/`full` and `up1` recorded). `jac_bound.py` exits 2 on a `post_exmain_permuted`/`post_exmain_from` disagreement. |
| L1-m3 | Accepted. Fail closed on missing `bound.json` or entries and on tracebacks; layout test; `--harness` accepted in check-dir mode; one-line note in `linux/README.md`. |
| L1-m4 | Accepted. Te-box `ppp` adds `"OMPJacVerbose": 1`; `report.py` lists the `NchunksJac` values seen in `run.log`; V5 pre-registers 25. |
| L1-m5 | Accepted as optional V11 (`up1` with `OMPJacFixedChunks=0` on the tip in Docker, recorded). Seeded-C1 control not planned. |
| L1-m6 | Accepted. Estimate 15–22 min (central ~18); cut order `up1` → `tebox` K 5→3 → `full` at 4 threads; merge condition in README/PR notes. |
| L1-m7 | Accepted (`:7-13`; `openmp-jacobian.md:116` also names `ci/common_check.py`). |
| L1-m8 | Not on this branch (AI layer); the main session handles it. |
