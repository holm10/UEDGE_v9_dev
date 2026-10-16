# AIUE-61 plan review, round 2

Plan: `.claude/plans/AIUE-61-omp-static-partition.md` at `a979331` (round 1 reviewed `4dea642`), branch
`bugfix/v9-AIUE-61-omp-static-partition`, base `1553e75`. Stage: plan. Reviewer: uedge-reviewer. Round-1 report
`docs/reviews/AIUE-61-plan-round1.md`, response `docs/reviews/AIUE-61-plan-round1-response.md`. I reviewed against the
owner decisions as relayed (Jira AIUE-61 comment 10021): D1 approved, Q2 64 user-editable, Q3 deterministic
non-convergence acceptable, Q4 `isjacreset` unchanged (AIUE-68), Q5 minimum chunk length, Q6 to AIUE-58/59. The
merge order is AIUE-56, then AIUE-60, then AIUE-61.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 5 MINOR (all new, all optional).

## Summary

All ten round-1 findings are resolved, and I checked each fix against the code.
- **L1-B1:** fixed mode now indexes the timing array by `ichunk`. A `--checkbounds` gate (G10) and a negative control
  (NC5) are added.
- **L1-M1:** Q5 is specified as a rule that depends only on problem size. It keeps the full problem at exactly 64
  chunks of 693 columns.
- **L1-M2:** the guarantee is scoped correctly. `exmain` really does refuse `ismcnon≠0` and `isimpon∉{0,2,6,7}` for
  any OpenMP run. It does so after `allocate` has set `ParallelJac` and before any Jacobian.
- **L1-M3:** the merge order and the "any failure is a FAIL" rule close the race question.

Keeping `emcoef` in `copyin` doesn't hurt the Jacobian path, and legacy mode stays bitwise equal by construction. The
remaining points are protocol refinements: the G7 load rule is likely to leave the 8-thread cell unfilled on this
machine, G10 has little power against an unfixed `(tid+1)` write, and the Q5 effect on mid-size problems is neither
measured nor stated.

## Findings

### BLOCKER
None.

### MAJOR
None.

### MINOR

**L2-m1: The G7 load rule will often invalidate the 8-thread runs on this machine, partly because of the protocol's
own load** (plan "G7 rules").
- What's wrong:
  - **Lag.** The 1-minute load average decays over about 60 s. Runs go back to back, one process at a time, so the
    previous run's 8 threads are still counted when the next run is checked. At T=8, a run of a few seconds' Jacobian
    plus single-threaded setup, repeated every 10–20 s, adds roughly 2–4 to `load1` by itself.
  - **Background.** `uptime` at review time showed `5.52 5.59 7.51`. The threshold at T=8 is 6.
  - **Re-queueing doesn't help.** An invalidated run goes to the end of the queue, up to 3 times. The protocol's own
    load is still there when it comes round again, so the cell is likely to end as "not run (machine busy)". The plan
    handles that outcome honestly: it never passes the cell. But it may leave G7 unrunnable in practice.
  - **Unequal cores.** The host has 10 performance and 4 efficiency cores (`hw.perflevel0/1.physicalcpu` = 10/4). At
    the threshold, 8 threads plus a load of 6 spill onto the E-cores, which adds noise.
- To resolve (optional):
  - Before each run, wait for quiet: poll until `load1` ≤ threshold, with a timeout and a recorded wait time, instead
    of invalidating and re-queueing.
  - Alternatively, measure only other processes' CPU (for example `ps` %CPU excluding the protocol's own children).
  - Consider a paired statistic: the median of the NEW/OLD ratios of adjacent interleaved pairs. It cancels slow drift
    better than a ratio of two medians.

**L2-m2: G10 has little power to detect an unfixed `OMPTimeLocalJac(tid+1)` write** (G10, NC5).
- What's wrong:
  - In the 1-chunk Te box run, the only iteration is usually taken by the master thread, `tid=0`. Index 1 is in
    bounds, so that run would pass even without the fix.
  - With 2 chunks, an unfixed write goes out of bounds only if a thread with `tid≥2` takes a chunk. Each G10 case runs
    once (K=1) at 4 threads.
  - NC5 shows that the checker *can* see the array, but G10 itself would pass an unfixed implementation with
    substantial probability.
  - The implementation review will read the code, so this is not a correctness risk. It is a weak gate.
