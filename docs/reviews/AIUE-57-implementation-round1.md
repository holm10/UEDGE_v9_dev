# AIUE-57 implementation review, round 1: OpenMP CI job `build-test-omp.yml`

Reviewer: uedge-reviewer (independent). Branch `feature/v9-AIUE-57-omp-ci-job` @ b0aa7b3, diff `8d4c2c9..HEAD`.
Reference: ticket AIUE-57 acceptance criteria, `.claude/plans/AIUE-57-omp-ci-job.md`.

## Verdict

**REVISE**. 0 BLOCKER, 2 MAJOR, 5 MINOR.

## Summary

The workflow, driver script and report are well built. The workflow builds the default OpenMP variant, a serial
build cannot pass (I reproduced exit 2), the gate cannot go green when a flow errors, leaves no `flow.json`, or has
a group with missing reports, and the static checks and unit tests pass. The pre-fix build, the seeded race
(`resee` without `+threadprivate`) and the AIUE-56 build all come out red locally, as the ticket expects.
Two things stand in the way of approval. First, under the PR set's `--itermx 3`, the cell that a failure names is
not the cell of the first mismatch: on the AIUE-56 build it is a downstream `yldot` entry, not the Jacobian entry
that differs. That misses the stated acceptance criterion. Second, the in-repo docs give "not before AIUE-56" as the
merge condition, but I confirmed that the AIUE-56 build is still red on every Te-box group. Merging on that
condition would turn every push in the repo red until M2 or decision 9 is settled.

## Findings

### BLOCKER

None.

### MAJOR

**R1-M1: With `--itermx 3`, the failure message names a downstream cell, not the cell of the first mismatch.**
Location: `tests/deterministic_omp/ci/report.py:35-49, 81-89`; the PR set in `run_omp_ci.sh:49` (every flow
uses `--itermx 3`); README CI section, "`--itermx 3` and the permuted Jacobian".
- What is wrong: after Newton iterations the post-`exmain` Jacobian is the permuted `psetnk` one, so the first
  mismatch the flow reports is `position N` with no cell. `report.py` then falls back to the first cell-mapped
  mismatch of any section in compare order (`sfscal`, `yldot`, ...). Once the Newton path has moved, those vectors
  differ everywhere in the box. Their first differing index is just the lowest-index cell, not where the defect is.
- Evidence (my runs, `rev57/aiue56` and `rev57/aiue56-1eval`):
  - AIUE-56 build, Te box, `--itermx 3`: the gated line says `first localised mismatch in equation te, cell
    (ix=3,iy=18) [yldot]`. Behind it, `yldot` has 25 mismatches. The Jacobian has only 1-2 mismatching entries,
    e.g. `0.004701627609469395` vs `0.004701627047183649`.
  - Same build, one evaluation (`OMP_CI_ITERMX=`): the gated line says `first mismatch in equation te, cell
    (ix=4,iy=20) ... row te(ix=4,iy=20) col te(ix=3,iy=21)`. That is the real location of the M2 entry.
  - So the PR job would send whoever debugs it to the wrong cell. On the pre-fix build the `sfscal` fallback
    happens to land on te(ix=3..4,iy=18), but that is luck, not design. The README itself says the full problem
    names `ni` rows.
- Acceptance condition (any one of these):
  - (a) The harness records the RCM permutation (`bbb.perm`/`qperm`, group `Jacreorder`, `bbb/bbb.v:2959-2966`)
    and maps permuted positions back to cells. This is a harness-ticket change.
  - (b) The PR set gets a one-evaluation Te-box `jac` group whose first mismatch is cell-mapped (cost about
    seconds per run). This needs per-flow `itermx` in the `OMP_CI_FLOWS` spec.
  - (c) The ticket owner explicitly accepts "first localised mismatch" as meeting the criterion. In that case the
    README must stop presenting the fallback cell as a location of the defect.

**R1-M2: The merge precondition is understated, and "green on the fixed code" cannot be met with the default gate.**
Location: `.github/workflows/build-test-omp.yml:8-9`; `tests/deterministic_omp/README.md` CI banner;
`.claude/context/testing.md` CI facts ("not to be merged before the OpenMP Jacobian fix (AIUE-56)").
- What is wrong: all three places name AIUE-56 as the only merge condition. The README adds, in passing, that the
  job stays red while M2 remains. The plan (`.claude/plans/AIUE-57-omp-ci-job.md`) and the validation record say
  correctly that merging also waits for decision 9 or an M2 fix, but the files a maintainer actually reads do not.
  The workflow triggers on `push` to every branch and on `pull_request`.
