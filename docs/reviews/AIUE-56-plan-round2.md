# AIUE-56 plan review, round 2

Plan: `.claude/plans/AIUE-56-omp-jacobian-fix.md` (revised, untracked on `bugfix/v9-AIUE-56-omp-jacobian-fix` at `3865c79`).
Previous: `docs/reviews/AIUE-56-plan-round1.md` (REVISE, 0/3/7) and `docs/reviews/AIUE-56-plan-round1-response.md`.
Reviewer: uedge-reviewer (plan stage, finding prefix L). Read-only; no builds or runs.

## Verdict

**REVISE**: 0 BLOCKER, 3 MAJOR, 1 MINOR (new). Of the round-1 findings, 7 are resolved and 3 are partially resolved
(m2, m3, m5). Round-1 m2 is promoted into L2-M2.

## Summary

The code change is unchanged and still correct: swap the `OmpCopyScalar*` and `OmpCopyPointer*` blocks at
`ppp/omp_parallel.F90:681-693`. The default-safety argument still holds. The revision handles the dependency
deviation, the measurement counts and the neutral reporting of the residual well.

Three verification and acceptance problems remain, and two of them come from the new material:

- **The tool pin.** The plan pins the harness and flow to `feature/v9-AIUE-52-omp-test-flow`. That branch carries
  the AIUE-49 core *before* its review fixes. The old core returns AGREE when no OpenMP code ran, and AGREE on
  records that differ. Pre-fix these defects were harmless, because every run failed anyway. Post-fix, a false
  AGREE is exactly the error that matters.
- **The C1 acceptance.** "Sparsity pattern equal to serial in every run" is now this ticket's own acceptance. The
  RCA's E3 evidence already shows it can fail after the swap because of the residual.
- **An overclaim.** The plan says a clean (3) would also meet the epic's full Jacobian-track criterion. Protocol (3)
  doesn't cover that criterion.

## Findings

### MAJOR

**L2-M1. The pinned harness and flow are the pre-review AIUE-49 core, which can report AGREE falsely.**
*Location:* Dependencies (lines 23-27), Testing 3-5 (lines 94-103).

- **What is wrong.** "harness + flow (`feature/v9-AIUE-52-omp-test-flow`, AIUE-49 core)" names a branch built on
  the AIUE-49 harness at `fbe0adf`. The fixes from AIUE-49's review are not on it:
  - `git merge-base --is-ancestor e1f5808 HEAD` → lacks; `8fddd95` → lacks.
  - There is no `check_arm` in `AIUE-52/tests/deterministic_omp/harness/compare.py`. The uncommitted AIUE-52 changes
    touch only `cli.py`, `config.py`, `flow.py` and the tests.
- **The open AIUE-49 findings that bite this ticket's post-fix runs**
  (`AIUE-49/docs/reviews/AIUE-49-implementation-round1.md`, and the fixes listed in its response):
  - **I1-B1:** AGREE (exit 0) when no OpenMP code ran. A mis-built `AIUE-56-omp` venv, or a switch that didn't
    take, would pass every run of Testing 3.
  - **I1-M3:** the comparator returns AGREE on inputs that differ (duplicates, one-sided vectors). Chunked CSR
    assembly is exactly where such faults come from.
  - **I1-M2:** the post-`exmain` Jacobian after `psetnk` is RCM-permuted but is localised as if it were not. The
    `--itermx 3` runs would report wrong rows and cells, and Testing 4's neutral residual report is built on rows
    and cells.
  - **I1-M1:** the ±0 rule is missing on the RHS-arm `yldot`. The jacrhs arm (Testing 5) would fail even on a
    correct state. It is report-only, but its data feeds AIUE-58.
- **Why it matters.** AIUE-54's pre-fix data with this tool is still valid, because every run failed. The positive
  result this ticket wants ("0 mismatches", "pattern equal") is the result the old tool can't certify.
- **Resolve by:**
  - running every gating comparison with a harness that contains the AIUE-49 review fixes (`8fddd95`/`71b0e3b` or
    later): AIUE-52 rebased on the revised core, or `check` from the AIUE-49 worktree for the gating counts;
  - recording in the validation file, for each run, that `check_arm` reported no problems;
  - pinning that commit.

  If the flow can't be rebased in time, say which results came from the old core, and that those results don't
  count as AGREE evidence.

**L2-M2. This ticket's own C1 acceptance includes a criterion that the known residual already breaks.**
*Location:* Acceptance, "This ticket (C1)" (line 109-110). This promotes round-1 L1-m2, now that the criterion is
part of the ticket's own acceptance.

