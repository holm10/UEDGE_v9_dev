# AIUE-56 plan review, round 1

Plan: `.claude/plans/AIUE-56-omp-jacobian-fix.md` (branch `bugfix/v9-AIUE-56-omp-jacobian-fix`, base `origin/v9-develop` = `3865c79`; docs-only on top of `0fac655`, where `base-omp`/`base-serial` were built).
Reviewer: uedge-reviewer (plan stage, finding prefix L). Read-only; no builds.

## Verdict

**REVISE**: 0 BLOCKER, 3 MAJOR, 7 MINOR.

## Summary

The fix is correct and it is the smallest one that works. I checked it against the generated code. `OmpCopyPointer<var>` sizes the copied section with the worker's own threadprivate bounds. Only the 12 `api` `Imslwrk` arrays have threadprivate bound scalars. Every `bbb` copy is bounded by `com` `Dim` scalars, which are not threadprivate, and `com` has no threadprivate variables at all. `OmpCopyScalar<pkg>` never touches an array. So copying the scalars first is safe for every package, and `OMPJacBuilder` is the only call site. The argument that defaults are unchanged also holds: `OMPJacBuilder` sits inside `#ifdef _OPENMP` (`ppp/omp_parallel.F90:440-751`) and is reached only through `ParallelJac.eq.1` (`bbb/oderhs.m:4696`).

The weak part is verification and acceptance. The plan runs ahead of AIUE-54/55 and uses tools from unmerged branches without saying so. Its measurement protocol does not match the ticket's acceptance: the repeat counts, Newton iterations, Linux and `pytests` are all missing or wrong. And it labels any residual as "M2" before measuring it, which would bias the owner's Phase 2 decision.

## Findings

### MAJOR

**L1-M1. The dependencies the plan relies on don't exist yet, and the plan doesn't say so.**
*Location:* Summary, Testing 1–4, Acceptance, Notes.

- **Ticket and spec.** The ticket says "implement the fix for the first root cause named in AIUE-55". The epic spec makes T10 (AIUE-56) depend on T9 (AIUE-55) and T5 (AIUE-53) (`AIUE-8-planning/docs/specs/...:38,218-236`).
- **Status of the inputs.**
  - The only RCA content is AIUE-50's §Shared-state scan, which is still marked "Status: in progress (… characterisation AIUE-54 and RCA AIUE-55 to follow)" (`AIUE-50/docs/rca/...:3`). C1 is a *candidate* there.
  - No AIUE-54 or AIUE-55 branch exists (`git branch -a`).
  - AIUE-52 and AIUE-53 are unmerged and have uncommitted changes in review (`git status` in both worktrees).
  - `tests/` does not exist on the AIUE-56 branch.
- **Plan statements that don't hold yet.**
  - "Sibling tickets from AIUE-55" (Notes) have not been filed.
  - The "pre-fix K=20 rates (AIUE-54)" (Testing 4) have not been measured.
  - "decision 9, AIUE-55" has not been taken.
  - The `check`, `flow` and serial-check commands are not reproducible from this branch.
