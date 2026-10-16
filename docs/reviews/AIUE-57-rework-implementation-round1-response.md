# Response to the AIUE-57 rework implementation review, round 1 (APPROVE 0/0/6)

Report: `docs/reviews/AIUE-57-rework-implementation-round1.md`. All six minors fixed as directed by the main session.

| Finding | Fix | Test |
|---|---|---|
| I1-m1 nothing to judge passes | `jac_bound.py`: a jac group without run directories is a group error (flow mode), a check directory without `run*` is "cannot judge" (check-dir mode); both exit 2 | `test_nothing_to_judge_is_exit_2` |
| I1-m2 `gate_summary.py` vs `jac_bound.py` | `linux/README.md`: `gate_summary.py` parses only the AIUE-56 script's format; read `jac_bound.py`'s lines directly | (doc) |
| I1-m3 V6b names no attribute | new `ci/ppp_keys.py`, run by `run_omp_ci.sh` right after the smoke test: every key of every flow's `ppp` field must exist in `uedge.ppp`, else exit 2 naming flow and key. Checked on the pre-fix macOS build: "ppp_keys: ERROR: the build has no such ppp variable: flow tebox1: ppp.OMPJacMinChunkLen (exit 2)"; on the combined build "ppp_keys: OK (OMPJacMinChunkLen, OMPJacVerbose)" | `test_ppp_keys.py` (3 tests) |
| I1-m4 nightly not validated on Linux | README "CI": the nightly set is not yet validated on Linux; a red first nightly is not necessarily a regression; owner decides; a manual `workflow_dispatch` `set: nightly` right after the merge answers it early. Also in the PR description draft | (doc) |
| I1-m5 tolerance on `--itermx` flows | `report.py`: tolerance acceptance only in one-evaluation flows (`settings.itermx` null); `--itermx` groups stay FAIL with "tolerance mode applies to one-evaluation flows only"; docstrings, README and script header say so | `test_tolerance_mode_does_not_apply_to_itermx_flows` |
| I1-m6 wording | (a) `jac_bound.py` stores `worst_ratio: null` and prints "n/a (no Te rows)" when the serial has no Te rows; `report.py` likewise; (b) `openmp-jacobian.md` and the workflow header say "emulated" | `test_no_te_rows_prints_na_not_zero`, `test_bound_line_without_te_rows_says_na` |