- Evidence: the AIUE-56 build (`venvs/AIUE-56-omp`), Te-box PR half (2 and 4 threads, K=5, both arms,
  `--itermx 3`) gives `run_omp_ci.sh` **exit 1**:
  - jac: 0/5 runs agree with serial at 2 threads and 0/5 at 4 threads; jacrhs: 0/5 and 0/5.
  - Failing sections: `jacobian:post_exmain (permuted indices)` with 1-2 entries at about 1.2e-7 relative,
    plus `yldot`, `yldot_probe`, `fnrm_final` and `fnrm_printed`.
  - One evaluation: 0/3 and 0/3, exit 1.
  - This confirms that under the bitwise gate M2 alone keeps the job red, and that is not specific to the 3e proxy
    build. On AIUE-56 it is worse: 0/5 at 2 threads, where the proxy had 4/5.
- Acceptance condition:
  - The workflow header, the README banner and `testing.md` all state the full precondition: not before AIUE-56
    **and** not before the gate is green on the AIUE-56 build (M2 fixed, or decision 9 settled).
  - The ticket's "green on the fixed code" criterion stays open until then. This is a gating and documentation
    defect plus an owner decision, not a code defect.

### MINOR

**R1-m1: The README's "one switch, no other file has to change" is not true under `--itermx 3`.** Location: README
CI section, "Gate mode (decision 9), one switch". The validation record (3e) notes this, and my AIUE-56 run confirms
it: the 1e-7 Jacobian difference moves the iterate, so `yldot` (25 entries) and `fnrm_*` also fail bitwise. A
tolerance that applies only to the Jacobian (`--jac-tolerance`) leaves the PR set red. Acceptance: the README says
that a tolerance gate must also cover `yldot`/`fnrm`, or that the gated flow must use one evaluation. The owner
needs this to make decision 9.

**R1-m2: The workflow has no `permissions:` block.** Location: `build-test-omp.yml` top level. The job only reads.
Add `permissions: contents: read`, as `claude-context-drift.yml` does.

**R1-m3: Duplicate runs and cancelled default-branch runs.** Location: `build-test-omp.yml:11-13, 25-27`.
- A push to a same-repo PR branch starts both a `push` run and a `pull_request` run: about 2 x 17 min of runner
  time. Because the concurrency group includes `event_name`, the two never deduplicate.
- `cancel-in-progress: true` also cancels the result of an earlier merge on `v9-develop` when the next merge lands
  within the run time.
- The triggers are what the ticket specifies, so this is a suggestion only: for example `push: branches:
  [v9-develop]`, or no cancelling on the default branch.

**R1-m4: "≥ 3 Newton iterations" is not enforced.** `--itermx 3` is an upper limit at the deck's `ftol`, and the
harness only checks that some iterations were recorded (`compare.py:195`). On the Te box I verified iterations
0-3 (3 Newton steps, `ijactot` 2) for both serial and OpenMP. For the full problem it was not checked. Acceptance:
assert (in the report or the harness) that the recorded iteration count equals `itermx`, or document why that
isn't needed.

**R1-m5: The defect found in `build-test-wheel.yml` is not recorded.** `build-test-wheel.yml:80` does run
`pip install forthon>=0.10.7` unquoted, so the shell redirects to a file named `=0.10.7` and `forthon` installs
unpinned. I confirmed this. The new workflow quotes it correctly (line 55). The fact belongs in the
`testing.md` "CI facts / quirks" list (code-facts), or in its own issue.

## Status of previous findings

Round 1: none.

## What was checked and how

All output is in
`/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev57/`.

**Static checks**
- `bash -n` (Homebrew bash and `/bin/bash` 3.2): OK.
- `shellcheck run_omp_ci.sh`: clean.
- `uvx --from actionlint-py actionlint .github/workflows/build-test-omp.yml`: exit 0.
- YAML load with pyyaml: OK.
  - The triggers parse as push, pull_request, schedule `17 3 * * *`, and workflow_dispatch with a `set` choice.
  - `timeout-minutes` is an expression that gives 150 for nightly and 30 otherwise.