- To resolve (optional): run the 2-chunk cases (Te box with `OMPJacMinChunkLen=12`, and `full` with
  `OMPJacNchunksFixed=2`) at 8 threads with K≥5. Or make part of G10 a static check that fixed mode never indexes a
  `NchunksJac`-sized array by `tid`.

**L2-m3: The effect of Q5 on mid-size problems is neither measured nor stated** (Solution 1, G7, R4, PR list).
- What's wrong: under the rule, with T threads:
  - `neq < 600` gives 1 chunk, so the OpenMP Jacobian runs on one thread, plus one reset;
  - `neq < 300·T` can't use all T threads;
  - up to `neq ≈ 19 200`, a problem gets fewer than 8 chunks per thread at 8 threads, so the dynamic tail can cost up
    to one chunk.

  The old default (one column per chunk) had none of these limits.

  G7 measures only the full problem, which keeps 64 chunks. R4 reports the Te box and D_only. The pytests D_only
  `nonog/default` grid is 8×4 (from its `gridue` header), so its `neq` is a few hundred and it runs as 1 chunk by
  default. It shows the serial-like extreme, not the mid-size tail.
- This follows from the owner's Q5 decision and isn't a defect in itself. The PR should still show the owner what it
  costs.
- To resolve (optional):
  - Add to R4 a mid-size emulation: `full` with `OMPJacNchunksFixed` 8 and 16 at 8 threads, against the old default.
  - Add one sentence to the PR's default-change paragraph: small problems no longer parallelise the Jacobian, or do so
    only partly.

**L2-m4: G10b doesn't say what a crash would mean, or how the variable is removed** (G10b).
- What's wrong:
  - The per-worker automatic and `firstprivate` arrays that need stack (`ylcopy`, `iJacRowCopy`, `TimeJacRowcopy`, and
    `wk` and `yl_check` in `LocalJacBuilder`, each of size `neq`) already exist on the AIUE-56 base.
  - The product README already tells users to set `OMP_STACKSIZE` (`README.md:103`, `export OMP_STACKSIZE=2G`).
  - So a G10b crash may be pre-existing. As written, it would be an AIUE-61 FAIL.
  - "With the variable left out" could also inherit `OMP_STACKSIZE` from the launching shell.
- To resolve (optional):
  - Remove the variable explicitly (`env -u OMP_STACKSIZE` or the equivalent in the launcher).
  - Pre-register a same-settings control on `AIUE-56-omp`. If both crash, record it as pre-existing and state that
    `OMP_STACKSIZE` is required. Only an AIUE-61-only crash is a FAIL.

**L2-m5: Small slips in the revised text.**
- Task 2 wraps "`jac_calc_omp` (`:545-563`)" in the fixed/legacy branch. Line 545 is
  `OMPTotTimeJacCalc = tick()`, which must stay outside the branch. The weights block is `:547-562`.
- The `.v` text says "(not ismcnon, not isimpon=5)". The roadblock refuses every `isimpon` other than 0, 2, 6 and 7
  (`bbb/odesetup.m:6727-6736`), so write "isimpon 0, 2, 6, 7 only".
- G0b: "on the combined tree: Part A gone". If AIUE-60 takes Part B in (its plan recommends it), Part B is gone too.
  Word the expected set as "whatever AIUE-60 leaves non-threadprivate".
- Solution 7 and the response say that `allocate` runs "unconditionally". At `bbb/odesetup.m:6646-6650` it runs under
  `ismpion.eq.0`, the default. The conclusion holds for the OpenMP build.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| **L1-B1** `OMPTimeLocalJac(tid+1)` out of bounds | **Resolved** | Solution 3 and task 3 write and print at `OMPTimeLocalJac(ichunk)` in fixed mode. Legacy keeps `(tid+1)` (`ppp/omp_parallel.F90:740,744`), so NC4 stays bitwise; its pre-existing overflow is recorded as F-61-2. Confirmed: the array is `OMPTimeLocalJac(1:NchunksJac)` (`ppp/ppp.v:70`), the team is unbounded (`:296`, no `num_threads`), and in fixed mode it is read only by the verbose print (`:568-572`), because the weights block moves into the legacy branch. `--checkbounds` adds `-fcheck=all` to all Fortran, including `ppp/*.F90` (`setup.py:742-746`). The gate's power: L2-m2. |
