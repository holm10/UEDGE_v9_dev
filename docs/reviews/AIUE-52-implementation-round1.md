# AIUE-52 implementation review, round 1: OpenMP test flow

Branch `feature/v9-AIUE-52-omp-test-flow` (worktree `uedge-wt/AIUE-52`), diff `fbe0adf..5fb700b`.
Reference: the ticket's scope and acceptance criteria, and `.claude/plans/AIUE-52-omp-test-flow.md`. Python only.

## Verdict

**REVISE**

## Summary

The flow does what the ticket asks. It has a configuration matrix, one serial reference per configuration, K
fresh-process repeats, determinism checks between repeats, verdicts per arm, and exit codes per gate. I reproduced
the Te-box and quick-set verdicts: the Jacobian arm fails with mismatches only in Te rows. An independent re-check of
the author's `--all` records confirms the Ti/ni/up/ng results and deviation 1. The gate can still go green when OpenMP
never ran. Run with a serial build's Python, the flow reports `ARM jac: PASS`, exit 0, because nothing checks that the
arm's parallel path was active (provenance shows `ParallelJac: 0`). Two more problems are open. The `compare.py` change
now skips `yldot`/`sfscal`/`suscal` without saying so when one record lacks them. The committed `phi` configuration is
not a valid isolation, so `--all` exits 2 on `v9-develop` by construction. The edge-case findings (input validation,
how harness-side failures are classed) are minor.

## Findings

### BLOCKER

**I1-B1: the flow reports PASS when the OpenMP path did not run** (`harness/flow.py` `compare_group`/`group_verdict`;
nothing checks what the run actually did)

- **Evidence.** I ran the Te-box flow with the serial build's Python:

  ```
  base-serial/bin/python cli.py flow --configs tebox --threads 4 --arms jac --repeats 2 --python base-serial/bin/python --out rev52/serialbuild
  | tebox | jac | 4 | PASS | 2/2 | yes |  |  |  |
  ARM jac: PASS  (gated)      exit code 0
  ```

  The run's `record.json` provenance holds `OMPParallelJac: 1, ParallelJac: 0, ParallelPandf1: 0, Nthreads: 4`. The
  switch was requested, but the parallel Jacobian never ran, and the serial reference and the "OpenMP" run are the
  same computation. The OpenMP build gives `ParallelJac: 1` on `jac` and `ParallelJac: 1, ParallelPandf1: 1` on
  `jacrhs` (checked in `rev52/tebox4`), so the record already holds what is needed to tell the two apart.
- **Why it blocks.** The flow is meant to be a CI gate (AIUE-57), and CI builds serial wheels by default
  (`CLAUDE.md`, `build-test-wheel.yml`). If CI points `--python` at the wrong interpreter, or a future change stops the
  OpenMP switches from taking effect (for example `ppp.Nthreads` being clamped, `ppp/omp_parallel.F90:299-309`), the
  gate shows a green PASS. That is the "skipped run reports PASS" case the ticket asked about.
