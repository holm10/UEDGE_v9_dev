# AIUE-52 implementation review, round 3 (final): OpenMP test flow

Branch `feature/v9-AIUE-52-omp-test-flow` (worktree `uedge-wt/AIUE-52`), HEAD `8d4c2c9`, rebased onto the final
harness core `feature/v9-AIUE-49-omp-harness-core` `de57d59`. Diff reviewed: `git diff de57d59..HEAD`
(06b4843 ... 8d4c2c9). Round-2 report: `docs/reviews/AIUE-52-implementation-round2.md`. Response:
`docs/reviews/AIUE-52-implementation-round2-response.md`.

## Verdict

**APPROVE**

## Summary

The rebase is clean. `de57d59` is an ancestor of HEAD. Under `harness/`, the branch changes only `cli.py` (the `flow`
subcommand and the exit-130 handling for Ctrl-C), `flow.py` and `test_flow.py`. The core's `compare.py`, `config.py`,
`runner.py`, `worker.py` and `test_harness.py` are byte-identical to `de57d59`. The flow now has a single arm checker:
it imports the core's `check_arm`, the local fallback is gone, and the checker is called with `asdict(RunSpec)`. All 107
unit tests pass with both venvs. I re-ran the four acceptance points of I2-M1 myself:
- serial build, Te box: ERROR, exit 2;
- OpenMP build, Te box: FAIL in the Te rows, exit 1;
- OpenMP quick set: FAIL, exit 1, with mismatches mapped to cells only in Te rows.

I2-m1 is fixed, and mutation tests confirm the unit tests pin it. One new MINOR: no test pins the flow's wiring to the
requested spec.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I3-m1: no test pins that the flow checks each record against the spec it requested** (`flow.py:392`,
`test_flow.py:314` `test_check_arm_uses_requested_spec`)

- **What the response claims.** The flow checks every record against the requested spec, which is stricter than the
  record's own spec, and `test_check_arm_uses_requested_spec` is cited as the evidence.
- **What that test does.** It calls `flow.check_arm`, which is the core function re-exported. It does not go through
  `compare_group`.
- **Mutation result.** In a copy, I replaced `check_arm(rec, asdict(spec)) if spec is not None else check_arm(rec)`
  with `check_arm(rec)`. All 75 `test_flow.py` tests still pass.
- **Why only MINOR.** The weaker check is still real. `compare_records` calls `check_arm(rec)` on both sides anyway,
  and the record's spec is written from the same `RunSpec` the flow hands to `run_spec`. So the gap only matters if
  the worker records a spec different from the one it was given.
- **To resolve (optional).** Add one `run_cli` test in which the fake runner writes a record whose `spec.threads`
  differs from the requested one, and assert ERROR.

## Status of previous findings

| Finding | Status | Evidence (checked by me this round) |
|---|---|---|
| **I2-M1** flow incompatible with the core's `check_arm` | **Resolved** | See below. |
| **I2-m1** report-level errors become an unexplained FAIL | **Resolved** | See below. |
| **I1-B1** PASS when OpenMP did not run | **Resolved** | Serial-build Te-box flow gives ERROR on both arms, exit 2 (below). The serial reference also goes through `check_arm` (`flow.py:456`). Mutating that check to `problems = []` fails 1 test. |
| **I1-M1** `compare_records` skips missing vectors (resolved pending rebase) | **Resolved** | The core's `compare_records` (`compare.py:220-224, 262-264`) is now the one in use. A missing vector is a report error, which the flow turns into ERROR (I2-m1). |
| **I1-M2** `phi` not a valid isolation | **Resolved** (unchanged) | `PHI_PRESET = "te_phi"`, which is the core's preset. |
| **I1-m1** input validation | **Resolved** (unchanged) | `plan`/`run_flow` validation is unchanged, and `test_cli_flow_rejects_bad_input_before_running` passes. |
| **I1-m2** harness-side failures classed FAIL (partly reversed at rebase) | **Resolved** | `"unreadable record"` is in `HARNESS_SIDE`, and both `unreadable record.json/npz` cases return `True`. In the live quick set, a solver overflow (`RuntimeError: ** overflow: SVR routine lusol0 loop 40`, `full/jacrhs_t2/run0`) was classed `harness_error=False`, so FAIL. That is correct: it is a failure of the build. |
| **I1-m3** slot release, orphaned children | **Resolved** (unchanged) | The `finally:` release and `_terminate_children` are unchanged, and their tests pass. |
| **I1-m4** phi has no verdict of its own | **Open for the owner, as recorded** | README text unchanged. |

### I2-M1: flow incompatible with the core's `check_arm`

1. **One checker, called correctly.** `flow.py:37` is `from harness.compare import check_arm, compare_records`.
   There is no `def check_arm` and no `ImportError` in `flow.py` or `cli.py`. The calls at `:392` and `:456` pass
   `asdict(spec)`, which is a non-empty dict, so the core's `spec or record.meta[...]` takes it.
2. **Fixtures and suite.** The fixtures use the core's `FakeRecord` and `provenance` from `test_harness.py`, and the
   check-arm tests assert the core's messages. Results: 107 passed with `base-omp`, 107 passed with `base-serial`.
3. **Docs.** README "Group verdict" and `openmp-jacobian.md` now point to `compare.check_arm`. The list in the
   context file (the arm's switches, `ParallelJac`/`ParallelPandf1`, `Nthreads`, `OMP_NUM_THREADS`, diagnostic
   switches, the capture source, iterations) matches `compare.py:153-197`.
