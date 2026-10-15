# PRD review: AIUE-9 "Create end-to-end test suite" (round 5)

PRD: `docs/prds/AIUE-9-create-end-to-end-test-suite.md` (1036 lines, uncommitted in worktree `AIUE-9-planning`)
Repo checked: worktree `AIUE-9-planning` at `0fac655` (v9-develop). Old suite: `upstream/pytests` at `b535508`
(read with `git show`/`git ls-tree`, not checked out).
Previous rounds: 1 (REVISE, 0/7/9), 2 (REVISE, 0/1/8), 3 (REVISE, 0/1/7), 4 (REVISE, 0/1/5).
Reviewer: uedge-reviewer (PRD stage), round 5, 2026-10-14.

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 4 MINOR.

## Summary

All five round-4 MINORs are fixed, apart from one leftover count. P4-M1 is fixed on paper: §4, §7.7, §8 and §9 now say
that `tests/tools/omp_check.py` keeps both `CheckPandf1` and `CheckJac`. The mechanism §7.7 specifies does not deliver
that, though. I ran the template states on an installed v9 build. Starting from the **converged** state with the case's
normal `ftol`, `nksol` stops at iteration 0 on `slab_phi` and `ortho`, so no Jacobian is built and `CheckJac` never runs.
A second, independent problem: `ppp` clamps `Nthreads` to `OMP_GET_MAX_THREADS()`, so with the harness's pinned
`OMP_NUM_THREADS=1` the "parallel" Jacobian runs on one thread. In both cases the check passes silently. That is the
P4-M1 coverage loss again, now hidden behind a tool that claims to do the check. The fix is three sentences in §7.7. The
MINORs are a mutation count that is now inconsistent, a Phase 1 fallback for templates that turn out not to be converged
(measured), and some details of the guard and of step 6.

## Findings

### MAJOR

**P5-M1: `omp_check.py` as specified can pass without comparing any Jacobian, or with only one thread.**
*Location:* §7.7 "OpenMP RHS + Jacobian check" (lines 642-654). Also §4 Out of scope (lines 186-190), §8 adopt PR
(lines 758-760), §9 (lines 800-801), and the §6 environment pin (line 241).

*Evidence.*

1. **Converged state + normal `ftol` → `nksol` returns before building a Jacobian.**
   - `nksol` evaluates `f` once and calls `nkstp0` (`svr/nksol.m:1005-1015`). That returns `iterm=1` when
     `max|sf·f| ≤ 0.01·ftol` (`svr/nksol.m:1394-1398`). This happens before `model`, the only path to `pset`/`jac_calc`.
     With `ftol = 1e-8` (`bbb/bbb.v:1204`; `slab` sets it again at `input.py:158`, `d_c` at `:135`) the threshold is
     `1e-10`.
   - I measured it on an installed v9 build (`~/.pyenv/versions/claude`, `uedge_ver 9.0.0-beta.0`). I used the
     unperturbed template `solution.h5` with the assembled `input.py` the PRD names, then `ftol=1e-8` and `exmain()`
     with `com.iprint=1`:

     | Family | `fnrm` at iter 0 | `max|sf·f|` | Newton iterations | Jacobian built |
     |---|---|---|---|---|
     | `slab_phi` | 1.33e-11 | 1.15e-11 | **0** (`iter=0 … iterm = 1`) | **no** |
     | `ortho` | 1.43e-12 | 1.08e-12 | **0** | **no** |
     | `d_only` | 4.59e-10 | 3.98e-10 | 1 | yes (barely: 4x the threshold) |
     | `d_c` (default family) | 8.98e-5 | 3.95e-5 | 2 | yes |
   - **Why `d_c` works today and may not after Phase 1.** It only builds a Jacobian because its template is *not*
     converged on this build (see P5-m2). If Phase 1 reconverges it to satisfy §7.1's convergence check, the default
     `omp_check` run may stop at iteration 0 as well. `d_only` shows what happens: after one Newton step its `fnrm` is
     1.9e-12.
   - **Today's check doesn't have this problem.** It runs in a `pytests/unittests/.../default` directory, whose
     `solution.h5` is the ±1 % perturbed copy. The blobs differ from the templates: `153c1e9` vs `c5d4abf` for D_only,
     `d9da824` vs `9baf307` for slab. So `nksol` always iterates there, and `CheckJac` always runs.
