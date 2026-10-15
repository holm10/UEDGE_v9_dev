# AIUE-52 implementation review, round 2: OpenMP test flow

Branch `feature/v9-AIUE-52-omp-test-flow` (worktree `uedge-wt/AIUE-52`), new commits `5fb700b..f3799f7`
(3f4cf9f report, 260720f fixes, f3799f7 code facts). The branch is still based on AIUE-49 `fbe0adf`. The harness core
(`feature/v9-AIUE-49-omp-harness-core`, HEAD `71b0e3b`) was checked for the parts the coordinator moved there.

## Verdict

**REVISE**

## Summary

As committed, every round-1 finding is either fixed on this branch or covered by the harness core. With a serial build
the flow now reports ERROR and exit 2. With the OpenMP build it still reports FAIL in the Te rows, exit 1. The `phi`
configuration's serial reference runs (I reproduced fnrm `0x1.e408034a40e6fp+0`, neq 6336). Bad input is rejected
before `--out` is created, and Ctrl-C stops the workers. The core's `compare_records` makes the RHS vectors mandatory
and fails a vector present on only one side, so I1-M1 is resolved by the core once this branch is rebased. One problem
remains, and it shows up exactly at that rebase. The response says the flow uses "the signature the AIUE-49 core will
provide", but that is not true. The core's `check_arm(record, spec=None)` reads `spec` as a dict (`spec.get("arm")`),
while the flow passes a `RunSpec` dataclass. On a trial merge with the core, every flow run stops with
`AttributeError: 'RunSpec' object has no attribute 'get'` (exit 2), and 21 of the 98 unit tests fail. A rebase that
only resolves the text conflicts would leave a gate that can never pass.

## Findings

### BLOCKER

None.

### MAJOR

**I2-M1: the flow does not work with the core's `check_arm`, so it breaks when rebased onto the core**
(`harness/flow.py:39-62` import fallback, `:404` `check_arm(rec, spec)`, `:468` `check_arm(serial_record, sj.spec)`;
core `AIUE-49/tests/deterministic_omp/harness/compare.py:146-151`)

- **The call does not match.** The flow passes `spec=js[0].spec` / `sj.spec`, which are `config.RunSpec` dataclass
  instances. The core does `spec = spec or record.meta.get("spec", {})` and then `spec.get("arm")`, which only works
  on a dict, and `RunSpec` has no `.get`.
- **Evidence: trial merge.** I built the merged tree with
  `git merge-tree --write-tree feature/v9-AIUE-49-omp-harness-core HEAD` (tree `b44870ab`) and resolved the conflicts
  toward the core: `compare.py`, `config.py` and `test_harness.py` from the core, `cli.py` with both sides. I
  extracted the result to `scratchpad/rev52r2/merged`. Running
  `base-omp/bin/python -m pytest tests/deterministic_omp/harness` there gives **21 failed, 77 passed**:
  - every `test_cli_flow_*` that reaches the comparison stops at `flow.py:468`, `check_arm(serial_record, sj.spec)`,
    in `compare.py:151` with `AttributeError: 'RunSpec' object has no attribute 'get'`;
  - the core's `cli.main` catch-all turns that into `HARNESS ERROR (unexpected)` and exit 2, so every flow run after
    the rebase ends in ERROR.
- **Not only the spec type.** I patched the two calls in a copy to `dataclasses.asdict(spec)`
  (`scratchpad/rev52r2/merged2`). The `test_flow.py` fixtures and assertions still fail, because they are written for
  the local checker:
  - the expected messages, for example `"ParallelJac=0 (expected >0)"`;
  - fake records without the fields the core requires: `rhs_probe_parallel` on `jacrhs`, `iterations`, `capture`
    and the `jac_post` arrays;
  - direct calls to `check_arm(rec, RunSpec(...))`.
- **Other places that describe the local rules.** The README ("must have `ParallelJac` > 0 ...") and
  `openmp-jacobian.md` describe the local rules, not the core's. The core requires `ParallelJac == 1` and adds checks
  for diagnostic switches, the capture source and missing iterations.
- **Why MAJOR.** The branch is correct only in its current, pre-rebase state, and it cannot merge in that state. The
  response's compatibility claim is the only thing standing between "resolve the text conflicts" and a broken gate,
  and that claim is wrong.
- **To resolve.** After the rebase onto the core:
  1. `flow.py` calls the core `check_arm` with an argument it accepts, either `asdict(spec)` or by changing the core to
     accept a `RunSpec`. The `ImportError` fallback is removed, so there is only one checker.
  2. The `test_flow.py` check-arm tests and fake records are updated to the core's rules, and the suite passes.
  3. The README and `openmp-jacobian.md` lines that describe the check match the core.
  4. A real Te-box flow on the rebased tree gives `ERROR`/exit 2 with `base-serial` and FAIL (Te rows)/exit 1 with
     `base-omp`.

  This can be closed during the central rebase if those four points are shown.

### MINOR