- **What is wrong.** "no ~1e43 entries, and the Jacobian sparsity pattern equal to serial, in every run of (3)".
- **Evidence.** RCA E3 (`AIUE-54/docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`, §C1 E3), with the identical
  swap, full problem, 4 threads, 2 runs:
  - run 2 had 416 serial entries missing and 3 extra in 7 Te rows. These are ulp-scale entries around
    `jaccliplim`, the M2 signature.
  - K=30 at 4 threads plus K=5 at 2 and 8 threads makes a pattern mismatch in some run very likely.
- **The conflict.** The ticket then fails its own acceptance for a reason that the plan itself (Testing 4) assigns
  to AIUE-55. The alternative is that the criterion gets relaxed after the fact, which is the bias that L1-M3 asked
  to avoid. "~1e43" also still has no threshold (round-1 m2).
- **Resolve by** an acceptance that C1 alone decides and that M2 can't break. Options:
  - the `TPCHK after-copy` checker, which reported 0 mismatching pairs in E3, at 2/4/8 threads on a scratch tree
    with the fix;
  - a stated bound: max|jac| equal to serial to a stated relative tolerance, and every differing or pattern-changed
    entry with |value| at most a stated multiple of ulp(yldot)/dyl;
  - an E2-style check: the first Jacobian of a process is in the same class as the second.

  Keep "pattern equal to serial" as a *reported* quantity under Testing 4, not as a pass/fail for C1.

**L2-M3. "If (3) shows 0 mismatches everywhere, the epic's full Jacobian-track criterion is met too" overclaims.**
*Location:* Acceptance (line 111).

The PRD MVP (`docs/prds/AIUE-8-…md:476-482`, §7.2 at `:327-339`) requires all of the following:
- the Jacobian, `sfscal` and the `fnrm` sequence over **≥ 3 Newton iterations**, for **every configuration at 2, 4
  and 8 threads**;
- the Jacobian taken at the raw capture point (unscaled, unpermuted, from `jac_calc*`).

Protocol (3) falls short in three ways:
- **Iterations.** `--itermx 3` runs only for the Te box and the full problem at 4 threads. Everything else is one
  evaluation.
- **Capture point.** The `AIUE-56-omp` build is `v9-develop` plus the swap, so it has no AIUE-47 capture hook
  (`bbb/bbb.v`/`bbb/oderhs.m` on `feature/v9-AIUE-47-raw-jacobian-capture`). Without the hook the harness keeps only
  the last `psetnk` Jacobian (`worker.py`: "last psetnk Jacobian: scaled, row-normalised, possibly RCM-permuted").
  The `sfsetnk` Jacobian and the intermediate Jacobians of a 3-iteration run are never compared.
- **Linux.** It is required, and the very next sentence (line 112-113) says it is not verifiable here.

A clean (3) would therefore be reported to the owner as "epic criterion met" on evidence that doesn't cover it.

*Resolve by:* deleting or rewording the sentence, e.g. "(3) covers the epic criterion for X, Y only; not covered:
…". Alternatively, add the missing runs: `--itermx 3` for every configuration at 2/4/8 threads, on a build with
the AIUE-47 hook (a scratch tree of AIUE-47 plus the swap, or after rebasing on merged AIUE-47). Either way, the PR
should list every acceptance line as met / not met / not run. That was the last sub-item of L1-M2 and is still not
promised.

### MINOR

**L2-m1. The AIUE-55 branch named in Dependencies does not exist.**
*Location:* line 22.
- **What is wrong.** The plan says AIUE-55 is being written on `feature/v9-AIUE-55-omp-jacobian-rca`. `git branch -a`
  shows no AIUE-55 branch, and there is no AIUE-55 worktree.
- **Resolve by:** saying "not yet started", or correcting the name once the branch exists.

## Status of previous findings

