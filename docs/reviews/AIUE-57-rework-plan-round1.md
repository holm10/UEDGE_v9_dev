# AIUE-57 rework plan review, round 1 (Amendment 1): OpenMP CI job `build-test-omp.yml`

Reviewer: uedge-reviewer (independent). Stage: plan. Branch `feature/v9-AIUE-57-omp-ci-job` @ `ed93aab`, base
`bugfix/v9-openmp-determinism-fix` @ `9fa2a0e`. Reference: ticket AIUE-57 acceptance criteria, the plan
`.claude/plans/AIUE-57-omp-ci-job.md` ("Amendment 1"), and the binding owner decisions relayed by the main session
(decision 9 = option F / AIUE-61; Linux x86-64 bitwise; macOS C2 needs a tolerance; RHS arm report-only, epic AIUE-70;
the C1 bound is defined on the scaled `post_exmain` Jacobian).

## Verdict

**REVISE**: 0 BLOCKER, 2 MAJOR, 8 MINOR.

## Summary

The amendment is well founded. Its premises hold against the code and records: the fixed-chunk count formula, the
1-chunk Te box at the default `OMPJacMinChunkLen`, the raw-versus-scaled gate-tool issue, the AIUE-64 link fix, and a
clean rebase (the range-diff changes only context lines in `openmp-jacobian.md`, and AIUE-53's section is intact).
The gate design is sound. On Linux the `jac` arm is compared bitwise in every section. `jac_bound.py` on the scaled
`post_exmain` matrix is a backstop that can only add red. Using `OMPJacMinChunkLen=1` on the Te box keeps the
default code path and only changes the chunk count, from 1 to 25. Two gaps stop approval. First, the plan does not
say how the new common-block step ends or how its result reaches the report. Read the natural way, it makes the
pre-registered negative control V6/V6c impossible. Second, the tolerance mode is safe only because of its bound
condition, and no planned test or V-check would fail if that condition were dropped or if a missing bound counted
as a pass. Both are cheap to fix.

## Findings

### BLOCKER

None.

### MAJOR

**L1-M1: The plan does not say whether the common-block step stops the script or how its result reaches the job
verdict. Read the natural way, it contradicts V6/V6c.**
- Location: plan, Amendment 1, "UPDATE `run_omp_ci.sh`", item 2 ("Exit 1 → job exit 1 ("common block FAIL"); 2 →
  exit 2"); item 5 (`report.py` gets `--gate-mode`, `--tol` and `bound.json`, but no common-block result); Testing
  strategy V6 and V6c.
- What is wrong:
  - The step comes before the flows. If a FAIL ends the script, the flows and `report.py` never run on a build that
    fails the check.
  - V6c expects exactly that FAIL on the pre-fix build ("a package other than `bbbpy` defines the block first").
  - V6, which is the same run ("V6c ... part of V6"), expects `OMP CI RESULT: FAIL` together with per-group Te-row
    mismatches, `C1 bound EXCEEDED` and a `FIRST MISMATCH` line. All of these come from the flows and `report.py`.
  - If the script runs on instead, the plan never passes the common-block code to `report.py`. The headline,
    `OMP CI RESULT:` line, step summary and annotations could then read `PASS (exit 0)` while the shell exits 1, or
    the reverse.
  - Resolving the package directory (`find_spec('uedge')` returning `None`) has no stated exit code either.
- Evidence: `run_omp_ci.sh:142-148`. The final exit is `report.py`'s code, and `report.py:179-192` builds that code
  only from `--codes` and each `flow.json` `exit_code`.
- Acceptance condition:
  - The plan states one behaviour. Either run the flows after a common-block FAIL or ERROR and fold the code into
    `report.py` (for example `--common-code N`, shown in the headline and summary and included in the exit code as
    `max`), or stop the script and split V6c from V6 (separate commands, separate criteria).
  - A `pkgdir` resolution failure is exit 2.
  - A `test_report.py` case where the common block FAILs and every flow PASSes gives exit 1, with a FAIL headline.

**L1-M2: The tolerance mode is safe only because of its bound condition, and nothing planned would catch an
implementation that skips that condition.**
- Location: plan, "UPDATE `report.py`": the tolerance-mode rule and its VALIDATE list; V8 and V9.
- What is wrong:
  - A FAIL group becomes PASS iff four conditions hold: no run failure, deterministic, only `jacobian:*` sections
    fail, and every run passes `jac_bound` at `tol=v`.
  - For a Jacobian-only difference, the bound is the only condition that separates "round-off" from "real
    regression".
  - The planned unit tests cover bound pass → PASS, `yldot` failing → FAIL, non-deterministic → FAIL and run failure
    → FAIL. None covers "Jacobian-only, deterministic, bound FAIL" → FAIL. None covers a missing `bound.json` or a
    missing group or run entry, which must not count as a pass.
  - V9 does not cover it either. On the pre-fix build, the one-evaluation Te box already differs outside the
    Jacobian (C1 corrupts `sfscal`: 18–19 rows in the AIUE-62 pre-fix Te-box data,
    `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` §Linux characterisation, "Pre-fix (C1) on Linux"). So V9 goes
    red through the `sfscal` section whatever the bound logic does.
  - Result: an implementation that forgets the bound condition, or treats "no bound entry" as within, passes every
    planned check.
  - The main session asked whether the tolerance mode can mask a real regression. As planned, that is not shown.
- Acceptance condition:
  - `test_report.py` cases: (i) Jacobian-only, deterministic, bound `pass: false` → stays FAIL, exit 1; (ii) the
    same with no `bound.json`, or with the group or run missing from it → not PASS, exit 2.
  - Preferably also a real-data falsifier. V8 repeated with `OMP_CI_JAC_TOLERANCE` below the measured macOS Te-box
    C2 deviation (from `bound.json` of the bitwise V8 run) must exit 1, with the bound named as the reason.

### MINOR

**L1-m1: The tolerance-mode exit code and the tolerance range.**
- `report.py` takes its exit code as `max` over `--codes` and over each flow's `exit_code` (`report.py:179-192`). In
  tolerance mode, a flow that FAILed bitwise exits 1 whatever the report decides. The plan should say that in this
  mode the gated exit code is recomputed from the adjusted group verdicts, while ERROR, `iteration_problems`, bound
  exit 2 and common-block results are kept. A wrong implementation would make V8 fail, so this is MINOR.
- The accepted range `(0, 1e-3]` reaches 1000× the registered C1 bound (1e-6). A tolerance above 1e-6 relaxes the
  owner-registered bound rather than applying it. Cap the value at 1e-6, or document why a looser value is allowed.

**L1-m2: In `--itermx` flows the bound sees only the last Jacobian, and V6's pre-registration assumes more.**
- In `--itermx 3` flows `post_exmain` is the last, permuted `psetnk` Jacobian (`worker.py:197-202`), so the bound
  only covers the first Jacobian in one-evaluation flows (`tebox1`, `up1`). That is acceptable, because the bitwise
  flow compares every `captured[k]`, but the README and the plan should say so.
- V6 expects "C1 bound EXCEEDED" in every jac group of `tebox` and `full` (`--itermx 3`). The pre-fix build has no
  capture hook, and C1 corrupts only the first Jacobian of a session (RCA, C1 row: "the second Jacobian of a session
  is correct (E2)"). An EXCEEDED there depends on the moved Newton state and on `sfscal`, not on the design.
  Pre-register it as "recorded", or justify it.
- V6 has no pre-registered outcome for `up1`. The pre-fix Linux `up` result is 2/2 agree at 4 threads (RCA,
  `amd64_base_k2_all`), so it will probably PASS.
- `jac_bound.py` should exit 2 when serial and run disagree on `post_exmain_permuted` or `post_exmain_from`.
  Position-by-position comparison is meaningless across different permutations.

**L1-m3: `jac_bound.py` and `bound.json` details.**
- Fail closed: a missing `bound.json`, a missing group or run entry, or an uncaught exception in `jac_bound.py`
  (Python exits 1 on a traceback) should be ERROR (2), not "EXCEEDED".
- Add a layout test: groups `<config>/jac_t<N>/run<k>` against `<config>/serial`, `jacrhs_t*` ignored, and
  `bound.json` keys that match the keys `report.py` looks up.
- The CHECKDIR interface "so `linux/gate_flows.py` can take it" must accept the `--harness DIR` argument that
  `gate_flows.py:41` passes.
- `linux/README.md:19,52` still point at `AIUE-56-c1-gate.py`. That is historical, so a one-line note to use
  `ci/jac_bound.py` on builds with the capture hook is enough.

**L1-m4: Nothing checks that the Te-box knob took effect.**
- The plan's own premise is that a 1-chunk Te box "tests nothing". `check_arm` checks only `ParallelJac`, `Nthreads`
  and the like (`compare.py:153-193`), and the record holds no `NchunksJac`. If a later change made
  `OMPJacMinChunkLen` ineffective but still settable, the Te-box flows would pass and test nothing.
- Cheap options:
  - add `"OMPJacVerbose": 1` to the `ppp` field (`InitOMPJAC` then prints `NchunksJac` to `run.log`,
    `omp_parallel.F90:327-330`) and have `report.py` or V5 confirm 25;
  - record `ppp.NchunksJac` in the worker's provenance (a harness change).
- At minimum, V5 should record the chunk count it observed.

**L1-m5: How strong the M3 guard and the negative controls are.**
- I agree with keeping `up1` (default 2).
- Its detection power has not been shown. On Linux before AIUE-61, `up` jac at 4 threads agreed in 3/5 runs. At K=3
  that leaves about a 22 % chance of missing a recurrence with the same rate; 8 threads gave 0/5 agree.
  - Optional control: on `T` in Docker, run `up1` with `{"OMPJacFixedChunks": 0}`. FAIL is expected, but only
    probabilistically.
  - Alternatively, run `up1` at 8 threads.
- I accept V6 with the `ppp` field emptied (default 3), if it is documented. On the pre-fix build `OMPJacNchunks=0`
  gives `NchunksJac = neq`. For the Te box that is the same 25 one-column chunks the knob gives on `T` (dynamic
  schedule, no fresh `pandf`). For `full` it is 44 352 chunks against 64. So V6 controls the CI layer against C1. It
  does not test whether the fixed-chunk path is sensitive to C1.
- V7 (the `resee` race on `T`) covers the fixed path. A seeded C1 on `T` (the AIUE-56 copy order reverted, scratch
  commit, Te-box flows) would answer "does the PR set catch a C1-class regression on today's code path" directly.
  Optional.

**L1-m6: The budget estimate and the merge condition.**
- The amendment gives no updated PR-time estimate. My estimate, built from `AIUE-57-validation.txt` §8d
  (central about 17 min), plus `up1` (1 serial and 3 one-evaluation runs at 4 threads, about 0.5–1 min), the bound
  step on the full records (about 0.5–1 min, not measured) and the common-block check (seconds), is about
  **15–22 min, central about 18 min**. It is an estimate from emulated or loaded-machine timings, not a prediction.
  The upper end is over the 20-min budget.
- Pre-register the order of reductions: drop `up1`, then Te box K 5→3, then `full` at 4 threads only.
- With the "do not merge" header gone, the plan should state the merge condition that replaces it, in the plan or
  in a PR checklist:
  - the first native `ubuntu-latest` PR run is green and inside budget (all Linux evidence so far is Rosetta);
  - the branch merges with or after `bugfix/v9-openmp-determinism-fix` (it is stacked on it);
  - the owner decides if native x86-64 shows C2-like entries. The tolerance mode cannot rescue the `--itermx` flows,
    which fail on `yldot`/`fnrm` by design.

**L1-m7: Small reference fixes.**
- The workflow's "do not merge" block is lines 7–13, not 7–12 (line 13 is "Merged earlier, it would turn every
  push and pull request red").
- `openmp-jacobian.md:116` names `docs/reviews/AIUE-60-common-check.py` as "Check:". It stays true, but could now
  also name the CI step `ci/common_check.py`.

**L1-m8 (AI layer, not this ticket; no action on this branch): the ticket-page skill lists sanitiser roots that differ
from its helper.**
- `.claude/skills/ticket-page/SKILL.md:134-135` lists `/Users`, `/home`, `/tmp`, `/private`, `/var`, `/Volumes`,
  `/opt`, `/scratch`, `/gpfs` and, with a following segment, `/global`, `/p`, `/g`, `/usr/workspace`, "…".
- The helper (`ticket_page.py:80-83`) also has the full roots `homes`, `mnt`, `srv`, `root`, `lustre` and the short
  roots `nfs`, `work`, `project(s)`, `data`, `usr/WS\d+`.
- I reproduced the effect: `/mnt/repo and /work/ci-NAME and /out/NAME` sanitises to `{local}/repo and
  {local}/ci-NAME and /out/NAME`.
- So the page shows container paths as if they were workstation paths and keeps `/out/...`, which is inconsistent.
  This is a documentation mismatch in the skill (and arguably a poor fit for container paths). Fix it on a
  `feature/v9-ai-*` branch.

## Answers to the main session's specific questions

- **Is the gate correct and falsifiable, and what exactly fails the job?**
  - Yes for the bitwise `jac` arm on Linux. `compare_records` compares `jacobian:*` (captured and `post_exmain`),
    `sfscal`, `suscal`, `yldot`, the probe and both `fnrm` sections bitwise, plus determinism.
  - Red (1): a gated group FAIL, a bound FAIL, a common-block FAIL.
  - Red (2): a flow ERROR, missing `flow.json`, a serial reference with fewer than N iterations, bound exit 2,
    unit-test or smoke-test failure.
  - A failure in the step that resolves `OMP_CI_GEN_DIR` also fails the job.
  - Gaps: L1-M1 (how the common-block result is combined) and L1-m3 (`bound.json` failures must fail closed).
- **Would the PR set catch C1-class and M3-type regressions?**
  - C1-class, by design yes: `tebox1` is one evaluation and bitwise, with the bound on the first Jacobian, and
    `full` is bitwise.
  - M3-type: probably, but not shown (L1-m5).
  - Budget: about 15–22 min estimated (L1-m6).
- **Is `OMPJacMinChunkLen=1` sound?** Yes. It is the default `OMPJacFixedChunks=1` branch
  (`omp_parallel.F90:314-317`); only `NchunksJac` changes, from 1 to `min(64, 25) = 25`, independent of the thread
  count. Multi-column chunks are covered by `up1` (21 chunks) and `full` (64). What is missing is a check that the
  knob took effect (L1-m4).
- **Is the tolerance mode safe?**
  - It is off by default (`OMP_CI_JAC_TOLERANCE: ""`; no `workflow_dispatch` input sets it).
  - It is constrained well: only `jacobian:*` sections may differ, the run must be deterministic, and runs must not
    fail.
  - It is not tested where it matters (L1-M2), and its range is too wide (L1-m1).
  - Keeping it (default 1) is reasonable.
- **Is the common-block port correct?**
  - The logic ports cleanly. The ELF regex `\s[BCDVbcdv]\s+ompcommonscalarcopy_$` fits `nm -D -S` output.
  - `importlib.util.find_spec('uedge')` does not import `uedge`.
  - The import order parsed from `src/uedge/__init__.py:21-32` is `uedgeC, compy, grdpy, flxpy, bbbpy, ...`, and
    `RTLD_GLOBAL` is set at `:21`.
  - Generated `*_p.F90` live in `build/temp.<plat>-cpython-<ver>/`. I checked this on the combined worktree's macOS
    build; Makefile.Forthon uses `--build-base build`.
  - The ELF branch has never run on a real Linux build. V5 is its first exercise, which is good.
- **Workflow:** triggers, `permissions: contents: read`, concurrency, timeouts and artefacts stay unchanged, except
  the planned `bound.json` and the generated-directory step. Removing the header is justified now that AIUE-56 and
  AIUE-61 are on the base, provided the merge condition in L1-m6 is stated.
- **Defaults 3 and 4:** acceptable. See L1-m5 for V6, and L1-m3 for the old gate script and the Linux README.

## Not independently verified (environment)

- Confluence ticket page 2490370 and Jira state: no Atlassian access. I checked the sanitiser behaviour locally
  instead (L1-m8).
- Native `ubuntu-latest` behaviour: bitwise equality without Rosetta, the in-tree `build/temp.*` path, `nm -D -S`
  output on the runner's binutils, Python 3.11 versus the image's 3.12, wall time, and the 20/20 red-run criterion.
  The plan correctly lists these as confirmable only on the first real PR run. My time figure is an estimate.
- AIUE-61 R5 and AIUE-62 Linux results: read from the records (`docs/reviews/AIUE-61-validation.txt:138-149`, RCA
  §Linux characterisation), not rerun (no Docker for this review).

## What was checked and how

- Plan read in full: Amendment 1 and the original plan, which is kept unchanged under its own heading
  (`git diff c338684 bda3085` removes only two header lines that were relabelled).
- Rebase:
  - `git range-diff 3c03d1c..8ee189d 9fa2a0e..c338684`: 5 commits identical, and 3 (`c65ae8f`, `92dcdb9`,
    `76d27c9`) differ only by the added context of AIUE-53's "Serial old-vs-new bitwise check" heading.
  - `git diff 9fa2a0e c338684 -- .claude/context/`: AIUE-53's section intact.
  - `3c03d1c` and `e52a44d` are ancestors of `9fa2a0e`; the backup ref is `8ee189d`.
  - AIUE-56 (`1553e75`) is not in `origin/v9-develop` (`e52a44d`), so V6's build is pre-fix.
- Trailers: every commit touching `.claude/context/` carries `AI-layer: code-facts`. There are no skill, agent or
  hook changes on the branch.
- Code claims verified by reading: `run_omp_ci.sh:52,54-58,76-93,95-106,108-139,113,142-148`; `report.py:71-118,
  169-253`; workflow `:1-13,42-51,68-79`; `flow.py:75-108,369-423`; `worker.py:162-255`; `config.py:60-110`;
  `compare.py:150-293`; `cli.py:33,118,133,153`; `ppp/ppp.v:60-75`; `ppp/omp_parallel.F90:290-333` (formula at
  `:317`); `setup.py:69-107,755-785`; `Makefile.Forthon:5-10`; `src/uedge/__init__.py:1-32`;
  `docs/reviews/AIUE-56-c1-gate.py`; `docs/reviews/AIUE-60-common-check.py`;
  `docs/reviews/omp-determinism-merge-validation.txt:55-96`; `docs/reviews/AIUE-61-validation.txt:120-149`; RCA
  §Linux characterisation (C1, C2, M3 rates); pre-fix `ppp/ppp.v` (`git show e52a44d:ppp/ppp.v`,
  `OMPJacNchunks /0/`).
- V4 inputs exist (`uedge-wt/logs/omp-determinism/chk_full_t4/{serial,run0..4}`), and so do the venvs named for V8
  and V9.
- Commands, all exit 0:
  - `pytest -q tests/deterministic_omp/harness tests/deterministic_omp/ci` (existing
    `venvs/omp-determinism-omp` interpreter, no install): **142 passed**.
  - `bash -n` and `shellcheck` on `run_omp_ci.sh`: clean.
  - `uvx --from actionlint-py actionlint .github/workflows/build-test-omp.yml`: clean.
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: **OK** (re-read notice only; "2 lock
    entries are no longer cited").
  - `uv run .claude/hooks/change_kind.py --range 9fa2a0e..HEAD`: **OK** (ticket branch; process = the two context
    files only).
- Ticket-page sanitiser: `ticket_page.py sanitize --repo <worktree> --max-chars 0` on the container paths (L1-m8).
- Not run: Docker, UEDGE builds or runs, Atlassian (per the review budget).