- **To resolve.** Every OpenMP run must show that its arm took effect, or its group is ERROR (it can't be judged):
  - `jac`: `ParallelJac > 0`.
  - `jacrhs`: `ParallelJac > 0` and `ParallelPandf1 > 0` (or `rhs_probe_parallel`).
  - Every run: provenance `Nthreads` equals the requested thread count.
  - The serial reference: both switches 0.

  Add a unit test with a fake record whose provenance shows the switch off, and re-run the serial-build command above
  to show it now gives ERROR and exit 2. The check could live in `compare_group` or in the AIUE-49 `check` path; either
  is fine as long as the flow verdict depends on it.

### MAJOR

**I1-M1: `compare_records` now skips required vectors without saying so when one record lacks them**
(`harness/compare.py:165-167`)

- **What changed.** Before this diff, `sfscal`, `suscal` and `yldot` were read unconditionally, so a missing array
  raised `KeyError`, which the flow turns into ERROR. The new loop does
  `if vec not in a.arrays or vec not in b.arrays: continue`, so a record missing any of them is still reported as
  agreeing. The `yldot_probe` exemption was already one-sided-tolerant, and the loop carries that over.
- **Evidence.** In my probe script (`rev52/probe/probe.py`), with `FakeRecord`s:
  - `yldot` deleted from one side gives `agree: True`, and the report has no `yldot` section.
  - `sfscal`/`suscal` deleted from one side gives `agree: True`.
  - `yldot_probe` present on one side only gives `agree: True`.
- **Why it matters.** AIUE-47 is changing `worker.py` at the same time. A worker change that drops a vector on one
  arm would pass the bitwise gate without anyone noticing.
- **To resolve.** `sfscal`, `suscal` and `yldot` stay mandatory (missing means an error or failed section). An RHS
  vector present on exactly one side is a failing section. Skipping is allowed only when both sides lack the optional
  probe. Add a unit test for each case.

**I1-M2: the committed `phi` configuration is not a valid phi isolation** (`flow.py:37,50`; author deviation 3)

- **Scope.** The ticket asks for "a valid phi isolation". The committed `PHI_PRESET = "full_note"` fails in serial
  (`Jacobian row = 0 for eqn iv = 1092`, phi(ix=11,iy=1); validation §3). As committed, the `phi` row of `--all` is
  always ERROR, and `--all` always exits 2 on `v9-develop` under the default `--gate jac`. So the "every configuration"
  command cannot serve as a gate.
- **The acceptance run.** It used an uncommitted `phi_te` preset. Its results (validation §1) are not reproducible
  from the branch.
- **To resolve.** `PHI_PRESET` names a committed preset whose serial reference runs on this case (the planned Te+phi
  preset from AIUE-49, after rebasing), backed by a flow run of `--configs phi` with a successful serial reference.
  Alternatively, keep `phi` out of `--all` until that preset exists, with the owner's agreement recorded on the
  ticket. See also I1-m4, which is about what a Te+phi isolation can show.

### MINOR

**I1-m1: input validation gaps in `cli.py flow`/`run_flow`** (all confirmed in `rev52/probe/probe.py` with the fake
runner)

- **Empty matrix passes.** `--configs ,`, `--threads ,` or `--arms ,` with `--gate all` (or `none`) runs nothing,
  or only serial references, and returns exit 0. With `--gate jac` the same input gives 2, but only after creating
  `--out`.
- **Duplicate entries.** `--threads 2,2` or `--configs tebox,tebox` creates two groups on the same run directories.
  The second group fails with `[Errno 17] File exists` and is reported as a build FAIL (exit 1).
- **Negative `--max-jobs`.** `--max-jobs -1` hangs forever: `running >= max_jobs` is always true, and `lock.wait()`
  has no timeout. `--max-jobs 0` means unlimited. A negative `--cores` is accepted without complaint.
- **To resolve.** Reject empty or duplicate lists and values below 1 for `--max-jobs`/`--cores` before any run starts
  (exit 2).

**I1-m2: harness-side failures of OpenMP runs are classed as FAIL** (`flow.py:296`; refines deviation 2)

- **The rule as written.** "Unreadable record is ERROR" is applied only in `_load`. Any exception from
  `run_spec`/`work()` on an OpenMP run becomes a `run_failure`, and so a FAIL.
- **What that sweeps in.** Directory collisions, `OSError`, the catch-all `Exception` ("a bug in the harness"),
  `parse_iterations` errors, and truncated JSON.
- **Evidence.** In validation §1, `phi_te jacrhs t2 run1` failed with `Expecting value: line 1 column 1 (char 0)`, a
  `JSONDecodeError` on `record.json`, and is shown as FAIL.
- **Assessment.** The outcome is conservative: exit is non-zero either way, so this cannot cause a false PASS. It does
  break "2 = cannot judge", though.
- **To resolve.** Class worker crashes and solver errors as FAIL, as deviation 2 intends. Class harness exceptions
  (`OSError`, non-`HarnessError` exceptions, an existing run directory, a record that can't be parsed) as ERROR. If
  the line is kept where it is, say so in the README.

**I1-m3: the scheduler releases its slot outside `finally`** (`flow.py:238-252`)

- **Hang risk.** If `log(...)` or `failure_reason(...)` ever raised inside `work()`, the slot would never be released
  and the main thread would wait forever in `lock.wait()`.
- **Orphaned processes.** Ctrl-C in the main thread leaves UEDGE child processes running from daemon threads.
- **To resolve.** Release in `finally:`. Optionally, terminate children on interrupt.

**I1-m4 (decision for the owner): a Te+phi isolation cannot give phi its own verdict while the Te bug exists**

In the author's `phi_te` run, every mismatch is in a Te row and the phi rows agree. The group therefore FAILs because of
the known Te defect, whatever phi does. If the phi configuration is meant to gate phi, it needs one of these:

- a preset in which Te is restricted (the Te-box style), so the Te defect does not fill the verdict;
- a verdict per row equation;
- an explicit note that the phi verdict has to be read from the "mismatch rows" column.

This is a design question, not a code defect.

## Author deviations

1. **±0 equal in the post-exmain `yldot` when a run used the parallel RHS. Accepted.**
   - *Limited to the parallel RHS:* `szero` comes from `rhs_probe_parallel` (`ParallelPandf1 > 0 and ijactot > 0`,
     `worker.py:120`). The rule is off for serial-vs-`jac` and `jac`-vs-`jac`, and off for `sfscal`/`suscal`.
     `--rhs-signed-zero-equal no` overrides it.
   - *Tests:* the new `test_harness.py` assertions cover both-serial strict, the parallel-RHS case, and the override.
   - *No masking, on the data:* I re-checked the author's `acc2_all_k2` records with my own bit comparison, which does
     not use `compare.py` (`rev52/probe/recheck.py`).
     - Every `yldot`/`yldot_probe` difference on `ti`/`ni`/`up` `jacrhs` (36, 255 and 4 entries, all thread counts
       and repeats) has both values equal to 0.0, so 0 of them are non-zero differences.
     - The Jacobian, `sfscal` and `suscal` are bit-identical in those groups.
     - The `jac` arm of `ti`/`ni`/`up`/`ng` is fully bit-identical.
   - *No masking, in principle:* a ±0-only difference has no numerical effect on the residual. Any downstream effect
     would show in the Jacobian or `fnrm`, and those stay strictly compared.
   - The remaining caveat (one-sided absence) is I1-M1.
2. **An OpenMP crash or solver error counts as FAIL. Accepted in principle.** A run that dies under OpenMP while serial
   ran is a finding about the build, and the exit code is non-zero either way. The classification is too broad,
   though: see I1-m2.
3. **Phi isolation. Not resolved:** I1-M2.

## Checks with no finding

- **Exit code logic.**
  - `exit_code` gates only `gated_arms(gate, verdicts)`: ERROR dominates FAIL, which dominates PASS.
  - An ERROR or FAIL in an ungated arm does not change the code. The tests include `("PASS","ERROR","jac",0)` and
    `("FAIL","ERROR","jac",1)`.
  - A failed serial reference is shared by both arms by design, so it is correctly ERROR in the gated arm too.
  - `--gate jac|jacrhs` with that arm missing from `--arms` gives a setup error (2). `--gate none` gives 0.
- **Silent drops.** `plan()` emits every (config, arm, thread) group. `group_verdict` turns a missing report count into
  ERROR ("missing reports"). An agreement or determinism compare that raises gives ERROR. A record that can't be
  loaded gives ERROR.
- **Determinism.** The first successful run is compared with every later run. Since bitwise equality is transitive,
  that is enough to establish that all repeats agree with each other. The comparison is meaningful even when every run
  disagrees with serial (the `deterministic` column).
- **Thread counts and the core budget.**
  - `run_spec` sets `OMP_NUM_THREADS = threads` and the worker sets `ppp.Nthreads = threads`.
  - Provenance in my runs: `Nthreads=4, OMP_NUM_THREADS=4` for t4, and 2/2 for t2. The serial reference is 1/1.
  - A run takes `threads` cores from the budget, and a run wider than the budget runs alone (unit test with
    budget 6 and an 8-thread job).
  - There is no oversubscription beyond the budget. The default budget, `os.cpu_count()`, is 14 here (10 P + 4 E
    cores).
- **AI layer.**
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` from the worktree prints `OK`, exit 0.
  - Branch changes under `.claude/` are only `context/` (commit 5fb700b, trailer `AI-layer: code-facts`) and
    `plans/` (an artifact). No skills, agents or hooks changed.
  - The README and `openmp-jacobian.md` claims match the code: flags, defaults, quick and `--all` sets, verdict and
    exit-code rules, output files.
  - "Te box ~5 s" / "in seconds" holds on an idle machine (validation: 2.5–7.5 s). Under load I measured 22.8 s.

## What was checked and how

- **Read** the full diff `fbe0adf..HEAD`: `flow.py`, `cli.py`, the `compare.py` hunk, `test_flow.py`, the
  `test_harness.py` hunk, README, context, plan and validation record. Also read the harness modules the flow relies
  on: `runner.py`, `worker.py`, `config.py`, `compare.py`.
- **Unit tests:** `base-omp/bin/python -m pytest -q tests/deterministic_omp/harness` gives 53 passed.
- **Te-box flow** (acceptance: < 2 min at 4 threads):
  `cli.py flow --configs tebox --threads 4 --python base-omp/... --out rev52/tebox4`.
  - Result: real 22.8 s at load average about 12–15, exit 1.
  - `jac` and `jacrhs` both FAIL, 0/2 agreeing with serial, not deterministic, mismatch rows `te` only.
  - First mismatch `jacobian:post_exmain value row te(ix=5,iy=18)`.
  - Meets the < 2 min criterion with a wide margin, and reproduces "fails with localised Te mismatches".
- **Quick set:** `cli.py flow --python base-omp/... --out rev52/quick` gives exit 1.
  - `tebox` and `full` FAIL on `jac` at 2 and 4 threads, Te rows only. For example, the first `full` mismatch is
    `te(ix=1,iy=1)` row, `ni[3]` column.
  - `full/jacrhs` stopped with `overflow: SVR routine lusol0 loop 40` at both thread counts and is reported as FAIL.
  - Wall time 1260 s: the load average rose to 43–97 because of other sessions, and `full/serial` alone took 506 s
    against 56 s on the author's run. The time is not comparable with the author's 127 s. The verdicts match
    validation §4.
- **Serial-build false-PASS test:** the `base-serial` command shown in I1-B1 gives PASS and exit 0. Provenance was
  checked in `record.json`.
- **Independent re-comparison** of `ti`/`ni`/`up`/`ng`/`tebox`/`te` in the author's
  `scratchpad/AIUE-52/acc2_all_k2` with my own bit comparison (`rev52/probe/recheck.py`):
  - The `jac` arm of `ti`/`ni`/`up`/`ng` is bit-identical to serial (Jacobian, `yldot`, the probe, `sfscal`,
    `suscal`).
  - On `jacrhs`, those groups differ only in ±0.
  - The `tebox` and `te` mismatches are all in Te rows.
  - This confirms acceptance criterion 1 and deviation 1 without re-running `--all`.
- **Edge-case probes with the test suite's fake runner** (`rev52/probe/probe.py`): empty lists, duplicate threads and
  configs, `--repeats 0`, `--max-jobs -1` (still hung after a 5 s timeout), and vectors missing on one side in
  `compare_records`. Results are given in I1-M1 and I1-m1.
- **Code:** `ppp/omp_parallel.F90:284-330` (how `Nthreads` is clamped and used) and `ppp/ppp.v:14`.
- **AI layer:** `check_context_refs.py` (clean) and `git diff --name-only origin/v9-develop..HEAD`.

All `rev52/...` paths are under
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev52/`.

### Not independently verified (environment)

- Linux and gcc builds, and CI behaviour (AIUE-57).
- Timings on an idle machine: the machine was heavily loaded the whole time.
- The `--all` run itself: I did not re-run it, as asked. I re-compared its saved records instead.
- The temporary `phi_te` preset: it is not committed. The `full_note` serial failure is accepted from validation §3,
  which is consistent with the code.