2. **`Nthreads` is clamped by `OMP_NUM_THREADS`.**
   - `ppp/omp_parallel.F90:296-303` calls `OMP_SET_NUM_THREADS(OMP_GET_MAX_THREADS())` and sets
     `Nthreads = OMP_GET_NUM_THREADS()` when `Nthreads` exceeds the maximum.
   - The harness pins `OMP_NUM_THREADS=1` before any import (§6 line 241), and §7.7 step 1 loads the family through "a
     `state.py` helper". If `omp_check.py` inherits that environment, `ppp.Nthreads=4` silently becomes 1, and the
     race check compares serial with single-threaded "parallel".
   - The same applies to `measure_roundoff.py`'s "OpenMP with N threads" row.
3. **Neither degradation is visible.**
   - On success, `CheckJac` prints a banner ("--- Checking whether parallel and serial evaluations of jacobian…",
     `ppp/parallel.F90:112-115`). On a mismatch it calls `xerrab`. If no Jacobian is built, it prints nothing.
   - §7.7 only asks for the output to be reported "verbatim". A run with no Jacobian therefore reads as a pass, and so
     does a run on one thread.

*Why this is MAJOR.* A ticket written from §7.7 would ship a tool that does not check the parallel Jacobian on two of
the five measured small families, and possibly not on its default family either. That is the coverage which P4-M1
required to be kept for the CLAUDE.md "OpenMP check" hard rule. The defect is hidden, which is worse than the round-4
state, where the gap was at least visible in the text.

*Acceptance.* §7.7 says all three of the following:
- **(a)** A Jacobian is always built. For example, start from `base_state.h5` (perturbed, which matches what today's
  check does), or otherwise force at least one `pset` call.
- **(b)** `omp_check.py` and `measure_roundoff.py`'s OpenMP row run with `OMP_NUM_THREADS` unset or ≥ `Nthreads`, not
  with the harness pin.
- **(c)** The tool **fails** unless the `CheckJac` comparison actually ran (banner present, or a Jacobian-evaluation
  count > 0) and the effective `ppp.Nthreads` after the run is > 1.

### MINOR

**P5-m1: The second range mutation is not counted (left over from P4-m5).**
- §7.5 (lines 530-533) now requires **two committed range mutations**: the `initialize_ranges` one and a "removes a
  single weak coupling from the evaluation window" one.
- §7.8 (lines 673-678) still lists 21 + 3 = **24**, with a single `initialize_ranges` patch. §11 (lines 828, 839) says
  24/24. Phase 2 (line 914) says "23/24 … The locality mutation is pending", and Phase 3 (line 935) says 24/24.
- *Acceptance:* add the window mutation to §7.8 and update the counts (25, and 23/25 in Phase 2), or say explicitly that
  it is a calibration-only patch outside the counted set.

**P5-m2: Some templates are not converged on v9. Phase 1 has no fallback.**
- §7.1 (lines 366-367) and §15 assume that the template states are converged, and Phase 1 "confirms" it.
- Measured on the installed v9 build: unperturbed template + assembled `input.py`, `ftol=1e50`, one `exmain`, then the
  scaled `yldot`. I cross-checked against `nksol`'s own iteration-0 `fnrm`, and the numbers match.

  | Family | Scaled `fnrm` | Converged to `ftol = 1e-8`? |
  |---|---|---|
  | `d_mols` | **2.2** (max entry 0.86) | no |
  | `d_c` | **9.0e-5** | no |
  | `d_only` | 4.6e-10 | yes |
  | `slab` | 1.3e-11 | yes |
  | `ortho` | 1.4e-12 | yes |
