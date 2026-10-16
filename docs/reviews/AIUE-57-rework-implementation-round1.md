# AIUE-57 rework implementation review, round 1 (covers plan Revision 1): OpenMP CI job `build-test-omp.yml`

Reviewer: uedge-reviewer (independent). Stage: implementation. Branch `feature/v9-AIUE-57-omp-ci-job` @ `77715c6`
(product `8416361`, code facts `97884a0`, record `77715c6`; plan revision `e51e2c0`), on the combined branch
`bugfix/v9-openmp-determinism-fix` @ `9fa2a0e`. Reference: ticket AIUE-57 acceptance criteria, plan
`.claude/plans/AIUE-57-omp-ci-job.md` (Amendment 1 + Revision 1), plan review
`docs/reviews/AIUE-57-rework-plan-round1.md` (REVISE 0/2/8) and its response.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 6 MINOR.

## Summary

The rework does what Revision 1 promised, and I checked each part against the code and the run outputs rather than
the record. The common-block result now reaches `report.py` and the exit code. The tolerance mode is falsifiable: four
mutations of `report.py` and five of `jac_bound.py` (bound condition dropped, missing `bound.json` treated as "not
applied", common-block code not folded in, flow 1-codes kept in tolerance mode, permutation check removed, and others)
each make at least one unit test fail. Re-running `jac_bound.py` on the V5 and V6 Docker outputs reproduces every
recorded `bound.json` byte for byte (as parsed JSON). Re-running `report.py` reproduces V5 PASS (exit 0), V6 FAIL
(exit 1), V8 tolerance PASS, V8b FAIL and V9 FAIL. An independent dense-matrix script reproduces the macOS C2 deviation
(5.6229e-10, 2 entries, Te magnitude ratio 1) that V8/V8b rest on. What remains is minor: two fail-open corners in
tools off the CI path, one pre-registered criterion met only in part (V6b), and the nightly set's untested Linux
configurations. Subject to the first native GitHub run, which the merge condition already requires, the job is ready
to merge into the combined branch and to gate its PR.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I1-m1: `jac_bound.py` passes when there is nothing to judge.**
- Location: `tests/deterministic_omp/ci/jac_bound.py:192-200`, `:204-214` (flow mode) and `:232-248` (check-dir mode).
- Evidence (reproduced):
  - A check directory with only `serial/` gives `BOUND PASS`, exit 0.
  - A flow directory with an empty `tebox/jac_t2/` gives `BOUND PASS (tol 1e-06, post_exmain)`, exit 0.
- In CI this is caught: `report.py` `bound_status` (`:112-117`) turns "no run entries" into an ERROR (exit 2), so the
  CI path fails closed.
- Check-dir mode has no such backstop. That is the mode `linux/gate_flows.py` uses and the one the Linux README now
  recommends.
- Acceptance: a group or check directory with no `run*` entries is exit 2 (or at least is reported as "no run
  judged"), with a unit test.

**I1-m2: `linux/README.md` says `gate_flows.py` can call `jac_bound.py`, but `gate_summary.py` silently summarises
nothing.**
- Location: `tests/deterministic_omp/linux/README.md` (new note after the table); `linux/gate_summary.py:7`.
- Evidence:
  - `gate_flows.py ci/jac_bound.py <root> <harness> fix=<V5 tebox1>` works: exit 0, every run judged.
  - `gate_summary.py` on that output prints nothing and exits 0. Its regex expects `PASS (worst magnitude ratio …,
    worst |a-b|/rowmax …)`, while `jac_bound.py` prints `PASS (post_exmain: worst magnitude ratio …, worst
    |a-b|/base …, …)`.
- These are offline tools, not the CI path.
- Acceptance: either the note says `gate_summary.py` only parses the AIUE-56 script's output, or one of the two
  formats is adapted.

**I1-m3: V6b meets its pre-registered criterion only in part, so the plan's acceptance criterion "V1–V10 pass as
pre-registered" is not literally met.**
- Location: `docs/reviews/AIUE-57-validation.txt` §9 V6b; plan, Testing strategy V6b ("exit 2, ERROR naming
  `OMPJacMinChunkLen`").
- What was met: exit 2 and fail-closed behaviour. I checked `logs/AIUE-57-rework/docker/base_v6b/ci.log:44-57`
  (`GATED [C1 bound] ERROR …`, `OMP CI RESULT: ERROR (exit 2)`).
- What was not met: the message is Forthon's generic `ppppy.error: no such attribute`. The record says so honestly.
- I disagree with the record's reason that naming the attribute "would need a harness change". A pre-flight check in
  the CI layer would do it: for example, the smoke step (`run_omp_ci.sh:119-120`) could check `hasattr(ppp, k)` for
  every key of every flow's `ppp` field and exit 2 naming the key.
- Impact is low. In CI the scripts and the build come from the same tree, so the case arises only for `RUN_TREE`
  replays against older builds, or for a future PR that renames the knob.
- Acceptance: either the cheap pre-check, or an explicit owner acceptance of the deviation, recorded in the PR notes.

**I1-m4: The nightly set gates bitwise on configurations with no Linux evidence.**
- Location: `run_omp_ci.sh:73-74` (`all1`, `all`: `--all`, 2/4/8 threads, both arms, `jac` gated); merge condition
  (workflow header `:11-14`, README "Merge condition").
- Evidence:
  - AIUE-61 R5 (`docs/reviews/AIUE-61-validation.txt:138-149`) shows Linux bitwise equality only for `tebox` (25
    chunks), `full` and `up`.
  - The other `--all` configurations (`te`, `ti`, `ng`, `phi`, `te_phi`, …) at 2/4/8 threads with the default
    partition were never run on Linux.
  - The merge condition covers only the first PR (`pr` set) run, and a scheduled nightly can run only after the
    merge.
- A red first nightly on `v9-develop` is therefore possible and would not be a regression.
- Acceptance: the README or PR notes say that the nightly set is not yet validated on Linux, and what the owner does
  with a red first nightly. Optionally, run a nightly replay in Docker, or a one-off `workflow_dispatch` with
  `set: nightly` right after the merge.

**I1-m5: In `--itermx` flows the tolerance mode bounds only the last Jacobian, while earlier Jacobian sections may
differ by any amount.**
- Location: `report.py:136-142` (`tolerable`) with `:206-210`.
- What happens: a group whose only failing sections are `jacobian:*` (for example `jacobian:captured[0]` from
  `sfsetnk`) is accepted if the last, permuted `post_exmain` is within V.
- Why this is safe in practice: the first (`sfsetnk`) Jacobian feeds `sfscal`, and every later one moves `yldot`/`fnrm`.
  In V6, `full` and `tebox` failed on `sfscal`. The README also says the mode "cannot rescue" `--itermx` flows.
- Why it is still worth fixing: the guarantee is incidental, not structural.
- Optional resolution: restrict tolerance acceptance to one-evaluation flows (`settings.itermx` null), where
  `post_exmain` is the same matrix as `captured[0]`. I confirmed this in the records: V8 `post_exmain_from=sfsetnk`,
  capture count 1. Alternatively, state the limitation in the `report.py` docstring.
- The workflow never sets the mode, so CI is unaffected.

**I1-m6: Wording.**
- (a) `jac_bound.py` prints "worst magnitude ratio 0" for configurations without Te rows (V5 `up1`). The magnitude
  check is vacuous there by design (it is AIUE-56's Te-row check), but "0" reads like a result. Printing "n/a (no Te
  rows)" would be clearer.
- (b) `.claude/context/openmp-jacobian.md` (CI paragraph) says "Linux x86-64 equals serial bit for bit with the fixed
  partition" without the README's qualifier "emulated x86-64". All Linux evidence so far is Rosetta-emulated.

## Status of previous findings (plan review round 1)

| Finding | Status | Evidence (checked myself) |
|---|---|---|
| L1-M1 common-block result | **Resolved** | `run_omp_ci.sh:125-141`: the check never exits the script. An empty `PKGDIR` (`find_spec` is `None`, so an AttributeError with stderr suppressed) gives `COMMON=2`. `--common-code` is passed at `:188`. `report.py:327-333`: folded with `max`, a `GATED [common-block]` line, and the `COMMON-BLOCK` line. `common_check.py:82-84`: no `bbb_p.F90` → 2. `test_common_block_fail_with_passing_flows_is_a_red_job` checks exit 1 and the FAIL headline in `summary.md`. Mutation (not folding the code) → that test fails. V6c ran inside the V6 run (`docker/base/ci.log`). |
| L1-M2 tolerance falsifiers | **Resolved** | `test_tolerance_i_bound_fail_stays_fail` and `test_tolerance_ii_missing_bound_is_exit_2_never_a_pass` (no file, no group, no run). Mutations: dropping the bound condition fails test (i); treating a missing `bound.json` as "not applied" fails 2 tests. V8b reproduced: `report.py --gate-mode tolerance --tol 2e-10` on `v8b/tebox1` → exit 1, "C1 bound (tol 2e-10): EXCEEDED in 3/3 runs … not within tolerance 2e-10 (C1 bound)". |
| L1-m1 exit recomputation, cap | **Resolved** | `report.py:318-320,344-346`: in tolerance mode a flow's 1 is dropped and its 2 kept. `run_omp_ci.sh:93-100`: `0 < v <= 1e-6`, else exit 2 (NaN and inf fail the comparison). Bound/`--tol` mismatch → exit 2 (`:350-354`, tested). Mutation (keeping flow 1-codes) → `test_tolerance_accepts…` fails. |
| L1-m2 last-Jacobian scope, permutation | **Resolved** | Stated in the `jac_bound.py` docstring, the `report.py` docstring and summary line `:399-401`, and the README. `judge` raises CannotJudge on a `post_exmain_permuted`/`_from` disagreement (`:104-107`; test, and a mutation fails 2 tests). V6 outcomes pre-registered per group, and the record matches them. |
| L1-m3 fail closed, layout, `--harness`, Linux note | **Resolved** (two corners left: I1-m1, I1-m2) | The `__main__` wrapper turns tracebacks into exit 2. `report.py` `bound_status` fails closed on a missing file, group or run. `test_flow_layout_keys_and_ignored_arms` and `test_check_dir_mode_accepts_harness…` exist. V4 reproduced. |
| L1-m4 chunk count | **Resolved** (informational, as Revision 1 chose) | `TEBOX_PPP` at `run_omp_ci.sh:68`. The `report.py` regex `NchunksJac:\s*(\d+)` matches the format at `omp_parallel.F90:330-333` (`*OMPJac* Nthreads:   2 NchunksJac:    25 …` in `docker/fix/tebox1/tebox/jac_t2/run0/run.log`). V5 ci.log shows `CHUNKS … NchunksJac 25` for every Te-box group. It is not gated: a knob that silently stopped working would show "NchunksJac 1" in the summary but stay green. That is acceptable as decided, but gating "25 expected" would be cheap. |
| L1-m5 M3 guard power | **Resolved as optional** | V11 was run and recorded: PASS 3/3 on the legacy partition, so `up1`'s detection power is not shown. The record says so, and `up1` is first in the cut order. The seeded-C1 control was not run (optional). |
| L1-m6 budget, merge condition | **Resolved** | Cut order is in the `run_omp_ci.sh:22` header and in the README "Budget". The 15–22 min estimate is in the README. The merge condition is in the workflow `:11-14`, the README and `testing.md`. |
| L1-m7 references | **Resolved** | The header is rewritten. `openmp-jacobian.md:116-117` also names `tests/deterministic_omp/ci/common_check.py`. |
| L1-m8 ticket-page sanitiser | **Not on this branch** (AI layer; the main session handles it). Not verified here. |

## Answers to the main session's questions

- **V5 (Docker replay PASS, bitwise, NchunksJac 25).** Confirmed from `docker/fix/ci.log` and by re-running both
  tools:
  - Flow codes 0,0,0,0.
  - All 4 recomputed `bound.json` equal the recorded ones; the worst deviation is 0.
  - `report.py` → exit 0.
  - The common-block ELF path works on a real Linux build (`nm -D -S`, import order parsed, bbbpy 728 B and apipy
    96 B detected).
- **V6 (pre-fix FAIL; `tebox1` bound EXCEEDED, `tebox`/`full` within).** Reproduced: report exit 1, and `tebox1` bound
  EXCEEDED (2.58e+38, Te max 2.367e+43 against 5.564e+05).
  - `tebox` and `full` are "within" (2.22e-16 and 0) because their `post_exmain` is the second, `psetnk` Jacobian
    (record: `post_exmain_from=psetnk`, capture callers `['sfsetnk','psetnk']`). C1 corrupts only the first Jacobian
    of a session (RCA E2).
  - This is the documented last-Jacobian scope, not a defect. Those groups fail bitwise, and on `sfscal`.
- **V6b (partial).** Acceptable for gating: it fails closed with exit 2. The criterion's diagnostic part is not met.
  See I1-m3 for a cheap CI-layer fix, or have the owner accept the deviation.
- **V6c (common check PASSes on the pre-fix build): was the plan wrong?** Yes. The plan's expectation was wrong, and my
  round-1 plan review did not catch it.
  - The FAIL in `docs/reviews/AIUE-60-amendment1-controls.txt:20-32` came from AIUE-60's *pre-amendment* build
    `02e6e60`, which had added threadprivate scalars to `com` (10 variables, 80 B) and `aph`.
  - The same file (`:5-17`) shows the AIUE-56 build, which has no extra threadprivate scalars, PASSing with
    `bbbpy 712 B; apipy 96 B`. That is exactly V6c's result on `e52a44d`.
  - So PASS is the correct outcome. The plan's hedge ("if PASS, record it; the FAIL path is then covered only by V1")
    applies.
  - On ELF, real data exercise only the definer detection, not the FAIL decision. The FAIL decision is
    platform-independent logic covered by unit tests, and AIUE-60 showed it on real Mach-O data with the same logic.
    Adequate.
- **V7 (seeded race FAIL).** Recorded: every Te-box jac group red, 15/16 runs red. Not rerun (no Docker for this
  review).
- **V8/V8b/V9.**
  - Reproduced with `report.py` on the stored outputs: V8 tolerance → exit 0 TOLERATED; V8b → exit 1 with the bound
    named; V9 → exit 1.
  - V9 is red through both the bound and a non-Jacobian section (`sfscal`), so V8b is the real test of the bound
    condition.
  - My independent dense computation of V8's deviation agrees with `bound.json` to all printed digits.
- **V11.** `up1` cannot show detection of an M3 recurrence. Recorded honestly; `up1` stays a cheap guard.
- **Deviations.**
  - `gen_dir.sh` is a sound extraction of the planned workflow step: it requires exactly one `build/temp.*` with
    `bbb_p.F90`, exits 1 otherwise, and is shared with the replay script.
  - The default harness in check-dir mode (the one next to the script) is sensible. Both deviations are acceptable.
- **Workflow.**
  - The header gives what is gated and the merge condition.
  - The gen-dir step is present, and a failure in it fails the job.
  - `bound.json` is added to the artefacts, and there is no `LDFLAGS`.
  - Triggers, `permissions: contents: read`, concurrency and timeouts (30/150) are unchanged. I checked this with
    `git diff e51e2c0 8416361 -- .github/workflows/build-test-omp.yml`.
- **`common_check.py` ELF path.** It fails closed:
  - an `nm` non-zero exit or empty output → 2;
  - `nm` missing (FileNotFoundError) → caught by the `__main__` wrapper → 2;
  - no definer → 2;
  - size unknown → 2.
- **Ready to merge into the combined branch and to gate a PR?** Yes, subject to the first native `ubuntu-latest` run,
  which the merge condition already names.
  - If AIUE-57 merges into `bugfix/v9-openmp-determinism-fix` first, that first native run is the combined branch's
    PR to `v9-develop`, and the merge condition then applies to that PR.
  - The nightly set is a separate, unvalidated risk (I1-m4).

## Not independently verified (environment)

- **Native `ubuntu-latest`:**
  - bitwise equality without Rosetta;
  - Python 3.11 (the replays used 3.12);
  - `build/temp.*` in-tree on the runner;
  - `nm -D -S` output of the runner's binutils;
  - the PR wall time against the 20-min budget (emulated: build 175 s plus script 481 s);
  - annotations and the step summary;
  - the scheduled nightly;
  - the ticket's 20/20 red-run criterion.

  Only the first PR run can confirm these. I checked the code paths and the Docker replay outputs.
- **V5, V6, V6b, V7, V11 Docker runs:** not rerun (no Docker or UEDGE runs in this review). I re-checked their
  stored outputs by re-running `jac_bound.py` and `report.py`. For V7 I only read the record.
- **V8, V8b, V9 macOS runs:** not rerun. Their stored outputs were re-analysed.
- **Confluence ticket page and Jira state:** no Atlassian access.

## What was checked and how

- Read in full: `ci/jac_bound.py`, `ci/report.py`, `ci/run_omp_ci.sh`, `ci/gen_dir.sh`, `ci/common_check.py`,
  `ci/test_report.py` (new tests), the workflow, `linux/run_ci_replay.sh`, `linux/gate_flows.py`,
  `linux/gate_summary.py`, the README CI section diff, the context-file diffs, plan Amendment 1 and Revision 1, and
  validation §9.
- Harness facts:
  - `flow.py:75-110` (`group_verdict`, `failing_sections`, `deterministic`) and `:147-161` (`exit_code`);
  - `worker.py:162-255` (`post_exmain_from`/`_permuted`, the order `ppp` is applied in);
  - `config.py:88-91` (`OMPJacVerbose` is not a forbidden diagnostic);
  - `ppp/omp_parallel.F90:304-333` (chunk formula and print format).
- Unit tests: `venvs/omp-determinism-omp/bin/python -m pytest -q -p no:cacheprovider tests/deterministic_omp/harness
  tests/deterministic_omp/ci` gives **173 passed**. The breakdown is 22 report, 10 jac_bound and 9 common_check, as
  the record says.
- Mutation tests, on scratch copies in `/tmp/aiue57-rev/mut`:
  - `report.py`: 4 mutations, each caught (1–2 failures).
  - `jac_bound.py`: 5 mutations (permutation check removed, `loc` forced, magnitude check off, tolerance hard-coded
    to 1e-3, judge error turned into "skipped"), each caught (2–3 failures).
- Static checks: `shellcheck` on the three shell scripts is clean; `bash -n` is OK; `uvx --from actionlint-py
  actionlint .github/workflows/build-test-omp.yml` exits 0.
- AI layer: `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` gives **OK** (re-read notice; "2
  lock entries are no longer cited"). `uv run .claude/hooks/change_kind.py --range 9fa2a0e..HEAD` gives **OK**: the
  ticket branch's process files are only the two context files, committed in `97884a0` with `AI-layer: code-facts`;
  there are no skill, agent or hook changes.
- Re-run on existing outputs, read-only (scratch outputs written to `/tmp/aiue57-rev`):
  - `jac_bound.py --flow` on `docker/fix/{tebox1,tebox,up1,full}` and `docker/base/{…}`: codes 0,0,0,0 and 1,0,0,0;
    all 8 JSONs equal the recorded `bound.json`.
  - `report.py` on symlinked copies:
    - V5 → exit 0;
    - V6 → exit 1, with FIRST MISMATCH te(ix=4,iy=18) and per-group lines as recorded;
    - V8 tolerance → exit 0;
    - V8b → exit 1;
    - V9 → exit 1.
  - `jac_bound.py --harness … chk_full_t4` (V4) → 5× PASS, worst 4.59e-09, raw 1.983e-04 "not judged", exit 0.
  - Independent dense recomputation (`/tmp/aiue57-rev/scripts/indep.py`) of V8 bitwise `tebox1` runs 0–2: worst
    5.6229e-10, 2 entries, Te ratio 1. This matches `bound.json`.
  - `gate_flows.py` with `jac_bound.py` and then `gate_summary.py` (I1-m2); empty run directories (I1-m1).
- Records: `post_exmain_from` and capture callers for V8, V5 `tebox`, `full` and `up1`.
  `docs/reviews/AIUE-60-amendment1-controls.txt` and `AIUE-60-common-check-r2.txt` (V6c). `AIUE-61-validation.txt:120-149`
  (Linux coverage, I1-m4).
- Commits: `77715c6` touches only the validation record. The V5 tip `97884a0` = T.
