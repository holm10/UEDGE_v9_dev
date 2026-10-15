# Feature: AIUE-57 — OpenMP CI job `build-test-omp.yml`

## Summary
**Type**: CI (workflow + test tooling; no Fortran, `.v` or `src/uedge` change)
**Complexity**: Low–medium
**Default results**: Unchanged (no product physics or numerics touched)
**Files**: `.github/workflows/build-test-omp.yml`, `tests/deterministic_omp/ci/{run_omp_ci.sh,report.py,test_report.py}`,
`tests/deterministic_omp/README.md` (CI section), `.claude/context/{testing,openmp-jacobian}.md` (code-facts),
`docs/reviews/AIUE-57-validation.txt`
**Branch / worktree**: `feature/v9-AIUE-57-omp-ci-job` @ `../uedge-wt/AIUE-57` (stacked on
`feature/v9-AIUE-52-omp-test-flow`; restacked by the main session once AIUE-49's stricter comparator lands)

> **DO NOT MERGE before AIUE-56 (the OpenMP Jacobian fix).** The job is red on the pre-fix code by design. With
> only C1 fixed it is still red under the bitwise gate while M2 (round-off-level Te-row entries) remains, so
> merging also waits for decision 9 (bitwise vs a fallback tolerance) or an M2 fix.

## Problem and solution
CI builds only `--serial` (`build-test-wheel.yml`), so OpenMP races are never seen. AIUE-57 adds a workflow that builds
the default OpenMP build and runs the AIUE-52 flow on the Te box and the full problem, gating on the Jacobian arm.
All steps live in a script so they run the same locally and in CI.

## Decisions
- **Workflow calls only the CLI** (`harness/cli.py flow`) through `ci/run_omp_ci.sh`; nothing imports harness
  internals, so the AIUE-49 restack does not touch the CI files. `ci/report.py` reads only `flow.json` fields the
  AIUE-52 flow writes (`groups[].{config,arm,threads,verdict,first_mismatch,agree_serial,errors,run_failures}`,
  `gated`, `exit_code`, `settings`, `timing`).
- **Triggers:** `push`, `pull_request` → `pr` set; `schedule` (daily 03:17 UTC) → `nightly` set; `workflow_dispatch`
  with a `set` choice. One job, set and timeout chosen by expression (30 min PR, 150 min nightly). `concurrency`
  cancels superseded runs of the same ref and event.
- **PR set** (reduced, budget ≤ 20 min): `tebox` 2,4 threads K=5 both arms; `full` 2,4 threads K=2 `jac` only; all
  `--itermx 3`. The full-problem `jacrhs` runs are dropped from the PR set because the arm is report-only and they
  are the most expensive runs (≈ 40 % of the full flow); the nightly set runs them.
- **Nightly set:** `--all` (8 configurations, 2,4,8 threads), K=3, both arms, `--itermx 3`.
- **Gate:** `--gate jac` (bitwise, the flow's own jac-arm verdict). `jacrhs` failures become `::warning::`
  annotations only. Exit 2 (cannot judge) is red as well.
- **Decision-9 switch:** `OMP_CI_JAC_TOLERANCE` (workflow `env`). Empty = bitwise. Non-empty is forwarded as
  `--jac-tolerance VALUE`; the script first checks `flow --help` for that option and stops with exit 2 if the harness
  lacks it. No tolerance comparator is implemented here (out of scope; harness ticket).
- **Failure message:** `report.py` prints one `GATED` line per failing gated group (configuration, arm, threads,
  equation and cell parsed from the flow's `first_mismatch`, runs agreeing), emits `::error::` on Actions, writes
  the combined `summary.md` and appends it to `$GITHUB_STEP_SUMMARY`.
- **Artifacts:** summaries, `flow.json`, logs, `record.json`/`spec.json`; not `record.npz` (~60 MB per full run).
- **Install:** mirrors `build-test-wheel.yml` (`forthon>=0.10.7` quoted — the existing workflow's unquoted `>=`
  is a shell redirect — `numpy==1.26.4`, `h5py`, `pytest`), then `pip install -v .`.

## Tasks
1. `ci/run_omp_ci.sh` (sets, env knobs, unit tests, smoke test, flows, report; bash 3.2 compatible; shellcheck clean).
2. `ci/report.py` + `ci/test_report.py`.
3. `.github/workflows/build-test-omp.yml` (actionlint clean).
4. README CI section; context code-facts (`testing.md` CI facts, `openmp-jacobian.md`), separate commit with
   `AI-layer: code-facts`.
5. Local evidence: pre-fix build red (exit 1, named first mismatch); seeded race (`resee` without `+threadprivate`)
   on v9-develop and on v9-develop + C1 swap red; C1-swap proxy build to show what the bitwise gate does after C1.
6. `docs/reviews/AIUE-57-validation.txt`; `check_context_refs.py --changed origin/v9-develop` clean.

## Validation
- `bash -n`, `shellcheck`, `actionlint` (via `uvx --from actionlint-py`), YAML load.
- `python -m pytest tests/deterministic_omp/harness tests/deterministic_omp/ci`.
- Local script runs (macOS, heavily loaded; `--cores 4 --max-jobs ≤ 2`) as listed in the validation record.
- Not verifiable locally: CI wall time, 20/20 CI runs, green on the fixed code (pending AIUE-56).