**Unit tests:** `pytest tests/deterministic_omp/ci tests/deterministic_omp/harness` gives 115 passed.

**Context drift:** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` (from the worktree)
prints OK, rc 0.
- Both context commits carry `AI-layer: code-facts`.
- No skills, agents, hooks or settings change in `8d4c2c9..HEAD`.
- The plan file under `.claude/plans/` is an "artifact" (`branching.md:13`), so it is allowed on a ticket branch.
- `testing.md` line 48 and `openmp-jacobian.md` are updated and say what the code does.

**Workflow review**
- Quoting: `"forthon>=0.10.7"` is quoted, so there is no redirect.
- OpenMP build: `pip install -v .` is the OpenMP default (`setup.py:38, 731-735` strip `-fopenmp` only with
  `--serial`).
- The schedule runs only from the default branch. GitHub API: the repo is public and its default branch is
  `v9-develop`, so the nightly would run after merge and the runner has 4 vCPUs.
- Concurrency key, artifact paths relative to `$GITHUB_WORKSPACE/omp-ci-out`, and `if: always()` on the
  wall-time and upload steps: checked.
- `inputs.set` on non-dispatch events evaluates to null and falls through to `pr`: correct.

**Gating logic review**
- `report.py` exit code = max(the script's flow exit codes, each `flow.json` `exit_code`, which defaults to 2).
- A missing or unreadable `flow.json` gives 2.
- The flow's own exit code: a gated arm with no verdicts gives 2 (`flow.py:154`); a group with fewer reports
  than repeats is ERROR "missing reports" (`flow.py:103-105`). Groups come from `plan()`, so a group cannot
  silently disappear.
- Any exception in `cli.py` gives 2.
- Result: I found no path to green when a flow errors.

**Local runs (macOS, libomp; load average about 45 from other sessions; at most 3 of my UEDGE processes at once)**

| Build | Flow | Result |
|---|---|---|
| `venvs/base-omp` (pre-fix) | `OMP_CI_FLOWS="tebox\|tebox\|2,4\|5\|jac,jacrhs"`, `--itermx 3` | **exit 1**, 83 s. jac 0/5 at 2 and 4 threads. Gated lines name te(ix=4,iy=18) and te(ix=3,iy=18) [sfscal]. |
| `venvs/AIUE-56-omp` (C1 fix) | same | **exit 1**, 84 s. jac 0/5 and 0/5; jacrhs 0/5 and 0/5; Jacobian 1-2 entries at about 1.2e-7 relative (M2). Gated lines name te(ix=3,iy=18) [yldot] (see R1-M1). Confirms the expected exit 1 under the bitwise gate. |
| `venvs/AIUE-56-omp` | Te box, jac, K=3, one evaluation | **exit 1**. Names te(ix=4,iy=20), the real M2 entry. |
| `venvs/base-serial` | Te box, jac, 4 threads, K=2 | **exit 2**: "ERROR (cannot judge): ... ParallelJac=0 (OpenMP Jacobian did not run: serial build?) ...". A serial build cannot go green. |
| `venvs/AIUE-57-race-swap` (seeded race, C1 swapped) | Te box, jac, 2 and 4 threads, K=3 | **exit 1**. All 6 of 6 OpenMP runs are red: 3 crash (2 x SIGSEGV, 1 `*** Stop ***`) and 3 mismatch. |

- Seeded race: I confirmed the diff in `uedge-wt/AIUE-57-race` (`bbb/bbb.v:2310`, `resee` without
  `+threadprivate`). `resee` is written in `bbb/pandf_plasma_energy.m:1009-1116`, the electron-energy path.

**Not independently verified (environment)**
- CI wall time and the ≤ 20 min budget. The estimate in the validation record is 14-21 min, central 17, with the
  derivation and cut order documented.
- 20/20 red CI runs on the pre-fix code and on the seeded race.
- The OpenMP build on `ubuntu-latest`, and Linux/libgomp behaviour.
- The full-problem half of the PR set: I did not run it (about 1 h under this load). The author's pre-rebase run
  (3a) is the only evidence for it.
- The nightly set.
