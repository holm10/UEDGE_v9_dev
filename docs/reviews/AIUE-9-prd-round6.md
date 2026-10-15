# PRD review: AIUE-9 "Create end-to-end test suite" (round 6)

PRD: `docs/prds/AIUE-9-create-end-to-end-test-suite.md` (1074 lines, uncommitted in worktree `AIUE-9-planning`)
Repo checked: worktree `AIUE-9-planning` at `0fac655` (v9-develop). Old suite: `upstream/pytests` at `b535508`
(not re-read this round; no claims about it changed).
Previous rounds: 1 (REVISE, 0/7/9), 2 (REVISE, 0/1/8), 3 (REVISE, 0/1/7), 4 (REVISE, 0/1/5), 5 (REVISE, 0/1/4).
Reviewer: uedge-reviewer (PRD stage), round 6, 2026-10-14.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 3 MINOR.

## Summary

All five round-5 findings are resolved, and I checked each fix against the code. `omp_check.py` now starts from the
perturbed `base_state.h5` with the normal `ftol`, so `nksol` always gets past `nkstp0` and builds a Jacobian. It runs in
its own process with `OMP_NUM_THREADS=N`, which avoids the `Nthreads` clamp. It also fails unless effective
`Nthreads > 1` and both check banners appear, and both banners exist in the code. The two-pass `ylodt` sequence in
step 6 matches `bbb/odesolve.m:149-152`. The mutation counts agree in all five places. The revisions introduced three
small problems, all of which a ticket can settle:
- stale `pull_request` trigger text that contradicts the new `pull_request_target` design;
- a CODEOWNER-approval rule that GitHub cannot satisfy on this single-owner repo when the owner opens the PR;
- a convergence test that uses a different norm from `nksol`'s own stopping test.

None of them would make `/spec` slice a wrong ticket, so they are listed as MINOR for `/spec`.

## Findings

### MINOR

**P6-m1: The guard's trigger is still `pull_request` in two places.**
- *Location:* §4 Integration, line 155 ("It runs on `pull_request` events only (opened, synchronize, reopened,
  edited)"), and §7.6, lines 596-597 ("It runs on `pull_request` events …").
- *Problem:* The P5-m3 fix moved the guard to `pull_request_target`, and the following places say so:
  - the §6 tree, line 346;
  - §7.6, lines 635-640 and 647;
  - §11, line 888 (the base-branch copy judges the PR).

  The two stale sentences contradict that. This matters for security. On `pull_request`, GitHub runs the PR head's copy
  of `reference-guard.yml`, which is exactly the hole P5-m3 closed. A ticket written from §4 alone would reopen it. The
  §11 test PR at line 888 would catch it, but only after implementation.
- *Acceptance:* §4 line 155 and §7.6 lines 596-597 say `pull_request_target` (same activity types).

**P6-m2: CODEOWNER approval cannot be given on the owner's own PRs.**
- *Location:* §7.6, lines 617-620 and 641-643; §11, lines 886-887; §6 tree, line 347; §8 "Added".
- *Problem:*
  - `origin` is `holm10/UEDGE_v9_dev`, a public repository owned by a user account (GitHub API: `owner.type = User`).
  - The epic owner is the only CODEOWNER named for `tests/**` and `.github/workflows/**`.
  - GitHub does not let a PR author approve their own PR. Agent-pipeline PRs are opened under the owner's account,
    for example PR #1 from `holm10/feature/v9-ai-layer`.
  - With "Require review from Code Owners" on, every PR that touches `tests/**` therefore needs an admin bypass, or a
    second account. That includes every reference regeneration and every new-switch variant. If the rule is
    bypassable, then "CODEOWNER approval" in practice just means "the owner merged it".
  - The §11 criterion "rejected unless it declares `Test criteria: loosened` and has CODEOWNER approval" cannot be
    demonstrated as written.
  - Separately, the `CODEOWNERS` file appears in the §6 tree, but §8 "Added" does not list it, and the Phase 3
    deliverables do not mention it.
- *Acceptance:* §7.6 says how approval is satisfied when the epic owner is the author. Any one of these would do:
  - agent PRs come from a separate bot or machine account;
  - an admin bypass counts as the approval and is recorded in the PR;
  - CODEOWNERS is dropped, and the guard's `Test criteria: loosened` declaration plus `pull_request_target` carry the
    protection alone.

  The §11 criterion matches that choice, and `CODEOWNERS` is listed in §8 "Added" and in Phase 3.