4. **Live flows.**
   - The serial-build flow gives `ERROR` on both arms and exit 2. The message is "jac arm but ParallelJac=0 (OpenMP
     Jacobian did not run: serial build?); jac arm run with a build that has no OpenMP runtime".
   - The OpenMP-build flow gives `FAIL` on both arms and exit 1. The first mismatch is
     `jacobian:post_exmain value row te(ix=4,iy=18)`.

### I2-m1: report-level errors become an unexplained FAIL

- **Direct probes.**
  - A group with only `{"agree": False, "errors": ["b: yldot missing ..."]}` gives ERROR with the message
    `agreement (serial vs run0): b: yldot missing from the record`.
  - A group whose agreement reports pass but whose determinism report has errors gives ERROR, not PASS.
- **End to end.** `test_cli_flow_missing_vector_is_error` exits 2 and puts the message in `summary.md`.
- **Mutations.** The error loop disabled (`if False:`) fails 2 tests. `"unreadable record"` removed from
  `HARNESS_SIDE` fails 2 tests.

## Regressions and new code

- **Rebase conflict resolutions.**
  - `cli.py`: the core's `HarnessError/ValueError/OSError/KeyError` → 2 handler and its catch-all are kept, and
    `KeyboardInterrupt` → 130 is placed before the catch-all, so Ctrl-C is not reported as a harness error.
  - `openmp-jacobian.md`: the core's section is intact, and the flow paragraph comes after it.
  - README: one hunk changes the core's text. The ±0 exception now covers "`yldot` and the RHS probe when a run used
    the parallel RHS ... counted as `signed_zero_differences`". This matches the core code (`compare.py:258-275`:
    `zero_ok` applies to `yldot` and `yldot_probe` when either record has `ParallelPandf1 > 0`). The new text is
    correct, and the old core text was the stale one.
- **`flow.exit_code` when nothing is gated.**
  - `exit_code({}, "all")` returns 2.
  - `exit_code({}, "jac")` and `exit_code({}, "jacrhs")` raise `ValueError`, which `cli.main` turns into 2.
  - `exit_code({}, "none")` returns 0, by design and as documented.
- **The `?` in the Te-box `jacrhs` mismatch rows.** It comes from the core comparing a permuted-index Jacobian by
  position: run0 iterated once more because its iteration-0 fnrm exceeded `ftol`. This is the core's labelling, not
  the flow's. The validation text (R2.3) explains it, and it is not a finding on this ticket.
- **AI layer.** No skills, agents, hooks or settings changed on the branch. Under `.claude/`, the diff over
  `origin/v9-develop` covers only `context/` and `plans/`, plus `CLAUDE.md` from the core. The AI-layer commits carry
  `AI-layer: code-facts`. `check_context_refs.py --changed origin/v9-develop` prints `OK`, rc 0. It also prints the
  usual "re-read" list, which includes `openmp-jacobian.md` → `flow.py`/README; I re-read those and they are
  consistent.

## What was checked and how

- **Ancestry and file scope.**
  - `git merge-base --is-ancestor de57d59 HEAD`: true.
  - `git diff --name-only de57d59 HEAD -- tests/deterministic_omp/harness` lists `cli.py`, `flow.py`, `test_flow.py`.
  - `git diff de57d59 HEAD -- harness/{compare,config,runner,worker,test_harness}.py` is 0 lines.
- **Code read.** Full `flow.py`, the `cli.py`/README/context diffs, and the core's `check_arm` and `compare_records`.
- **Unit tests.** `venvs/base-omp/bin/python -m pytest -q tests/deterministic_omp/harness` gives 107 passed, and the
  same with `base-serial`.
- **Mutation tests** on copies in `scratchpad/rev52r3/mut{1..5}`, running `test_flow.py` (75 tests):

  | Mutation | Result | Caught? |
  |---|---|---|
  | M1: report-errors loop disabled | 2 failed | yes |
  | M2: requested-spec check replaced by the record's own spec | 0 failed | no (I3-m1) |
  | M3: serial-reference `check_arm` removed | 1 failed | yes |
  | M4: `"unreadable record"` removed from `HARNESS_SIDE` | 2 failed | yes |
  | M5: nothing-gated returns 0 | 1 failed | yes |

- **Edge probes.** `flow.exit_code` with empty verdicts for every gate, `group_verdict` on report-error-only and
  determinism-error groups, and `classify_failure` on an `unreadable record.json` error and a UEDGE `RuntimeError`.
- **Live flows** (no reinstall; 1-min load average 16, rising to about 100 during the quick set):
  - serial build, `flow --configs tebox --threads 4 --cores 4 --max-jobs 2`: both arms ERROR, exit 2, 6.8 s;
  - OpenMP build, same command: both arms FAIL, 0/2 agree, not deterministic, mismatch rows `te` (`?,te` for
    `jacrhs`), exit 1, 7.6 s;
  - OpenMP build, quick set `flow --cores 6 --max-jobs 3`:
    - 18 runs, every group FAIL, rows mapped to cells only `te`, exit 1, 318 s total;
    - `full/jacrhs_t2/run0` stopped with an SVR `lusol0` overflow, which was counted as a build FAIL
      (`run_failures`, `harness_error=False`);
    - the `jac` arm's first mismatch on `full` is `te(ix=1,iy=1)`, as in the round-1 validation.
- **AI layer.** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` from the worktree prints
  `OK`, rc 0. Commit trailers were checked with `git log de57d59..HEAD`.

The outputs are in
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev52r3/`
(`ser_tebox/`, `omp_tebox/`, `omp_quick/`, plus the matching `.log` files).

### Not independently verified

- Linux/gcc and CI.
- `--all`, and the `phi`/`te` `jacrhs` crashes stated in the README (validation R1.3/R1.4).