**I2-m1: after the rebase, report-level errors from the core's `compare_records` become an unexplained FAIL**
(`flow.py` `group_verdict`, `first_mismatch`)

- **How it happens.** The core's `compare_records` now returns `report["errors"]` with `agree=False` for several
  cases: a missing `yldot`/`sfscal`/`suscal`/`jac_post`, an `neq` or spec mismatch, a `check_arm` problem, or a
  capture-hook mismatch. `group_verdict` looks only at `agree`.
- **Evidence.** A group whose only report is `{"agree": False, "errors": ["b: yldot missing from the record"],
  "sections": {}}` gives verdict `FAIL`, `first_mismatch ''` and `failing_sections []`. The summary row says FAIL with
  no reason, and the exit code is 1, not 2.
- **A related case.** The core's `Record` wraps a truncated `record.json` as
  `HarnessError("unreadable record.json ...")`. That message is not in `flow.HARNESS_SIDE`, so after the rebase
  `classify_failure` classes it as FAIL. This reverses the I1-m2 rule the README states ("an unreadable or truncated
  record" is ERROR).
- **Why only MINOR.** Both cases are conservative: the exit is non-zero and there is no false PASS. I1-M1's acceptance
  ("missing means an error or failed section") is still met.
- **To resolve.** Map a report with non-empty `errors` to the group's `errors` (ERROR, with the message shown), and
  add `"unreadable record"` to `HARNESS_SIDE`. If the line is drawn differently, say so in the README.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| **I1-B1** PASS when OpenMP did not run | **Resolved on this branch** (but see I2-M1 for the rebase) | See below. |
| **I1-M1** `compare_records` skips missing vectors | **Resolved by the core, pending rebase** | See below. |
| **I1-M2** `phi` not a valid isolation | **Resolved** | See below. |
| **I1-m1** input validation | **Resolved** | See below. |
| **I1-m2** harness-side failures classed FAIL | **Resolved on this branch**; partly reversed after the rebase | See I2-m1. |
| **I1-m3** slot release, orphaned children | **Resolved** | See below. |
| **I1-m4** phi has no verdict of its own | **Recorded for the owner, as asked** | See below. |

### I1-B1: PASS when OpenMP did not run

- **Re-run of the round-1 command.** I re-ran it with the serial build:
  `cli.py flow --configs tebox --threads 4 --arms jac --repeats 2 --python base-serial/bin/python --cores 4 --max-jobs 2`.
  It gives `ERROR run0: arm did not take effect: ParallelJac=0 (expected >0); run1: ...`, `ARM jac: ERROR (gated)`,
  exit 2. The serial reference is checked as well (`flow.py:466-469`, and the unit test `serial_ref_parallel` gives 2).
- **The local fallback is equivalent to the core for every I1-B1 case:**
  - serial build on `jac`/`jacrhs`: core `ParallelJac != 1`, local `ParallelJac > 0` false;
  - clamped `Nthreads`, and `OMP_NUM_THREADS` not equal to the requested count: both;
  - a serial reference with any of `OMPParallelJac/OMPParallelPandf1/ParallelJac/ParallelPandf1 != 0`: both;
  - `jacrhs` without the parallel RHS: core `ParallelPandf1 != 1` plus `rhs_probe_parallel`, local
    `ParallelPandf1 > 0`;
  - missing provenance: both.
- **Where they differ:**
  - Local only: a `ParallelPandf1 == 0` check on the `jac` arm, and checks of the requested `OMP*` switches.
  - Core only: diagnostic switches, the capture source, a truncated capture, and missing iterations.
  - None of these changes an I1-B1 verdict.

### I1-M1: `compare_records` skips missing vectors

The core's `compare_records` (`AIUE-49 compare.py:214-219,254-262`) covers all three acceptance cases:

- A missing `yldot`/`sfscal`/`suscal` on either side is a report error, so `agree=False`.
- `(vec in a) != (vec in b)` gives a failing section, `"present in one record only"`.
- `yldot_probe` is skipped only when both sides lack it.

This branch keeps the old `continue` until the rebase. On the trial merge the core's version is the one used. After
the rebase the verdict is FAIL rather than ERROR (I2-m1).

### I1-M2: `phi` not a valid isolation

- `PHI_PRESET = "te_phi"`, and `config.py:39-41` keeps `isteon`/`isphion`. It is the same as the core's `te_phi`, so
  the `config.py` conflict at rebase is cosmetic.
- My run of `--configs phi --threads 4 --arms jac --repeats 1`:
  - the serial reference ran: neq 6336, `fnrm_final_hex 0x1.e408034a40e6fp+0`, which equals 1.890747266414930 as
    claimed;
  - `jac` FAIL, mismatch rows `te` only, exit 1, 64 s wall under load average about 60.

### I1-m1: input validation

`cli.py flow` with each of `--configs ,`, `--threads ,`, `--arms ,`, `--gate all --arms ,`, `--max-jobs -1|0`,
`--cores -1|0`, `--repeats 0` and `--threads 0` exits 2 with a clear message, and `--out` is not created (checked for
each). Duplicates are dropped (`test_cli_flow_dedupes`). `--max-jobs 0` used to mean "unlimited" and is now rejected.
The README is consistent with that.

### I1-m3: slot release, orphaned children

- The slot is released in `finally:` (`test_scheduler_survives_failing_log`).
- Live test: I started the Te-box flow with SIGINT reset to default (`perl -e '$SIG{INT}="DEFAULT"; exec ...'`) and
  sent SIGINT to the driver after 7 s while two workers ran.
  - Result: exit 130, `INTERRUPTED (child runs were sent SIGTERM)`, and no `worker.py` process left 4 s later.
- An earlier attempt with a plain `&` background job was not a valid test: a non-interactive shell starts background
  jobs with SIGINT ignored, so the flow ran to completion.

### I1-m4: phi has no verdict of its own

The README and the `PHI_PRESET` comment say to read phi from the "mismatch rows" column and list the options. The
design question is still open for the owner.

## Exit codes and empty report lists (the core reviewer's `exit_code([])` concern)

- **The function itself.** `flow.exit_code({}, "all")` returns 0, and `group_verdict` with `repeats=0` and no
  reports returns PASS (both checked directly).
- **Not reachable through any flow path:**
  - `plan()` rejects empty configuration/arm/thread lists and `repeats < 1`, and `run_flow` calls `plan` before any
    run. All four rejections were checked.
  - Every arm in `--arms` therefore gets at least one group, so `arm_verdicts` is never empty.
  - Every group expects `repeats >= 1` reports or run failures. Fewer gives ERROR (`"missing reports"`, checked with
    an empty group: ERROR).
  - `--gate jac|jacrhs` with that arm missing is a setup error (2).
- **`--gate none`.** It returns 0 by design (report only), as documented.
- **Assessment.** I raise no finding. A one-line guard in `exit_code` (empty `gated` with `gate != "none"` gives 2)
  would protect any sibling tool that reuses it, and it costs nothing.

## Regressions and new code

- **Unit tests.** The new code (`classify_failure`, `_terminate_children`, the scheduler split, the `check_arm`
  fallback) is covered by tests that would catch the obvious bugs. The 11 `classify_failure` cases include
  "worker `KeyError` is ERROR" and "UEDGE `RuntimeError` is FAIL".
- **Te-box flow with the OpenMP build.** `--configs tebox --threads 4 --cores 4 --max-jobs 2` gives exit 1:
  - both arms FAIL, 0/2 agree with serial, not deterministic, mismatch rows `te` only;
  - first mismatch `jacobian:post_exmain value row te(ix=4,iy=18)`;
  - 39.7 s wall at load average about 65.

  This is the same result as round 1 and validation R1.2.
- **AI layer.** `.claude/context/openmp-jacobian.md` (commit f3799f7, trailer `AI-layer: code-facts`) matches the
  branch code. It will need to change with I2-M1. No skills, agents or hooks were changed on the branch.

## What was checked and how

- **Read:**
  - `git diff 5fb700b..HEAD` for `flow.py`, `cli.py`, `config.py`, `test_flow.py`, README, plan, context and the
    validation addendum;
  - core `compare.py` (`check_arm`, `compare_records`), `config.py` and `runner.py` at `71b0e3b`.
- **Unit tests (branch):** `base-omp/bin/python -m pytest -q tests/deterministic_omp/harness` gives 89 passed.
- **Trial rebase:** `git merge-tree --write-tree` (no worktree changes), with the conflicts resolved toward the core,
  in `scratchpad/rev52r2/merged`. The unit tests there give 21 failed, 77 passed, with the `AttributeError` traceback
  at `flow.py:468` / `compare.py:151`. A copy patched to `asdict(spec)` (`merged2`) still fails the `test_flow.py`
  fixtures.
- **Flows:** run with the branch code, `--cores 4 --max-jobs 2`:
  - serial-build Te box: ERROR, exit 2;
  - OpenMP Te box, both arms: FAIL in Te rows, exit 1;
  - `--configs phi --arms jac --repeats 1`: serial reference ran, FAIL in Te rows, exit 1;
  - live SIGINT test: exit 130, no workers left.
- **Input validation:** 10 bad-argument probes, all exit 2 with `--out` not created.
- **Edge-case probes:** `exit_code({}, ...)`, `plan` with empty inputs, and `group_verdict` on empty, `repeats=0` and
  errors-only reports.
- **AI layer:** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` from the worktree prints
  `OK`, rc 0. `git diff --name-only origin/v9-develop..HEAD` under `.claude/` shows only `context/` and `plans/`.

All `rev52r2/...` and `scratchpad/rev52r2/...` paths are under
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev52r2/`.

### Not independently verified

- Linux/gcc builds and CI.
- The quick set and `--all`: not re-run, because of machine load. Validation R1.4 is consistent with my round-1
  quick-set verdicts.
- The `jacrhs` SIGSEGV on `phi` (validation R1.3): I ran `jac` only.