- **Why it matters.** AIUE-50's E3 is already the minimal experiment that T9's acceptance asks for, so implementing early may well be a reasonable owner call. But it is a deviation from the agreed dependency order, and it changes what this ticket must carry. If C1 is the only cause, AIUE-56 carries the full set. If AIUE-55 files siblings (e.g. `areapl`, F16), it doesn't.
- **Resolve by:**
  - stating the deviation, and the owner's agreement to it, in the plan;
  - pinning the tool sources (worktree + commit of AIUE-52/53/47 used for each run, including AIUE-53's revision);
  - running the pre-fix baseline yourself with the identical commands on `base-omp`, instead of citing AIUE-54;
  - stating the merge order: the PR waits for AIUE-53 (and AIUE-52) to merge, or the serial-check output in the PR names the tool commit.

**L1-M2. The measurement protocol doesn't match the acceptance criteria it reports on.**
*Location:* Testing 3–4, Acceptance.

| Acceptance item | Plan | Gap |
|---|---|---|
| 0/5 at 2 and 8 threads; 0/5 for each other configuration at 4 threads | `flow --all --repeats 2` | 2 repeats, not 5 |
| PRD §11: Jacobian, `sfscal` and `fnrm` sequence over ≥ 3 Newton iterations | No `--itermx` anywhere | The harness default is one evaluation (`AIUE-52/.../harness/cli.py:118,138`) |
| "on Linux and macOS (or the fallback gate …)" | Linux not mentioned | — |
| "OpenMP-build `pytests` suites still pass" | Absent from Testing and Acceptance | — |

Pre-fix, C1 corrupted only the first Jacobian of a process (RCA E2). So the one-evaluation runs are the right C1 detector. The ≥ 3-iteration runs are what the acceptance and the M2 history question need.

*Resolve by:*
- running the acceptance counts as written (K=30 Te box and full at 4 threads; K=5 at 2/8 threads; K=5 for every other configuration at 4 threads);
- adding `--itermx 3` (or the PRD number) runs next to the one-evaluation runs;
- adding the OpenMP-build `pytests` suites;
- naming the Linux run, or stating explicitly that it is not run and that this is open for the owner;
- for each acceptance line in the PR, listing "met / not met / not run".

**L1-M3. The residual is labelled before it is measured, and the expected-status section conflates two things.**
*Location:* Testing 2–4, Acceptance.

- **Presumed labels.** Testing 3 expects agreement "except M2 round-off", and Testing 4 says "Report the M2 residual". M2 is only characterised on a handful of runs (RCA §M2). Another known candidate is live on the full problem: the `areapl` race (F16), a real race on physics state in the plate BCs. A residual on the 30-run full-problem sample could come from either, or from something new. Calling it M2 up front steers the owner's Phase 2 decision, which the binding constraints forbid this ticket to pre-empt.
- **Who carries the full set.** "Not expected to be met in full because of M2" treats the full Jacobian-track set as this ticket's acceptance. The ticket says the *last fix ticket to merge* carries it. Whether that is AIUE-56 depends on AIUE-55 (L1-M1).
- **Resolve by:**
  - reporting the residual neutrally, per run: number of differing entries; equation, ix and iy of each row; whether the cell is plate-adjacent; magnitude against ulp(yldot)/`del` scale; sparsity changes; OpenMP-vs-OpenMP determinism separately from OpenMP-vs-serial;
  - saying which signature (M2, F16, other) each class matches, and on what evidence;
  - stating this ticket's own acceptance (C1 removed, no regression, serial check, `pytests`, timing, code facts) separately from "full set if last to merge".

### MINOR

**L1-m1. The mechanism description omits `copyin(emcoef)`.**
- The column loop has `copyin(yinc,xlinc,xrinc,emcoef)` (`ppp/omp_parallel.F90:715`). For a POINTER, copyin copies the association, so inside the loop the workers' `emcoef` points at the master's array. The zero tables on the first Jacobian were the knots and data (`xdata_api`, `x/y/zknots`, …), not `emcoef`. The RCA's F1 row says this; the plan says "keep zeros elsewhere" for all of them.
- Consequence after the first Jacobian: the workers' `emcoef` stays aliased to the master's buffer (threadprivate persists). Every later `OmpCopyPointeremcoef` then has N-1 workers writing identical values into the master's array at the same time. That is a formal data race, benign in practice, existing since before this change, and not changed by the swap.
- *Resolve by:* stating this in the plan and in the `openmp-jacobian.md` copy rule, and keeping "no other change" (don't drop the `copyin` in this ticket).

**L1-m2. The "C1 removed" criterion is indirect and partly brittle.**
- Testing 2 uses "no 1e43 entries, sparsity equal to serial, `fnrm` equal". "Sparsity equal" can fail because of M2: the full-problem E3 run 2 had 416 + 3 pattern changes after the swap. "No 1e43" has no threshold.
- AIUE-50 already has a deterministic check of the mechanism itself. `scan_ompcopy.py` flags copy-order hazards statically (12 now, all `Imslwrk`) and should report 0 on the AIUE-56 OpenMP build. The TPCHK `after-copy` checker (scratch build) should report 0 mismatching pairs.
- *Resolve by:*
  - using the static scan (0 hazards) as the primary "C1 removed" evidence;
  - adding a negative control: the same `check` command on `base-omp`, which must fail;
  - turning the symptom criterion into a threshold, e.g. max|jac| equal to serial to a stated relative tolerance.

**L1-m3. Citation and description errors.**
- `api/apip93.m:102-108` is in `splinem` (starts at `:91`, called from `bbb/odesetup.m:1130,1150`), not in `readpost`. The RCA has the same slip.
- `ldf_api` and `mdf` have no DATA default (`api/api.v:152-153`), so not all the bounds are `/1/`.
- *Resolve by:* fixing the plan, and the comment text if it repeats this.

**L1-m4. The debug switches after the swap.**
- With `OMPCopyArray=1, OMPCopyScalar=0`, the array copy still uses the workers' stale bounds, so the C1 hazard remains in that debug setting.
- *Resolve by:* noting this in the call-site comment, or in `openmp-jacobian.md`, next to "keep both switches working independently".

**L1-m5. Timing method not specified.**
- Testing 5 names no metric or sample size.
- *Resolve by:* naming the metric (e.g. `OMPTotTimeCopy + OMPTotTimeLocal`, or wall time of `jac_calc_omp`), the number of runs, and that before/after run on the same machine and load.
- Note that the "~1e5 extra elements" applies only to the first Jacobian of a process. Later Jacobians already copied the full sections.

**L1-m6. The jacrhs-arm statement is imprecise.**
- `OMPPandf1Rhs` (`ppp/omp_parallel.F90:902-997`) never calls `OmpCopy*`. Its workers run on whatever `OMPJacBuilder` last copied, and with `ijactot=0` it falls back to the serial `pandf`. So the fix makes the RHS workers' `Imslwrk` state correct from the first Jacobian on. Any staleness between Jacobians remains, and that is AIUE-58's business.
- *Resolve by:* stating this precisely, and recording the jacrhs arm at the same K/threads as the jac arm, so AIUE-58 starts from data.

**L1-m7. Line-reference drift.**
- The added comment lines shift every `ppp/omp_parallel.F90` line after `OMPJacBuilder`. In `openmp-jacobian.md` that hits `:715`, `:902` and `:953-955`; `--fix` covers these.
- The RCA on AIUE-50 (`:681-686`, `:688-693`, `:715`) and the PRD cite the same lines, but are outside the hook's `DOC_GLOBS`.
- *Resolve by:* noting the drift in the PR, so whichever of AIUE-50/56 merges second updates the RCA references.

## Status of previous findings

Round 1: none.

## What was checked and how

- **Call site.** I read `OMPJacBuilder` and `jac_calc_omp` (`ppp/omp_parallel.F90:495-751`). `grep -rni OmpCopy` over the repo (excluding `build/`) finds calls only at `ppp/omp_parallel.F90:683-692`. Line 905 is a `USE` only, and `get_packages.py` is a dev script outside the build. `OmpInitZero*` has no caller.
- **Generated code** (`base-omp/build/temp.*/api_p.F90`, `bbb_p.F90`, `com_p.F90`):
  - `OmpCopyPointerxdata_api` (`api_p.F90:218-232`): the guard and the `firstprivate` buffer use the master's `nxdata_api`; the worker assignment uses its own.
  - `apisetarraypointerxdata_api` (`:898-930`): `pcopy__` is allocated with the master's bounds and `copyin`'d, and the workers point at it.
  - `OmpCopyScalarapi` (`:441-475`).
  - The same pattern for `bbb` `te` (`bbb_p.F90:4566-4580`, `20662-20698`).
- **Bound scan** (scratchpad `bounds.py`): over all `OmpCopyPointer<var>` routines and `ListThreadPrivateVariables_<pkg>.txt`.
  - `bbb`: 434 routines, 0 with threadprivate bound scalars.
  - `api`: 12 of 14 have them, exactly the `Imslwrk` set.
  - `com`, `aph`, `flx`, `grd`, `ncl`, `ppp`, `svr`, `wdf`: 0 threadprivate variables.
  - No threadprivate variable is uncovered by a copy routine.
  - `OmpCopyScalarbbb` (89 copies) references no array.
- **Default safety.** `#ifdef _OPENMP` spans `ppp/omp_parallel.F90:440-751`. The dispatch is `c!omp if (ParallelJac.eq.1)` (`bbb/oderhs.m:4696`), and `InitParallel` sets it (`ppp/parallel.F90:4-43`). The defaults `OMPParallelJac=OMPParallelPandf1=0` are at `ppp/ppp.v:6-7`, and `OMPCopyArray`/`OMPCopyScalar` are at `:35,38`.
- **Physics path.**
  - `emissbs` (`api/apip93.m:189-221`) is used at `bbb/pandf_plasma_energy.m:775,822`.
  - The `Imslwrk` declarations are at `api/api.v:143-172`.
  - The `splinem` call sites are at `bbb/odesetup.m:1129-1130,1149-1150`.
- **Thread-team persistence.** `InitOMPJac` (`ppp/omp_parallel.F90:281-333`) keeps `OMP_GET_MAX_THREADS()`, so the team size is constant across the allocation and Jacobian regions.
- **RCA** (`AIUE-50/docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`): summary, F1/F2/F15/F16, E1–E4, M2, TSan, not-covered.
- **Requirements.** PRD §4, §7.3-7.6, §9, §11 (`docs/prds/AIUE-8-…md`); epic spec T4–T10 (`AIUE-8-planning/docs/specs/…md:110-236`).
- **Tools.**
  - Harness CLI: `AIUE-52/tests/deterministic_omp/harness/cli.py:112-144`, `flow.py:71-88`.
  - Serial check: `AIUE-53/.../serial_check.py:65-107,598-610`.
  - Context-ref checker scope: `.claude/hooks/check_context_refs.py:44`.
  - `build_uedge.sh`.
  - Base worktrees at `0fac655`; `0fac655..origin/v9-develop` is docs only.
- **Not done.** No builds or runs, by design.