- The installed build may not be exactly `0fac655`, so Phase 1 must re-measure. But the confirmation step can plausibly
  fail, and the PRD does not say what happens then.
- *Acceptance:* §7.1 or Phase 1 states the fallback. For example: reconverge on the same grid with the family
  `input.py` on the reference commit, store the result as `converged_state.h5`, and record this in `family.toml`. This
  is not the "reconverging fine-grid cases" that §4 puts out of scope. Also see the note to the user below.

**P5-m3: Guard details introduced by the P4-m3 fix.**
- **The workflow file is head-controlled.**
  - The guard checks out the base copy of `check_reference_change.py` (lines 620-622).
  - But on `pull_request` events, GitHub runs the *PR's* version of `reference-guard.yml`. A PR can therefore edit the
    workflow so that it skips the base checkout or exits 0, and the required status check would pass.
  - Close this with one of:
    - `pull_request_target`, safe here because the guard only reads manifests and diffs and never executes head code;
    - CODEOWNERS plus required review on `.github/workflows/**` and `tests/**`.
- **"Default results: changed" is overloaded.**
  - Line 611 makes *any* change to `tests/harness/**`, `conftest.py` or `test_*.py` a loosening that needs
    `Default results: changed`.
  - So every harness bug fix, and any Phase 3/4 PR that adds harness code after the guard is required, must declare that
    default results changed, which contradicts §9 ("Default-results impact: none") and the CLAUDE.md meaning of that
    line.
  - A separate declaration, for example `Test criteria: loosened`, keeps the signal honest.
- **`test_inventory.py` flags itself.** Its skip/xfail scan (lines 618-619) matches its own pattern strings unless it
  excludes itself.

**P5-m4: The `ylodt` packing example in step 6 doesn't work as written (lines 252-254).**
- `bbb.convert()` packs `yl` from the **live** arrays (`ni`, `up`, `te`, …; `bbb/convert.m:42-128`), not from the `*s`
  arrays that `hdf5_restore` fills. So "load the arrays, `bbb.convert()`" packs whatever the live arrays hold.
- The PRD says the exact sequence is fixed in Phase 1, so this is only a pointer. UEDGE already has a hook for it:
  `isyloext=1` with `yloext` (`bbb/bbb.v:1311-1312`) makes `exmain` set `ylodt = yloext`
  (`bbb/odesolve.m:151-152`). Neither is `+input`-tagged, so neither collides with the sweep.

### Notes to the user on binding decisions (not PRD defects)

- **Decision 3 (converged starting points) and decision 11 (template families).** On an installed v9 build, the
  `d_mols` template is far from converged (scaled `fnrm` ≈ 2.2) and `d_c` is not converged to its `ftol` (≈ 9e-5); see
  P5-m2. The design does not need convergence for old-vs-new comparison (§7.1 rationale), but decision 3 asks for it. If
  Phase 1 confirms this, you will need to choose between reconverging these templates on the same grid (my
  recommendation, and consistent with decision 11, which only forbids coarsening) and accepting them as they are.

All 13 binding decisions are otherwise reflected without contradiction.

## Status of previous findings (round 4)

