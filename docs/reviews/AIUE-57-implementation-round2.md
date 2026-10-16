# AIUE-57 implementation review, round 2: OpenMP CI job `build-test-omp.yml`

Reviewer: uedge-reviewer (independent). Branch `feature/v9-AIUE-57-omp-ci-job` @ 2d52e03. New commits since
round 1: `cae4975` (code, docs, plan) and `2d52e03` (context facts, `AI-layer: code-facts`).
Inputs: round-1 report, `AIUE-57-implementation-round1-response.md`, `AIUE-57-validation.txt` section 8.

## Verdict

**APPROVE**. 0 BLOCKER, 0 MAJOR, 2 MINOR (both optional).

This approves the implementation. It does not approve merging. The merge precondition (AIUE-56 merged, **and** a
gate that can be green on the AIUE-56 code through decision 9 or AIUE-61) is now stated correctly in every file a
maintainer reads. The ticket's "green on the fixed code" item stays open, as the authors say.

## Summary

Both round-1 MAJOR findings are resolved, and I checked each fix myself. The PR set now starts with a
one-evaluation Te-box `jac` flow (`tebox1`). On the AIUE-56 build my run gives exit 1, and the job's
`FIRST MISMATCH` line names `te(ix=4,iy=20)`, the real M2 entry. The `--itermx 3` groups cite that location
explicitly, and the downstream fallback is labelled as such and is never used for the headline.
The merge condition is complete in the workflow header, the README banner, `testing.md` and the plan.
The new iteration assertion works on real records: I truncated a serial `record.json` and got exit 2. The narrowed
push trigger, the cancel rule and `permissions` are correct and pass actionlint. Two small documentation points remain.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**R2-m1: The revised PR budget understates its own upper end, and the nightly estimate does not include `all1`.**
Location: `docs/reviews/AIUE-57-validation.txt` 8d; README "Budget" (14–20 min).
- The components listed in 8d add up to 1 + 4–7 + 0.5 + <1 + 1–2 + 6.3–8.8 + 0.5 = **13.3–20.8 min**. The quoted
  "~14–20 min" therefore rounds the upper end down after a flow was added, while round 1 gave 14–21.
- The nightly estimate (70–90 min, section 5) is unchanged, although `all1` (`--all`, K=2, one evaluation, both
  arms) was added. AIUE-54 measured that same flow at 368 s locally, which scales to about 18 min on CI by the
  validation's own factor of 3. The new total is therefore about 90–110 min, still inside the 150-min timeout.
- Neither number is measured, and the CI `Wall time` step will settle both. Acceptance: quote 14–21 min, or
  justify the tighter bound, and add `all1` to the nightly estimate.

**R2-m2: The README implies that a `FIRST MISMATCH` line always appears; it can be absent.**
Location: README "What a failure says" ("First one `FIRST MISMATCH` line ... for the job").
- `report.py` prints the headline only when a gated group has a cell-mapped location. The unit test
  `test_permuted_first_mismatch_falls_back_...` asserts it is absent otherwise, which is the intended design.
- Two realistic cases end up without a headline:
  - A defect that shows only in the full problem. The PR set has no one-evaluation `full` flow, so its group gets
    only the "may be downstream" entry.
  - An intermittent defect that happens to agree in all K=3 `tebox1` runs. In my AIUE-56 run, `tebox1` at 2 threads
    had **1/3** runs agreeing with serial, so M2 is intermittent at 2 threads. The 4-thread group (0/3) supplied the
    headline.
- In both cases the job is still red, and no wrong cell is presented as the defect, so this is wording only.
- Acceptance: one sentence saying the headline is omitted when no gated group has a cell-mapped location (for
  example a defect that shows only in `full` in the PR set; `all1` covers this nightly).

## Status of previous findings