| **L1-M1** Q5 missing | **Resolved** | The rule `min(OMPJacNchunksFixed, max(1, neq/OMPJacMinChunkLen))`, the `.v` text, the `InitOMPJac` branch, the docs (task 5), G3-count and the Te-box runs with min 1 are all present. Arithmetic: 44352/300 = 147 gives 64; 44352/64 = 693 exactly, so P2, P5 and R2 stay valid; Te box 25/300 = 0 gives 1; min 12 gives 2. Q1–Q6 are recorded as decided. |
| **L1-M2** Guarantee too broad | **Resolved** | I verified the roadblocks. `exmain` calls `allocate` (`bbb/odesetup.m:6649`), which runs `InitParallel` (`:369`) and sets `ParallelJac=1` (`ppp/parallel.F90:20-22`). Then, inside the same `igrid` iteration and before `imeth`/the solver, it calls `xerrab` for `isimpon>0` not in {2,6,7} and for `ismcnon>0` when `ParallelJac>0` or `ParallelPandf1>0` (`:6727-6745`). `ismcnon` is `/0/` (`bbb/bbb.v:2337`), and the `ismcnon=4` compounding is at `bbb/pandf_plasma_continuity.m:124-133`, as the plan says. The plan's reliance on the roadblocks is correct. The `.v` and doc texts name the scope, C-guard tests it, and G0a re-runs P3 in Jacobian mode over all packages. |
| **L1-M3** Races and gate outcome | **Resolved** | "Any determinism or identity failure is a FAIL, whatever its cause" is in "Guarantee and its scope" and in the definition of "Deterministic". The merge order is AIUE-56 → AIUE-60 → AIUE-61, with the final gates on the combined tree; the rebase command's `--onto` form is correct. The shared writes are listed from AIUE-60's Probe S (`d2fac6e`, Parts A–C, which match the plan's list), and G0b checks them dynamically. `ParallelPandfCall` is shared, set to 1 only inside `OMPPandf1Rhs` and reset to 0 on exit (`ppp/omp_parallel.F90:950,999`), so the reset runs full ranges. |
| L1-m1 P3 slips | Resolved | P3 now says which scratch scalars come from `jacobian_store_*` and which six come from the energy loops; F-61-1 is recorded; the regions and packages are stated as actually run. |
| L1-m2 G7 power | Resolved (feasibility: L2-m1) | ≥ 9 repeats at 8 threads, a load rule, and no "within noise" exemption. |
| L1-m3 Schedule independence | Resolved | G3-sched (`OMPLoopJacNchunk` 3 vs 1). |
| L1-m4 `CheckJac` | Resolved | `CheckJac` is report-only (its absolute `1e-14` positional check is at `ppp/parallel.F90:120`); G9b is the binding check. |
| L1-m5 Wording | Resolved (one slip: L2-m5) | "OMP_NUM_THREADS" and "next exmain" are in the `.v` texts; the timers are in the PR list. |
| L1-m6 Default stack | Resolved (pre-registration: L2-m4) | G10b added. |

## Assessments requested by the coordinator

- **The Q5 rule and the default of 300 are sensible.**
  - The full problem keeps 64 chunks: any minimum up to 693 would.
  - By P4's numbers (0.77 ms per column, 23 ms per reset), a 300-column chunk keeps the reset at about 10 % of the
    chunk's work.
  - The cost ratio scales with the number of grid cells, not with `neq`. The plan says so. On a much larger grid with
    few equations per cell and `neq` < 19 200, the reset share is higher than 10 %. That is accepted under Q5.
  - The real cost of the rule is lost parallelism on small and mid-size problems (L2-m3).
- **G10 and NC5 are a sound design.** NC5 calibrates the checker, and "void if NC5 doesn't trip" is the right rule.
  The power is low with K=1 (L2-m2).
- **G0a and G0b address what round 1 asked.**
  - G0a: Jacobian mode, all packages, all regions.
  - G0b: a dynamic scan of shared writes over one full Jacobian-mode evaluation, checked against Probe S, with a stop
    rule.
  - Neither sees `save`d locals or F90 module state. The plan says so, and the exmain roadblocks exclude the one known
    case (`fmombal`).
- **G7 is sound in its statistics, but the load rule is marginal here** (L2-m1). With background load around 5.5 and
  the protocol's own lagging load, the 8-thread cell will often fail the rule. The plan's fallback, "not run, never
  passed", keeps it honest.
- **`emcoef` in `copyin` doesn't hurt the Jacobian path.**
  - `OMPJacBuilder` runs the scalar copies and then the array copies after any `ueinit` (`:683-699`). `copyin` then
    points each worker's `emcoef` at the master's filled table.
  - `emcoef` is only read inside `pandf`, through `emissbs` → `B3VAL` (`api/apip93.m:212-218`). The B-spline work
    arrays `work2` and `iworki` are `+threadprivate` (`api/api.v:156-159`).
  - The reset adds only full-grid reads of `emcoef`. The AIUE-58 R3 defect, workers holding unfilled tables after
    `gallot`, affects the RHS arm before the next Jacobian copy, not the Jacobian (RCA lines 181-188 on
    `feature/v9-AIUE-58-omp-rhs-rca`). Keeping the directive's tested `copyin` list is reasonable. AIUE-59's later
    one-token removal will need a merge note.
- **Legacy mode stays bitwise equal.**
  - The only change on the legacy path is the heap fix: direct writes into the contiguous column `iJacCol(:,ichunk)`,
    with `OMPCollectJacobian` reading only `1:nnz-1`. The chunk-count branches, the weights, `OMPSplitIndex` and the
    `(tid+1)` timing are unchanged.
  - NC4 at one thread is a valid bitwise check: the multi-thread legacy result isn't deterministic, so it can't be
    compared bitwise.
  - G1 (42 cases, both builds, `OMPParallelJac=0`) covers the defaults.
  - Per-chunk storage can't overflow more easily than before. A chunk of L columns gets `L·nnzmx/neq·omplenpfac` slots,
    which is never less than the sum of L single-column budgets under legacy's one column per chunk.

## Not independently verified (environment)

- I made no builds and no UEDGE runs (the budget was read-only). P2–P5 are accepted as recorded; phase 2 reproduces
  them.
- Jira AIUE-61 comment 10021 (the owner's decisions and the merge order): I have no Atlassian access. They reached me
  from the coordinator.
- The default `OMP_STACKSIZE` behaviour on macOS libgomp and the likelihood of a G10b crash: reasoned only.
- The self-load estimate in L2-m1 is approximate (`load1` dynamics), not measured.

## What was checked and how

- `git diff --stat 4dea642..a979331`: the plan and two `docs/reviews` files only. No process files are on the ticket
  branch.
- I read the plan (446 lines), the round-1 report and the response in full.
- Spot-checked line references with `sed -n`:
  - `ppp/omp_parallel.F90`: 296, 312, 320, 509-510, 545, 563, 646-647, 672, 675, 706-707, 720, 729-735, 740, 744,
    766-771, 920-1000;
  - `ppp/parallel.F90`: 4-43, 120, 159-345;
  - `ppp/ppp.v`: 1-80;
  - `bbb/odesetup.m`: 6630-6790 (the roadblocks, their order after `allocate`, `ismpion` guard);
  - `bbb/pandf.m`: 180-245, 400-440, 560-580, 690-745 (the full-call path: `jacobian_store`/`reset` only for `xc≥0`,
    `TimingPandfOn`, `add_timestep` only for `yl(neq+1)<0`);
  - `bbb/pandf_plasma_continuity.m`: 100-140; `bbb/bbb.v:2337,3305,4129-4135`.
- `emcoef`: `git grep` (declared at `api/api.v:170`, written only in `splinem1`, read in `emissbs`) and the
  `Imslwrk` attributes (`api/api.v:143-172`). AIUE-58 RCA (`uedge-wt/AIUE-58`, `git grep emcoef -- docs`), rows R3
  and F15, and lines 181-188.
- AIUE-60 plan `d2fac6e`: Parts A–C, A6, and the merge note (`git show d2fac6e:.claude/plans/AIUE-60-omp-races.md`).
- `setup.py:66-96,726-770` (the `--checkbounds` flags reach the `ppp` F90 sources through `FARGS`).
- Machine: `sysctl` (14 CPUs: 10 performance, 4 efficiency) and `uptime` (load 5.52/5.59/7.51 during the review).
- The pytests D_only `nonog/default` `gridue` header (8×4) and `input.py` switches, to estimate its `neq` and chunk
  count.
