# AIUE-52 implementation review, round 2: response

Review: `docs/reviews/AIUE-52-implementation-round2.md` (REVISE: 0 blocker, 1 major, 1 minor).

**Rebase.** The branch is rebased onto the final harness core, `feature/v9-AIUE-49-omp-harness-core` at `de57d59`
(`git rebase --onto feature/v9-AIUE-49-omp-harness-core fbe0adf feature/v9-AIUE-52-omp-test-flow`). Conflicts went
toward the core: `compare.py` and `test_harness.py` are the core's (so the duplicate ±0 rule for the parallel-RHS
`yldot` is gone, the core has it), `config.py` keeps the core's single `te_phi` (identical to this branch's), the
README presets bullet is the core's, `cli.py` keeps the core's catch-all and this branch's `flow` subcommand and
`KeyboardInterrupt` exit 130, `openmp-jacobian.md` keeps the core's harness section and this branch's flow paragraph
after it. `git diff de57d59 HEAD -- tests/deterministic_omp/harness` touches only `cli.py`, `flow.py`, `test_flow.py`.

| Finding | Resolution |
|---|---|
| **I2-M1** the flow calls the core's `check_arm` with a `RunSpec` | **Fixed.** `flow.py` imports `check_arm` from `harness.compare` (the `ImportError` fallback is deleted, so there is one checker) and calls `check_arm(record, asdict(spec))` for the serial reference and every OpenMP run, i.e. against the spec the flow requested (stricter than the record's own spec: `test_check_arm_uses_requested_spec`). `test_flow.py` fixtures now build records with the core's fields (`provenance()` and `FakeRecord` from `test_harness.py`, spec as `asdict(RunSpec)`, iterations, `rhs_probe_parallel` on `jacrhs`, arrays and equation maps), and the check-arm tests assert the core's messages (serial build, `ParallelPandf1`, clamped `Nthreads`, `OMP_NUM_THREADS`, no OpenMP runtime, diagnostic switch, serial reference with a switch on). README and `openmp-jacobian.md` now point at the core's rules instead of restating the old local ones. The four points of the review: (1) done; (2) 107 unit tests pass (core + flow); (3) done; (4) Te box with `base-serial`: ERROR, exit 2 (jac only and both arms); with `base-omp`: FAIL in Te rows, exit 1 (validation R2.1–R2.3). |
| **I2-m1** report-level errors become an unexplained FAIL | **Fixed.** `group_verdict` moves every report with `errors` into the group's errors (ERROR), with the comparison kind and its first error as the reason shown in the summary (`test_group_report_errors_are_error`; end to end, a run whose record lacks `yldot` gives ERROR "…: yldot missing from the record", exit 2, `test_cli_flow_missing_vector_is_error`). `HARNESS_SIDE` gains `"unreadable record"`, so the core's `unreadable record.json/npz` is ERROR (two new `test_classify_failure` cases). `flow.exit_code` now returns 2 when a gate has nothing to judge, as `cli.exit_code([])` (`test_exit_code_nothing_gated_is_error`); not reachable through the CLI, which rejects empty matrices. |

New observation (not a finding): with the core's comparison, the Te-box `jacrhs` run0 reports `jacobian_count`
(`['post_exmain']` vs `['post_exmain (permuted indices)']`), because its parallel-RHS iteration-0 fnrm was 1.06e31
> `ftol=1e20` and nksol iterated once (validation R2.3). The flow shows `?` among the mismatch rows for that permuted
Jacobian, which the core compares by position without cell labels.

`check_context_refs.py --changed origin/v9-develop`: OK.