| Round-1 finding | Status | Evidence |
|---|---|---|
| L1-M1 dependencies not stated | **Resolved** | New "Dependencies and merge order" section (lines 14-28): the deviation is stated for the owner, the voiding condition if C1 is refuted, tool sources named with commits to be pinned in `AIUE-56-validation.txt`, the AIUE-54 baseline with negative-control re-runs, and the merge order. Owner agreement can't be obtained in an unattended run, and recording it for the owner is acceptable. The pin itself names the wrong harness revision: that is the new L2-M1. |
| L1-M2 protocol vs acceptance | **Resolved** (one sub-item moved to L2-M3) | Testing 3 now has K=30 one-evaluation and K=5 `--itermx 3` (Te box, full, 4 threads), K=5 at 2/8 threads, and K=5 for the six single-equation configurations. `--itermx` exists in both CLIs (`AIUE-52/.../cli.py:118,138`). The `pytests` requirement is covered by AIUE-53's serial check, which already includes pytests cases from D_only, D+C, D_mols, slab and fulltests, plus `-it5` variants (`AIUE-53/.../serial_check.py:66-85`), for both build pairs (`:583-586`). Linux is stated as not run. The "met / not met / not run per line" sub-item is still missing (L2-M3). |
| L1-M3 residual pre-labelled | **Resolved** | Testing 4 reports neutrally (rows/columns, cells, plate adjacency, ulp scale, run-to-run variation, serial-history test), and attribution is left to AIUE-55. The ticket's acceptance is separated from the epic's at lines 107-115. The new C1 acceptance has its own problem (L2-M2). |
| L1-m1 `copyin(emcoef)` | **Resolved** in the plan (lines 46-49) | The `openmp-jacobian.md` task (line 79) mentions only the copy order, not the aliasing/benign race. Optional. |
| L1-m2 indirect C1 criterion | **Partially resolved** | The static scan plus the `base-omp` negative control were added (Testing 1). I checked `scan_ompcopy.py:144-211`: it reads the order of the call lines in `OMPJacBuilder`, which are one per line (`ppp/omp_parallel.F90:683-692`), so it will flip from 12 to 0 with the swap. That makes it a check that the edit was made, not a runtime check. The "~1e43" threshold is still missing, and the sparsity criterion is now a gate (promoted to L2-M2). |
| L1-m3 citations | **Partially resolved** | The DATA statement for `ldf_api`/`mdf` is fixed (line 40). Line 40 still says `splinem` is "called from `readpost`". `splinem` is called from `bbb/odesetup.m:1130,1150`, and `readpost` (`api/apip93.m:3-42`) doesn't call it. The response's "Corrected" is not accurate. Don't copy this into the code comment. |
| L1-m4 debug switches | **Resolved** | GOTCHA at lines 73-74 and the code-comment instruction. |
| L1-m5 timing | **Partially resolved** | The metric and sample are now named (line 104-105). Three problems remain. `bbb.ttotjf` is not a `bbb` variable: it is `com.ttotjf` (`com/com.v:507`), wall clock via `system_clock` (`com/misc.m:91-104`), accumulated at `bbb/oderhs.m:4703`. The harness doesn't record it, and `elapsed_s` includes deck setup. AIUE-54's timings were taken at load average 10-75 ("upper bounds"), so comparing "before (AIUE-54 data)" with after isn't on the same machine and load. Re-time `base-omp` next to `AIUE-56-omp` in one session. |
| L1-m6 RHS arm | **Resolved** | Lines 50-51 and Testing 5. Note that AIUE-54 shows the jacrhs arm crashing (SIGSEGV) for `te` and `te_phi` and overflowing in `lusol0` on the full problem at 2 threads, so expect exit-2 runs there. |
| L1-m7 line drift | **Resolved** (rebuttal accepted) | `--fix` covers `openmp-jacobian.md`, which cites `:649`, `:715`, `:902`, `:953-955`. The RCA citing pre-fix lines on purpose is a correct argument. |

## What was checked and how

- **Revised plan and response.** Read in full and compared with the round-1 findings line by line.
- **Code references.**
  - `ppp/omp_parallel.F90:645` (`OMPJacBuilder` start), `:681-693` (copy blocks, one call per line), `:715`
    (`copyin(yinc,xlinc,xrinc,emcoef)`), `:748` (end).
  - `api/apip93.m:3,91,110` and `bbb/odesetup.m:1130,1150` (the `splinem` callers).
  - `com/com.v:507`, `com/misc.m:91-104` and `bbb/oderhs.m:4695-4703` (`ttotjf`).
- **AIUE-54 characterisation.** `AIUE-54/docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`: §Characterisation (matrix,
  K=20 rates, timing under load), §C1 E1-E4 (E3 full run 2 pattern changes after the swap) and §M2. The data are in
  `docs/rca/AIUE-8-data/` (CSV and two flow summaries; the jac arm is 0/20 for tebox and full, jacrhs 0/20 for
  tebox).
- **Harness revisions.**
  - The AIUE-49 branch log (`e1f5808`, `8fddd95`, `71b0e3b`), `compare.py:146-180` (`check_arm`),
    `worker.py:115-197` (capture hook), and `compare.py:233-234` (a hook in one record only is an error).
  - The AIUE-49 review round 1 and its response.
  - AIUE-52 ancestry via `git merge-base --is-ancestor`, plus `grep check_arm`. AIUE-52 `worker.py:70-115` keeps only
    the last `psetnk` Jacobian with `--itermx`.
  - AIUE-47's diff (`bbb/bbb.v`, `bbb/oderhs.m`: the capture hook).
- **Static scan.** `AIUE-50/tests/deterministic_omp/tools/scan_ompcopy.py:128-211` (order detection).
- **Serial check.** `AIUE-53/tests/deterministic_omp/harness/serial_check.py:9-18,60-90,583-597`: the case set and
  the build pairs.
- **PRD.** §7.2 (`:326-339`), the MVP success definition (`:476-488`), and P3-m1 (`:652-658`).
- **Branches.** `git branch -a` shows no AIUE-55.
- **Not done.** No builds or runs, by design.