| ID | Status | Evidence |
|---|---|---|
| P4-M1 parallel Jacobian dropped | **Partially resolved** (P5-M1) | The text is fixed. §4 lines 186-190, §7.7 lines 642-654, §8 lines 758-760, §9 lines 800-801 and the Phase 1 deliverable (line 888) all keep `CheckPandf1` + `CheckJac`, and `omp_check.py` is in the tree (line 338). But the specified mechanism (converged state, normal `ftol`, pinned environment) does not reliably build a Jacobian or use more than one thread. Measured: `slab` and `ortho` stop at `iter=0`. Code: `ppp/omp_parallel.F90:296-303` clamps `Nthreads`. |
| P4-m1 stale sentences | **Resolved** | §8 line 741-742 ("the reference guard lives in its own `reference-guard.yml`"); §11 line 846 (no guard in `build-test-wheel.yml`); Phase 3 lines 923-924; §6 Facts line 299 now says "step 8". |
| P4-m2 unperturbed arrays | **Resolved** (pointer in P5-m4) | `converged_state.h5` holds the physical arrays (§4 lines 108-110, §7.1 lines 380-381). Step 6 packs `ylodt` from it, with the sequence fixed in Phase 1. |
| P4-m3 guard rule details | **Resolved** (new details in P5-m3) | Default loosening rule (line 611-613); prune-override exception (line 617); skip/xfail ban (lines 618-619); base copy of the guard script (lines 620-622); required status check with an admin action in Phase 3 (lines 623-624, 924; §11 lines 847-848). |
| P4-m4 normal form | **Resolved** | `ast`-based check, imports allowed (lines 270-277). `d_c` `:132` and `:143-144` re-verified with `git show`. `ortho` `:105-108` snippet and `:57` mid-file allocate re-verified, and §6 now keeps `:57`. Spawn fallback isolation at line 291-292. |
| P4-m5 locality calibration | **Mostly resolved** (count in P5-m1) | Range mutations "from the evaluation window" (lines 530-535); "required on `slab_phi`, `d_c`, `large_dd2c`, demonstrated where possible on 8x4" (lines 536-537); `M_cls`/`M_loc` split (lines 437-439, 528-529, 541-544, 609). Whether the second mutation joins the committed set is still unsaid, and the counts are now inconsistent. |

## What was checked and how

**Code claims (worktree at `0fac655`, `sed -n` / `grep -n`)**
- `nksol` early exit: `svr/nksol.m:1005-1015`, `nkstp0` at `:1364-1398` (`fmax ≤ 0.01·ftol`).
- `ftol` default: `bbb/bbb.v:1204`.
- `CheckJac`/`CheckPandf1` behaviour: `ppp/parallel.F90:112-150` (banner on success, `xerrab` on a difference);
  `ppp/omp_parallel.F90:984-988`.
- `Nthreads` clamp: `ppp/omp_parallel.F90:284-330`.
- `validate` §4: `.claude/skills/validate/SKILL.md:70-84`. Context: `.claude/context/openmp-jacobian.md`.
- `convert` packing: `bbb/convert.m:1-128`. `ylodt`/`yloext`: `bbb/odesolve.m:140-153`, `bbb/bbb.v:1311-1312`.
- `jac_calc` `del`/`dylconst`: `bbb/oderhs.m:1156`, `bbb/bbb.v:3302-3304`.

**`upstream/pytests` at b535508 (`git show`, `git ls-tree`)**
- `d_c` template `input.py`: `:132`, `:135`, `:143-144`. `ortho` `input.py`: `:8`, `:55-59`, `:105-108`.
- Template vs generated `solution.h5` blob IDs for D_only and slab: they differ, which confirms the generated copies
  are perturbed.

**Short runtime checks.** These were single evaluations, about seconds each; no build and no test suite. I used the
installed `~/.pyenv/versions/claude` (`uedge_ver 9.0.0-beta.0`, not necessarily `0fac655`). Template files were
extracted to the session scratchpad.
- Probe: `exec(input.py)` (template restore), `ftol=1e50`, `exmain()`, then `pandf(-1,-1,…)` with `yl[neq]=-1`. That
  gives `max|sfscal·yldot|` and the L2 norm for `d_c`, `d_only`, `d_mols`, `slab` and `ortho`.
- Iteration check: the same setup with `ftol=1e-8`, `com.iprint=1` and `exmain()`. I read `nksol`'s `iter=`/`iterm`
  lines and `bbb.nni`. The `slab` and `ortho` runs stop at `iter=0`, `d_only` takes 1 iteration and `d_c` takes 2. The
  iteration-0 `fnrm` matches the probe exactly.

**Decision fidelity.** All 13 decisions were checked against §4, §6, §7, §11, §12 and the Appendix; see the note on
decision 3 above.

**Template.** All 15 `create-prd` sections are present. Assumptions are in §15.