**P6-m3: The §7.1 convergence test uses a different norm from `nksol`.**
- *Location:* §7.1, lines 370-377 (the check, and the new reconvergence fallback); Phase 1, lines 918-919.
- *Problem:*
  - The check is "scaled `fnrm` (`issfon=1`) must be ≤ the case's `ftol`". `fnrm` is the L2 norm `vnormnk`
    (`svr/nksol.m:1404-1418`).
  - `nksol` declares convergence on the max norm: `fmax = max|sf·f| ≤ ftol` (`svr/nksol.m:1244-1246`), and
    `≤ 0.01·ftol` in `nkstp0` (`:1399`).
  - A state that the fallback reconverges with `rundt` therefore meets `nksol`'s criterion, but can miss the §7.1 check
    by up to a factor of `√neq` (about 60 for `d_c`).
  - The check and the fallback can disagree on the very family the fallback exists for. In practice Newton's quadratic
    convergence usually leaves a wide margin, so this is MINOR.
- *Acceptance:* §7.1 states one criterion that the fallback is guaranteed to meet. One example is `nksol`'s own
  criterion: `max|sf·f| ≤ ftol`, or equivalently that `exmain` from the stored state returns at iteration 0. Another is
  to state explicitly that the fallback reconverges until the L2 test passes.

### Notes to the user (decisions, not PRD defects)

- **Branch protection on a single-maintainer repo (see P6-m2).** Making `reference-guard.yml` a required status check
  works for owner-authored PRs. Requiring CODEOWNER review does not, unless you add a second account or accept admin
  bypasses. Which one is your call as repo admin. The PRD only needs to record it.
- I did not verify against GitHub documentation that a `pull_request_target` run is reported as a check on the PR head
  that branch protection can require. My understanding is that it is. The Phase 3 test PRs in §11 (lines 883-889)
  exercise this, so a problem would surface before the guard is relied on.

All 13 binding decisions are reflected without contradiction. Decision 3 ("converged starting points") is now
explicitly protected by the §7.1 fallback. That fallback is consistent with decision 11, because it reconverges on the
same grid. It also does not conflict with the §4 out-of-scope item, which concerns making mid-size cases.

## Status of previous findings (round 5)

| ID | Status | Evidence |
|---|---|---|
| P5-M1 `omp_check` can pass without a Jacobian or with 1 thread | **Resolved** | See note (a) below. |
| P5-m1 mutation count | **Resolved** | See note (b) below. |
| P5-m2 non-converged templates, no fallback | **Resolved** (criterion detail in P6-m3) | See note (c) below. |
| P5-m3 guard details | **Resolved** (new details in P6-m1, P6-m2) | See note (d) below. |
| P5-m4 `ylodt` packing | **Resolved** | See note (e) below. |

**Notes**

(a) **P5-M1.** §7.7, lines 665-684.
- **(a) Jacobian built.** The tool starts from the perturbed `base_state.h5` with the normal `ftol`. A few-percent
  perturbation puts `max|sf·f|` far above `0.01·ftol`, so the code goes past `nkstp0` (`svr/nksol.m:1014-1015,1399`)
  into the iteration block, where `pset` builds the Jacobian. This matches round 5's measurement on `d_only`: a state
  only 4x above the threshold already built one.
- **(b) Thread count.** The tool runs in its own process with `OMP_NUM_THREADS=N`, and `Nthreads=N`. The clamp at
  `ppp/omp_parallel.F90:296-303` runs inside a parallel region of `OMP_GET_MAX_THREADS()` threads, so `Nthreads=N`
  survives. The `measure_roundoff` N-thread row uses the same rule (lines 681-682).
- **(c) Fail conditions.** The tool fails unless:
  - the effective `Nthreads > 1`;
  - the `CheckJac` banner appears. It exists at `ppp/parallel.F90:112`; a mismatch ends in `xerrab` at `:150`, and the
    "identical" line follows;
  - `CheckPandf1` ran. Its line "Serial and parallel pandf are identical for nfe =" is at `ppp/omp_parallel.F90:987`.
- The `ppp.v` names `OMPParallelPandf1`, `OMPParallelJac`, `Nthreads`, `CheckPandf1` and `CheckJac` exist
  (`ppp/ppp.v:6-15`).

(b) **P5-m1.** §7.8 line 703 lists 21 + 4 = 25, with both range mutations at lines 708-710. The other counts agree:
- §11: lines 861 and 872 (25/25), and line 873 (both range mutations by locality);
- Phase 2: line 949 (23/25, range mutations pending);
- Phase 3: line 970 (25/25).

A grep for `24` and `/24` finds no leftovers.