| Finding | Status | Evidence (checked by me) |
|---|---|---|
| **R1-M1** wrong cell under `--itermx 3` | **Resolved** (option b) | **Driver:** `run_omp_ci.sh:55` PR set = `tebox1\|tebox\|2,4\|3\|jac\|none;...`. The sixth field `none` omits `--itermx`; my run's command line for `tebox1` has no `--itermx`, and `flow.json` has `settings.itermx = null`. **My AIUE-56 run:** exit 1, headline `FIRST MISMATCH: configuration tebox, arm jac, threads 2, equation te, cell (ix=4,iy=20) (flow tebox1)`. The `tebox` jac lines say `located by the one-evaluation group [tebox1]: equation te, cell (ix=4,iy=20)`. The `jacrhs` lines (no one-evaluation counterpart) say `first cell-mapped differing entry (may be downstream of the defect): ... (ix=3,iy=18) [yldot]`, and that entry is not used as the headline. **Without `tebox1`:** running `report.py` on the `tebox` flow alone gives no headline and only labelled downstream entries. **Code:** `report.py` `one_eval_locations` only takes FAIL groups of flows with `itermx` null whose first mismatch is cell-mapped; the headline ranking puts one-evaluation entries first (stable sort); a fallback entry has `direct=False`, so it cannot become the headline. |
| **R1-M2** merge condition understated | **Resolved** | Workflow header lines 8–13, README banner lines 208–217, `testing.md` "Merge condition", and plan line 13 all state both conditions: AIUE-56 **and** a gate that can be green (decision 9 or AIUE-61). My run confirms again that the AIUE-56 build is red under the bitwise gate. |
| R1-m1 "one switch" claim | **Resolved** | README "Gate mode" now says a Jacobian-only tolerance is not enough under `--itermx 3` and names the two ways out. The workflow `env` comment says the same. |
| R1-m2 no `permissions:` | **Resolved** | YAML load: `permissions: {'contents': 'read'}`. actionlint exit 0. |
| R1-m3 duplicate / cancelled runs | **Resolved** | `push.branches: [v9-develop, main]`. `cancel-in-progress: ${{ github.event_name == 'pull_request' }}` is the documented expression form, and actionlint accepts it. The concurrency group still includes `event_name` and `ref`, so pushes and the schedule never cancel each other, and a PR run (`refs/pull/N/merge`) only cancels its own predecessor. The ticket's push and pull_request triggers both remain, now narrowed. |
| R1-m4 iterations not enforced | **Resolved** | `report.py` `iteration_problems` reads `<flow>/<groups[].serial.rundir>/record.json`, and I confirmed those field names in the real `flow.json`. On my run, the serial `iterations[].iter` = `[0,1,2,3]` and the check passes. With a copy of the run whose serial record was truncated to 3 entries: **exit 2**, `serial reference tebox/serial made 2 Newton iteration(s), fewer than --itermx 3`. So the check is live on real data and not a silent no-op. A missing or unreadable record is skipped, but that case is already an ERROR of the flow. |
| R1-m5 `build-test-wheel.yml` quoting | **Resolved** | Recorded in `testing.md` "CI facts / quirks". `build-test-wheel.yml:80` is unchanged and still unquoted, which is correct for this ticket. |

New-change review (no new BLOCKER/MAJOR):
- **Spec parsing:** the per-flow `itermx` parsing in `run_omp_ci.sh:113-121` is correct.
  - An empty field falls back to `OMP_CI_ITERMX` (default 3).
  - `OMP_CI_ITERMX` set but empty, or the field set to `none`, gives one evaluation.
  - An old five-field custom spec still works: `read` leaves `itermx` empty.
- **Headline:** for an `--itermx` group, a cell taken from its own first mismatch could in principle be downstream.
  That needs a bitwise-equal post-`exmain` Jacobian at a different iterate, which is not credible. One-evaluation
  entries outrank it anyway.

## What was checked and how

All output is in
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev57r2/`.

**Static checks**
- `bash -n` (Homebrew bash and `/bin/bash` 3.2): OK.
- `shellcheck run_omp_ci.sh`: clean.
- `uvx --from actionlint-py actionlint .github/workflows/build-test-omp.yml`: exit 0.
- YAML load (`uvx --with pyyaml`): push branches `[v9-develop, main]`, `permissions` `contents: read`, and the
  cancel expression all as described.

**Unit tests:** `pytest tests/deterministic_omp/ci tests/deterministic_omp/harness` with the AIUE-56 venv:
**117 passed**. The two new tests cover the headline from a one-evaluation group and the exit 2 for too few
iterations.

**Context drift**
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` (worktree): **OK**, rc 0.
- `2d52e03` carries `AI-layer: code-facts` and touches only `.claude/context/{testing,openmp-jacobian}.md`. Their
  new text matches the code (PR/nightly sets, triggers, headline source, merge condition, wheel quirk).
- `cae4975` touches no skills, agents, hooks or settings. The plan file is an allowed artifact.
- The `CLAUDE.md` change on the branch predates round 1 (`483d57a`).

**Local run (AIUE-56 build, Te-box part of the PR set)**
- Command: `PYTHON=venvs/AIUE-56-omp/bin/python OMP_CI_CORES=4 OMP_CI_MAX_JOBS=3
  OMP_CI_FLOWS="tebox1|tebox|2,4|3|jac|none;tebox|tebox|2,4|5|jac,jacrhs|3" run_omp_ci.sh`.
- Result: **exit 1**, wall 96 s (`tebox1` 22 s, `tebox` 70 s).
- `tebox1`: jac t2 1/3 and t4 0/3 agree with serial, first mismatch row te(ix=4,iy=20).
- `tebox`: jac t2 1/5 and t4 0/5 agree, located via `tebox1`. `jacrhs` 0/5 and 0/5, report-only.

**Report logic replays (no UEDGE runs)**
- `report.py` on the `tebox` flow alone: no headline, labelled downstream entries, exit 1.
- `report.py` on a copy with a truncated serial `record.json`: exit 2 with the iteration message.

**Budget:** I re-added the 8d components myself (see R2-m1).

**Not verifiable here (environment):** CI wall time and the ≤ 20 min budget; 20/20 red CI runs; the OpenMP build
and libgomp behaviour on `ubuntu-latest`; the full-problem flow (not re-run this round); the nightly set.