(c) **P5-m2.**
- The measured non-convergence is recorded in §7.1 lines 372-373, and in §15 lines 1052-1054.
- The fallback (same grid, reference commit, `rundt`, `converged_state.h5`, commit and `fnrm` in `family.toml`, epic
  owner confirmation) is at lines 374-377, with the Phase 1 deliverable at lines 918-919.
- It is consistent with decisions 3 and 11.

(d) **P5-m3.**
- **`pull_request_target`.** The base-branch workflow and script are used, the PR head is read as data, and the
  permissions are read-only (lines 634-640).
- **Separate declarations.** `Test criteria: loosened` is distinct from `Default results: changed` (lines 617-620).
- **Self-match.** The skip/xfail scan is `ast`-based, so it does not match its own strings (lines 630-633).
- **CODEOWNERS and required check** (lines 641-643).
- **CLAUDE.md rule** naming all three declarations (lines 169-170 and 798-799).
- Two stale trigger sentences remain (P6-m1). CODEOWNERS feasibility is P6-m2.

(e) **P5-m4.** Step 6, lines 253-260.
- `exmain` sets `ylodt(i) = (1-isyloext)*yl(i) + isyloext*yloext(i)` (`bbb/odesolve.m:149-152`). `yloext` and
  `isyloext` are at `bbb/bbb.v:1311-1312`; neither is tagged `+input`.
- Pass (a) obtains `y_c` packed by UEDGE with the variant applied. This matters for `isflxvar`/`isrscalf` scaling.
- The rest of the cited chain also holds:
  - `fqydt` reads the `*s` face values (`bbb/pandf_potencur.m:217-222`);
  - these are re-derived from `nis`/`tis`/`phis` in `convsr_vo2` (`bbb/convert.m:858-930`), which `pandf` calls through
    `convsr_vo` (`bbb/pandf.m:589`, `bbb/convert.m:157-164`);
  - the old-time copies `ni0`/`up0`/`te0`/`ng0`/`phi0` made at `odesolve.m:131-146` are not read in `bbb/pandf*.m`,
    `convert.m` or `oderhs.m` (grep).

  Step 6c's reset of the `*s` arrays is therefore sufficient.

## What was checked and how

**PRD.** I read it in full (1074 lines) and the round-5 review. I grepped the PRD for mutation counts, guard triggers
and declaration keywords.

**Code (worktree at `0fac655`, `sed -n` / `grep -n`)**
- `ppp/omp_parallel.F90:280-330`: the `InitOMPJac` clamp, inside the parallel region.
- `ppp/omp_parallel.F90:975-990`: the `CheckPandf1` output line.
- `ppp/parallel.F90:95-152`: `CheckJac` banner, `xerrab`, "identical" line.
- `ppp/ppp.v`: variable names.
- `svr/nksol.m`:
  - `:1005-1015`, initial `f` and `nkstp0`;
  - `:1244-1246`, the max-norm stopping test;
  - `:1399`, `nkstp0` at `0.01·ftol`;
  - `:1404-1418`, `vnormnk` is L2.
- `bbb/odesolve.m:126-152`: old-time copies, `ylodt`/`yloext`. Also `bbb/bbb.v:1308-1312` and `bbb/pandf.m:728-742`.
- `bbb/pandf_potencur.m:210-225`, `bbb/convert.m:157-164,372,850-932`, `bbb/pandf.m:589,596`.
- AI-layer line references for the adopt/retire PRs, unchanged and still correct:
  - `.claude/skills/validate/SKILL.md` §4;
  - `init-project/SKILL.md:59-62`;
  - `execute/SKILL.md:57`;
  - `implement-fix/SKILL.md:58,74`;
  - `.claude/hooks/check_context_refs.py:55`.
- `bbb/bbb.v:3377,3397`: `pandf` and `ffun` are Python-callable, which `measure_roundoff`'s `ffun` OpenMP row needs.

**Repository ownership.** I read `git remote -v`, then made an unauthenticated GitHub API call (`curl
https://api.github.com/repos/holm10/UEDGE_v9_dev`). It returned public, `owner.type = User`, `holm10`. `gh` is not
installed, so I could not check collaborators or branch-protection settings.

**Runtime.** No builds, no test runs, and the installed `~/.pyenv/versions/claude` build was not used this round.

**Web.** One search on whether `pull_request_target` works as a required check. It was inconclusive, so the point is
recorded as a note, not as a finding.

**Decision fidelity.** All 13 Appendix decisions were checked against §4, §6, §7.1, §7.6, §7.7, §11, §12 and §15.

**Template.** All 15 `create-prd` sections are present. The assumptions in §15 are updated for the convergence finding.
