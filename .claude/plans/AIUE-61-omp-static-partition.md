# Feature: AIUE-61 — Reproducible OpenMP Jacobian: fixed chunk partition (decision 9, option F)

Validate the patterns and file references below before implementing. Line numbers are those of this branch's base
(`bugfix/v9-AIUE-56-omp-jacobian-fix` at `1553e75`). Revision 3: approved in plan review round 2 (`docs/reviews/AIUE-61-plan-round2.md`), with its optional minors folded
in (response `docs/reviews/AIUE-61-plan-round2-response.md`). Round 1: `docs/reviews/AIUE-61-plan-round1.md` and its response.

## Summary
**Type**: Numerics/Parallel (OpenMP-only code path), plus the `OMPJacNchunks≠0` stack-crash fix
**Complexity**: Low (code, ~60 lines in `ppp/`), High (validation)
**Default results**:
- **Serial build and OpenMP build with `OMPParallelJac=0`: unchanged.** The changed routines run only with
  `ppp.OMPParallelJac=1` in the OpenMP build. The new `.v` variables are inert elsewhere.
- **OpenMP Jacobian (`OMPParallelJac=1`): changed on purpose. This is the owner's decision 9 (2026-10-15), an explicit,
  owner-approved exception to the PRD/`CLAUDE.md` rule against changing defaults** (Jira AIUE-61 comment 10021). The
  default OpenMP Jacobian becomes bitwise reproducible and independent of the number of OpenMP threads, within the
  scope stated under "Guarantee and its scope". On macOS arm64 it still differs from serial at round-off (C2: about
  12 000 entries in 78 rows of the full problem, worst 4.6e-9 × row max, probe P2). On Linux x86-64 it is expected to
  equal serial bitwise (to be checked, R5). The old behaviour stays available through `ppp.OMPJacFixedChunks=0`.
- **A trade-off the PR states:** on macOS at 4 threads or fewer, the old default often equals serial bitwise (9 of 10
  study runs at 4 threads, and P2's `full_D_t4`), but it varies from run to run. The new default always differs from
  serial in the C2 rows, and never varies.
- The PR states all of this in its first paragraph, together with decision 9 and D1.

**Packages / files**: `ppp/ppp.v`, `ppp/omp_parallel.F90` (`InitOMPJac`, `jac_calc_omp`, `OMPJacBuilder`, new
`OMPFixedSplitIndex`), `ppp/parallel.F90` (`LocalJacBuilder`), `.claude/context/openmp-jacobian.md` (code facts),
`docs/reviews/AIUE-61-*` (validation scripts and record).

**Branch / worktree**: `bugfix/v9-AIUE-61-omp-static-partition` @ `/Users/holma/Documents/uedge/src/uedge-wt/AIUE-61`.
- **Merge order (owner, via the coordinator): AIUE-56, then AIUE-60, then AIUE-61.**
- Implementation and development checks run on the current base, `bugfix/v9-AIUE-56-omp-jacobian-fix` `1553e75`.
- Once AIUE-60's implementation is approved, rebase: `git rebase --onto bugfix/v9-AIUE-60-omp-races bugfix/v9-AIUE-56-omp-jacobian-fix`.
  AIUE-60's plan is `d2fac6e`, revised to `203a5ff`, with amendment 1 at `cb05472` (in review; the combined-tree run
  uses AIUE-60's **approved final tip**, whatever it contains). Under amendment 1, AIUE-60 makes `areapl` and
  `TimingPandfOn` threadprivate, keeps the `com` timers shared but accumulates them atomically (`acctim`), writes
  `nfsp` only when it changes, and replaces `iflag_aph` with locals; it adds no `+threadprivate` to `com`/`aph`
  scalars. AIUE-61 doesn't depend on the timers being threadprivate: they are output only (read in prints and the
  debug dump, never by the RHS or the Jacobian).
- **The final gates G0–G10 run on the combined tree.**
- Expected conflicts, as AIUE-60's plan foresees:
  - `ppp/parallel.F90`: AIUE-60's `sfscal(ii)` clip is at `:288,292` and doesn't overlap AIUE-61's edits;
  - `openmp-jacobian.md` and `.claude/context/refs.lock.json`: keep both texts, re-lock after re-reading.
- If AIUE-60 is not approved when AIUE-61's validation is otherwise done, the PR says that the reproducibility claim is
  **unproven until it is validated together with AIUE-60**, and the AIUE-56-based results are labelled preliminary.
- Venvs: `venvs/AIUE-61-omp` (this tree), `venvs/AIUE-61-serial` (second tree `uedge-wt/AIUE-61-serial`, detached at
  the same commit, as AIUE-56 did), `venvs/AIUE-61-chk` (this tree, OpenMP, `--checkbounds`, for G10).

## Owner decisions (Jira AIUE-61 comment 10021, 2026-10-15; relayed by the coordinator)

| # | Decision | Where in this plan |
|---|---|---|
| Decision 9 | Option F: fixed contiguous chunks, a count independent of the thread count, boundaries fixed between Jacobians, heap fix, new OpenMP default, the old behaviour behind a documented OpenMP-only switch, serial unchanged | Solution 1–5 |
| D1 / Q1 | **Approved:** fixed boundaries, a fresh full `pandf` at every chunk start, and the **dynamic** schedule instead of decision 9's literal `schedule(static,1)`. Reason: P1, P2, P2-neg | Solution 2, 4 |
| Q2 | Default **64 chunks**, as a user-editable `ppp` variable (`OMPJacNchunksFixed`) | task 1 |
| Q3 | A hard `dtreal=1e-9` step that doesn't converge is acceptable **as long as it is deterministic** (R2 then gates determinism, not convergence) | R2 |
| Q4 | `isjacreset` unchanged; removing it is AIUE-68 (epic AIUE-63) | Deliberate choices |
| Q5 | **Add a minimum chunk length, by a rule that depends only on problem size** | Solution 1, task 1–2, G3 |
| Q6 | A post-Jacobian worker reset for the RHS arm is **out of scope**: AIUE-58/AIUE-59 (AIUE-59 waits for AIUE-60 and AIUE-61) | Deliberate choices, R3 |

## Pre-plan probes (scratch, macOS arm64, gfortran 15; not reviewed; reproduced in phase 2)

Scratch: `/Users/holma/Documents/uedge/src/uedge-wt/scratch-AIUE-61/` (scripts and records). Prototype: the tree
`uedge-wt/AIUE-61-probe` (detached at `1553e75` plus the revision-1 design, which has no minimum chunk length and the
`OMPTimeLocalJac` defect of L1-B1) and `venvs/AIUE-61-probe` (OpenMP). Case: the AIUE-57 harness case (`full`: neq
44352, numvar 14; `tebox`: neq 25).

| # | Question | Result |
|---|---|---|
| P1 | Does static round-robin without a reset give a thread-independent Jacobian? (cost-study records, `OMPJacSchedule=2`, `OMPAutoBalance=0`, uniform boundaries) | **No.** 8 chunks: the same hash at 2/4/8 threads; 16 chunks: the same at 2/4/8; 32 chunks: the same at 4/8. **64 chunks: 4 threads give `217b791b…`, 8 threads give `8761cd9e…`** (5 runs each, each deterministic). Under `static,1` a worker starts chunk k from the end state of chunk k−T. This fits a column-history reach of about 2–4 thousand columns (an inference; the conclusion doesn't depend on it). Re-derived independently by the round-1 reviewer. |
| P2 | Fixed partition, 64 chunks, reset (a full `pandf` at every chunk start), `schedule(dynamic,1)` | **Full problem: one hash, `8761cd9e36658ee1`, at 2, 3 and 4 threads and in two runs at 4 threads**, nnz 3 180 971. It is the same as the study's 64-chunk static run at 8 threads, where no chunk started near another chunk's history. Against serial (`0ee4446a…`, nnz 3 190 290): 12 275 mismatching entries in 78 rows, worst 4.59e-9 × the serial row max (the AIUE-56 C1-gate bound is 1e-6). Te box (25 one-column chunks): the same hash at 2 and 4 threads, 2 entries in 1 row against serial, 5.62e-10. Cost at 4 threads: `ttjstor` 9.99 and 10.06 s, against 9.68 s for the old default in the same batch (single samples). At 2 threads: 19.31 s (the study's old default: 18.4 s). |
| P2-neg | The same partition **without** the reset (`OMPJacChunkReset=0`) | Full problem: 2 threads `48d3f455…`, 4 threads `6ece2e5a…` (nnz 3 184 409 vs 3 181 726). The reset is what removes the thread dependence. |
| P3 | Does a full `pandf(-1,-1)` erase the column-loop history? Serial build `AIUE-56-serial`, one deck (`full`). A Jacobian-like column loop of 3000 columns (perturbed and restoring local `pandf`, plus the `isjacreset` call), then a full `pandf`, with snapshots before and after. Regions 1–3000, 20001–23000 and 41001–44352 snapshot `bbb`, `com` and `api` (`reset1`). Region 12001–15000 snapshots `bbb, com, api, aph, wdf, svr, flx, grd, ppp` (`reset2`). **`yl(neq+1)` was left at its post-`exmain` value, not set to Jacobian mode.** | **Yes, within that scope.** The column loop changes about 150 variables (`vsoree`-type carriers, the `Selec` ranges, `areapl`, `api.work2/iworki`, …). After the full `pandf`, every variable equals the fresh state except timers/counters and the `Jacobian_restore` scratch. `yldot` is bitwise equal. How the scratch is used (corrected after review L1-m1): `jacobian_store_*` writes `*o`, `*om` and most `*old` at the start of each local `pandf` (`bbb/pandf_jacobian.m:6-67`). Six scalars are written instead inside the energy loops: `erlizold`, `erlrcold`, `eeliold`, `pwrebkgold`, `pwribkgold`, and `pradold` when `isimpon≥2` (`bbb/pandf_plasma_energy.m:574-575,597,771,909,927`). They come from the box's last cell, and `jacobian_reset` (`bbb/pandf_jacobian.m:87-93`) then writes them into `(xc,yc)`, which restores the wrong cell. That is a pre-existing history carrier inside the column loop; the full reset rewrites it. The probe doesn't see `save`d locals or F90 module state. Phase 2 re-runs P3 in Jacobian mode over all packages and regions (G0a). |
| P4 | Cost of the reset | A full `pandf` takes 23.1 ms and a local one 0.30 ms. The serial Jacobian takes 34.2 s (0.77 ms per column, full problem, 1 thread). 64 resets are about 1.5 s of CPU, about 4–5 % of the Jacobian work, spread over the threads. Te box with 25 one-column chunks: the reset dominates (`ttjstor` 0.22–0.35 s against 0.06 s without it), because the grid is full-size while neq is 25. Hence Q5. |
| P5 | `dtreal=1e-9` scenario: the deck, `full`, 5 × `exmain`, stopping at the first failed step; prototype at 4 threads | **64 chunks: step 1 fails, with `iterm=4` after 30 iterations and final `get_fnrm` `0x1.aa0e230edbab4p-2`.** These are the same bits as the study's 64-chunk static run at 8 threads (failed 3 of 3). 128 chunks: also fails (`0x1.a9ef9d857899cp-2`). For comparison, serial converges (21, 4, 3, 4, 3 iterations), serial with `-ffp-contract=off` fails, and the old default converged in 3 of 5 runs at 4 threads. Accepted by the owner if deterministic (Q3). |

## Problem and solution

**Problem** (RCA `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` §Jacobian RCA, on `feature/v9-AIUE-62-linux-characterisation`).
- After the C1 fix (AIUE-56), the OpenMP Jacobian still differs from serial at round-off and **varies from run to
  run** (C2/M2).
- The serial Jacobian depends on the history inside its column loop. OpenMP workers have a different history, and
  with the default dynamic one-column chunks that history depends on timing.
- Separately, any `OMPJacNchunks≠0` crashes the full problem. The `firstprivate` automatic arrays
  `iJacColCopy`/`rJacElemCopy` (`ppp/omp_parallel.F90:672,675,720`) sit on the master's 8 MB stack.

**Solution (default `OMPJacFixedChunks=1`):**
1. **Fixed partition, with a problem-size-only chunk count:**
   `NchunksJac = min(OMPJacNchunksFixed, max(1, neq / OMPJacMinChunkLen))`, with integer division. The defaults are
   64 and 300.
   - The count depends on `neq` and the inputs only, never on the thread count.
   - Full problem: 44352/300 = 147, so it gets 64 chunks, which keeps P2, P5 and R2's pre-registered bits valid. Any
     `OMPJacMinChunkLen` ≤ 693 would do that.
   - Te box: 25/300 = 0, so it gets 1 chunk.
   - Why 300: at 0.77 ms per column against 23 ms per reset (P4), a 300-column chunk keeps the reset at about 10 % or
     less, and longer chunks less.
   - The reset cost scales with the grid, not with `neq`, so problems with few equations on a large grid get
     relatively more. The owner asked for a rule based on problem size only, and this rule satisfies that.
   - Chunk i covers columns `(i−1)·neq/N + 1 … i·neq/N` (`OMPFixedSplitIndex`).
   - Weights, `OMPAutoBalance`, `OMPLoadBalance` and `OMPSplitIndex` are not used, so the boundaries never move
     between Jacobians. Auto-balancing does nothing in today's default anyway: `OMPSplitIndex` returns one column per
     chunk before it reads the weights (`ppp/omp_parallel.F90:766-771`).
2. **Fresh start per chunk:** `LocalJacBuilder` calls `pandf(-1,-1,neq,t,yl,wk)` before its first column when its new
   argument `ifresh=1`. It uses unperturbed `yl`, with the Jacobian-mode flag `yl(neq+1)=1` that `jac_calc` callers
   set (`bbb/oderhs.m:1716,1939,2325`), and the routine's own automatic `wk`. The chunk then starts from the fresh
   full-RHS state whatever ran before it on that thread (P3), so its columns are a function of `yl` and the boundaries
   only (P2). The debug switch `OMPJacChunkReset=0` turns this off (negative control).
3. **Per-chunk timing slot (L1-B1):** in fixed mode, `OMPJacBuilder` writes the chunk's time to
   `OMPTimeLocalJac(ichunk)`, never to `(tid+1)`. The array has `NchunksJac` elements, and the team can be larger
   than that: there is no `num_threads` clause, `InitOMPJac` calls `OMP_SET_NUM_THREADS(OMP_GET_MAX_THREADS())`
   (`:296`), and fixed mode can have few chunks. Fixed mode never reads the array for weights. Legacy mode keeps
   `(tid+1)`, unchanged, so NC4 stays bitwise. Its pre-existing out-of-bounds risk when `NchunksJac` is smaller than
   the team (`OMPJacNchunks>0` small, or `-1` with `Nthreads` below the team size) is recorded as finding F-61-2 for a
   follow-up, not fixed here.
4. **Heap fix (both modes):** drop `iJacColCopy`/`rJacElemCopy`. `LocalJacBuilder` writes straight into
   `iJacCol(:,ichunk)`/`rJacElem(:,ichunk)`, a contiguous column owned by that chunk, so there is no race and no
   temporary.
5. **Schedule:** unchanged, `schedule(dynamic,OMPLoopJacNchunk)` (D1, approved). With the reset, the schedule doesn't
   change the result (control G3-sched).
6. **Legacy (`OMPJacFixedChunks=0`):** today's path (`OMPJacNchunks`, weights, `OMPSplitIndex`, `(tid+1)` timing, no
   reset), apart from the heap fix, which changes no values (NC4).
7. **When settings take effect:** `InitOMPJac` runs from `InitParallel` in `allocate` (`bbb/odesetup.m:369`), which
   `exmain` calls on every grid step under `ismpion=0`, the default (`bbb/odesetup.m:6646-6650`). A change to the three inputs therefore takes effect at the
   next `exmain`. The `.v` descriptions say so.

### Guarantee and its scope (L1-M2, L1-M3)
- **The guarantee:** for a given `yl`, inputs, `neq`, `OMPJacNchunksFixed` and `OMPJacMinChunkLen`, the fixed-mode
  Jacobian is bitwise the same for any number of OpenMP threads (`OMP_NUM_THREADS`), any schedule, and any run. It
  holds **as long as a full `pandf` in Jacobian mode is a pure function of `yl` and the inputs, and no shared
  (non-threadprivate) variable carries results between threads.**
- **Known exceptions, already refused by the existing OpenMP roadblocks in `exmain`** (`bbb/odesetup.m:6727-6770`,
  evaluated after `allocate` has set `ParallelJac`):
  - `ismcnon≠0` ("Only ismcnon=0 is validated with openmp"). That covers `ismcnon=4`: `initialize_ismcnon`
    (`bbb/pandf_plasma_continuity.m:124-133`) multiplies the shared `parvis`/`travis` by `pnc_cf*` in every Jacobian-mode
    full call and only `jacobian_reset` divides it back, so the resets would compound it.
  - `isimpon` other than 0, 2, 6, 7 ("Invalid isimpon"). That covers `isimpon=5` with its `save`d `fmombal` arrays
    (`api/fmombal.m:70,368,1064`).
  - Also refused: `ishosor`, `ispsorave`, `cfvisxneoq/v`.
  - Control C-guard checks that both exceptions stop before any Jacobian. This plan adds no new guard. The `.v`
    description and `openmp-jacobian.md` name the conditions.
- **Shared state a full `pandf` writes:** AIUE-60's Probe S (plan `d2fac6e`, revised `203a5ff`) is a static scan of
  every unit reachable from `pandf`. It doesn't depend on whether the call is local or full, so it covers the reset.
  - Default paths, Part A, made safe by AIUE-60 (amendment 1): `areapl` and `TimingPandfOn` threadprivate; the `com`
    timers (`ttimpfe`, `ttimpjf`, `ttnpg`, `ttngxlog`, `ttngylog`, `ttngfd2`, `ttngfxy`, `totintrv`) atomic through
    `acctim`; `com.nfsp` written only when it changes.
  - Non-default paths kept in AIUE-60 (Part B in `203a5ff`): B2 `sputflxllim/rlim` (limiter sputtering) and B4
    `aph.workh/iflag_aph` (`istabon=5,6`).
  - Moved to AIUE-69 (Part C in `203a5ff`): `ghxpt/gvxpt/sxyxpt` (`nxpt=2`), `iwalli/iwallo/fngysi/fngyso` (coupled
    walls), and `isimpon=5` (refused above), together with `ismcnon` (also refused).
  - Phase 2 checks this dynamically for a full Jacobian-mode evaluation (G0b). The non-default paths are outside the
    validated scope and are named as such in `openmp-jacobian.md`.
- **The validated scope:** the eight `flow --all` configurations of the reproducer deck at 1–8 threads; the D_only
  default case (G9b); macOS arm64; and Linux x86-64 if R5 runs.
- **Any determinism or thread-identity failure in the gates is a FAIL whatever its cause** (F16/`areapl`, a new
  history carrier, a race). It is not attributed away. If the cause is a shared variable AIUE-60 fixes, the remedy is
  the rebase onto AIUE-60, after which the gates are re-run.

### Deliberate choices
- **`isjacreset` (`bbb/bbb.v:3305`, default 1) is unchanged in both modes** (owner Q4; removing it is AIUE-68). It
  doesn't change the Jacobian (control C-isjr).
- **RHS arm (`OMPParallelPandf1=1`): untouched** (owner Q6 → AIUE-58/AIUE-59). `OMPPandf1Rhs` runs on whatever state
  each worker kept from its last chunk, and under the dynamic schedule that varies. The `jacrhs` arm is report-only
  (R3), read against AIUE-58's R1 (the `hcyn` range bug at chunk edges).
- **The resets add to the full-RHS timers and counters** (`ttimpfe`, `ttnpg`, `TotTimePandf`, …). With AIUE-60's atomic
  accumulation the worker resets add CPU time summed over threads, so these timers can exceed wall time. The PR says so.
- **No settings-changed guard in `jac_calc_omp`:** `exmain` always re-runs `InitOMPJac` (Solution 7), so modes can't
  be mixed through `exmain`. This is documented, not guarded.

## Context references — read before implementing
- `ppp/ppp.v:18-40` (group `ParallelDebug`) and `ppp/ppp.v:42-56` (group `OMPJacSettings`), where the new variables go.
  `ppp/ppp.v` group `OMPJac`: `OMPTimeLocalJac(1:NchunksJac)`.
- `ppp/omp_parallel.F90:281-333` `InitOMPJac`: team size at `:296`, chunk count at `:312-319`, `nnzmxperchunk` at
  `:320-324`. Called from `InitParallel` (`ppp/parallel.F90:4-43`) at every `allocate` (`bbb/odesetup.m:369`, `:6649`).
- `ppp/omp_parallel.F90:495-642` `jac_calc_omp` (weights and split at `:545-563`).
- `ppp/omp_parallel.F90:645-754` `OMPJacBuilder`: copies `:678-699`, automatic arrays `:672,675`, init `:706-707`,
  loop `:718-747`, timing writes `:740,744`.
- `ppp/omp_parallel.F90:759-813` `OMPSplitIndex` (legacy; unchanged).
- `ppp/parallel.F90:159-345` `LocalJacBuilder`: arguments `:159-160,185`, `wk` `:195`, loop start `:210-211`.
- `bbb/oderhs.m:1090-1235`, the serial `jac_calc` column loop; `bbb/oderhs.m:1716`, the Jacobian-mode flag.
- `bbb/odesetup.m:6727-6770`, the OpenMP roadblocks.
- AIUE-60 plan `203a5ff:.claude/plans/AIUE-60-omp-races.md` (revision of `d2fac6e`: Part A, B2/B4 kept, B1/B3 to AIUE-69; merge notes).
- `.claude/context/openmp-jacobian.md` "OpenMP parallelism"; `.claude/context/variables-forthon.md` (`[none]` for
  dimensionless inputs, e.g. `bbb/bbb.v:1334`).
- Probe tree `uedge-wt/AIUE-61-probe` (`git -C … diff`): the revision-1 design. It is a reference only; it lacks Q5
  and the L1-B1 fix, and its `.v` texts are placeholders.

## Patterns to mirror
- A switch with a documented legacy value: `OMPCopyArray integer /1/ # For Debug purpose: …` (`ppp/ppp.v:35`).
- A fatal input check in `InitOMPJac`: `call xerrab('Nthread must be >0')` (`ppp/omp_parallel.F90:305`).
- Free-form F90 (`.claude/context/mppl-fortran.md` "Hand-written free-form sources"). Default integers are 8-byte
  (`-fdefault-integer-8`, `-DISZ=8`; seen in the probe build log and re-checked in task 4's build log), so
  `(i-1)*neq` doesn't overflow.

## Step-by-step tasks

### 1. UPDATE `ppp/ppp.v`
- **IMPLEMENT** in `OMPJacSettings`, after `OMPLoopJacNchunk` (`:54`):
  ```
  OMPJacFixedChunks   integer [none] /1/   # [1] (default): fixed contiguous chunks; every chunk starts from a fresh
                                           # full pandf on its thread, so the OpenMP Jacobian is bitwise reproducible and
                                           # the same for any number of OpenMP threads (OMP_NUM_THREADS); it still differs
                                           # from serial at round-off on some platforms. Holds where a full pandf resets
                                           # all state, i.e. the paths the exmain OpenMP checks allow (ismcnon=0 and
                                           # isimpon 0, 2, 6, 7 only); see .claude/context/openmp-jacobian.md. OMPJacNchunks,
                                           # OMPLoadBalance, OMPAutoBalance are then ignored. [0]: the partition used
                                           # before AIUE-61 (varies from run to run at round-off). OpenMP build only;
                                           # takes effect at the next exmain.
  OMPJacNchunksFixed  integer [none] /64/  # Maximum number of chunks when OMPJacFixedChunks=1. The count used is
                                           # min(OMPJacNchunksFixed, max(1, neq/OMPJacMinChunkLen)), independent of the
                                           # thread count. Use about 8 or more chunks per thread for load balance; a
                                           # different count changes the Jacobian at round-off. Next exmain.
  OMPJacMinChunkLen   integer [none] /300/ # Minimum number of Jacobian columns per chunk when OMPJacFixedChunks=1, so
                                           # small problems get fewer chunks (each chunk costs one full pandf).
                                           # Next exmain.
  ```
  Append `(OMPJacFixedChunks=0 only)` to the descriptions of `OMPJacNchunks`, `OMPLoadBalance`, `OMPAutoBalance` and
  `OMPBalanceStrength` (`:43-51`).
  In `ParallelDebug`, after `OMPCopyScalar` (`:38-40`):
  ```
  OMPJacChunkReset  integer [none] /1/  # For debug, OMPJacFixedChunks=1 only: [1] evaluate the full RHS (pandf) on
                                        # the thread before each chunk, so every chunk starts from the same state;
                                        # [0] skip it (the Jacobian then depends on the thread count and the schedule)
  ```
- **GOTCHA**: no `#` inside descriptions. None of these is written inside `pandf`, so none is `+threadprivate`.
- **VALIDATE**: after task 4's build, `python -c "from uedge import ppp; print(ppp.OMPJacFixedChunks, ppp.OMPJacNchunksFixed, ppp.OMPJacMinChunkLen, ppp.OMPJacChunkReset)"` → `1 64 300 1` in both venvs.

### 2. UPDATE `ppp/omp_parallel.F90` — `InitOMPJac`, `jac_calc_omp`, new `OMPFixedSplitIndex`
- **IMPLEMENT** `InitOMPJac` (`:312`), a new first branch:
  ```fortran
  if (OMPJacFixedChunks.gt.0) then
      if (OMPJacNchunksFixed.le.0) call xerrab('*** InitOMPJac: OMPJacNchunksFixed must be > 0 ***')
      if (OMPJacMinChunkLen.le.0) call xerrab('*** InitOMPJac: OMPJacMinChunkLen must be > 0 ***')
      ! problem size only (AIUE-61): never depends on the thread count
      NchunksJac=min(OMPJacNchunksFixed, max(1, neq/OMPJacMinChunkLen))
  elseif (OMPJacNchunks.eq.0) then   ! legacy branches unchanged
  ```
  `USE OMPJacSettings` is already whole-module. `nnzmxperchunk` keeps its formula, which gives the same total storage
  as today.
- **IMPLEMENT** `jac_calc_omp` (`:547-563`; `OMPTotTimeJacCalc = tick()` at `:545` stays outside the branch):
  `if (OMPJacFixedChunks.gt.0) then; call OMPFixedSplitIndex(neq,NchunksJac,OMPivmin,OMPivmax); else; <weights block and OMPSplitIndex unchanged>; endif`.
  Add `OMPJacFixedChunks` to the `USE OMPJacSettings, ONLY:` list (`:509-510`).
- **IMPLEMENT** `SUBROUTINE OMPFixedSplitIndex(neq,N,ivmin,ivmax)` next to `OMPSplitIndex`, outside `#ifdef _OPENMP`
  like it: `ivmin(i)=((i-1)*neq)/N+1`, `ivmax(i)=(i*neq)/N` for i=1..N. Comment: the boundaries depend only on neq and
  N.
- **VALIDATE**: task 4's build. With `OMPJacVerbose=1`, a full-problem run shows 64 chunks of 693 columns, the same in
  both Jacobians of one `--itermx 3` run. The Te box shows 1 chunk, and 25 with `OMPJacMinChunkLen=1`.

### 3. UPDATE `ppp/omp_parallel.F90` — `OMPJacBuilder` (heap fix, reset flag, timing slot)
- **IMPLEMENT**:
  - Delete `iJacColCopy` and `rJacElemCopy`: the declarations (`:672,675`), the init (`:706-707`), the `firstprivate`
    entry (`:720`) and the copy-back (`:734-735`). Pass `iJacCol(:,ichunk), rJacElem(:,ichunk)` to
    `LocalJacBuilder` (`:729-730`).
  - New local `integer :: ifresh`, set before the loop: `1` if `OMPJacFixedChunks.gt.0 .and. OMPJacChunkReset.gt.0`,
    else `0`. Shared and read-only in the loop, and passed as the new last argument.
  - **Timing (L1-B1):** replace the write at `:740`, and the verbose print at `:744`, with
    `if (OMPJacFixedChunks.gt.0) then; OMPTimeLocalJac(ichunk)=…; else; OMPTimeLocalJac(tid+1)=…; endif` (the print
    the same way). Comment: in fixed mode the chunk count can be smaller than the team; legacy unchanged.
  - Add `OMPJacFixedChunks` (from `OMPJacSettings`) and `OMPJacChunkReset` (from `ParallelDebug`) to the `USE` lists
    (`:646-647`). Comment at the call: why the chunk starts fresh (AIUE-8 C2, column history).
  - **Verbose table (implementation review I1-m2):** in `jac_calc_omp`, with `OMPJacVerbose>0`, fixed mode prints the
    chunk table without `OMPLoadWeight` (unused there); legacy mode prints it as before.
  - Keep `schedule(dynamic,OMPLoopJacNchunk)` and the `copyin` list (D1). Dropping `emcoef` from `copyin` (AIUE-60
    plan, A6) is left out deliberately, so the directive keeps its tested form.
- **GOTCHA**:
  - `iJacCol(:,ichunk)` is a contiguous column, so there is no copy-in temporary, and each `ichunk` belongs to one
    thread.
  - `OMPCollectJacobian` reads only `1:nnz-1` (`:477-482`).
  - The remaining `firstprivate` arrays (`ylcopy`, `iJacRowCopy`, `TimeJacRowcopy`, each of size neq) are unchanged.
- **VALIDATE**: task 4's build, then NC3 and G10.

### 4. UPDATE `ppp/parallel.F90` — `LocalJacBuilder`
- **IMPLEMENT**: a new argument `ifresh` (`integer,intent(in)`), appended at `:159-160` and declared at `:185`.
  Before `loopiv` (`:211`) add `if (ifresh.gt.0) call pandf (-1, -1, neq, t, yl, wk)`, with a comment: start this
  chunk from the fresh full-RHS state, so its columns don't depend on what this thread evaluated before (AIUE-61).
  Every column re-initialises `wk(ii1:ii2)` (`:236-238`), so nothing reads the reset's output.
- **GOTCHA**: `yl` is the thread's `firstprivate` `ylcopy`: unperturbed between columns, with `yl(neq+1)` as the
  caller set it. `LocalJacBuilder` has no other caller.
- **VALIDATE**:
  - `build_uedge.sh …/AIUE-61 venvs/AIUE-61-omp omp`.
  - The second tree: `git worktree add --detach ../AIUE-61-serial <commit>`, then `build_uedge.sh … venvs/AIUE-61-serial serial`.
  - `venvs/AIUE-61-chk`: the same as `build_uedge.sh … omp`, but with `-C "--build-option=--checkbounds"`. Use a copy
    of the script with that option, never an edit of the shared script.
  - All three import, with no new warnings in `ppp/*`.
  - Smoke: P2 with the real build gives the same full-problem hash at 2 and 4 threads.

### 5. UPDATE `.claude/context/openmp-jacobian.md` (own commit, trailer `AI-layer: code-facts`)
- **IMPLEMENT**:
  - In the Jacobian bullet:
    - the default fixed partition (`OMPJacFixedChunks=1`; the chunk count rule with `OMPJacNchunksFixed=64` and
      `OMPJacMinChunkLen=300`);
    - the full `pandf` at each chunk start, and why;
    - the guarantee and its scope: the exmain roadblocks, the AIUE-60/AIUE-69 non-default paths unvalidated, macOS ≠ serial;
    - the legacy switch;
    - no per-thread automatic copies;
    - `OMPTimeLocalJac` per chunk in fixed mode.
  - A rule for future code: a new history carrier that a full `pandf` doesn't reset, or a shared variable written in
    `pandf`, breaks the guarantee.
  - Then run `check_context_refs.py --changed origin/v9-develop` (`--fix` for the moved `ppp/omp_parallel.F90` lines;
    `--update` after re-reading).
- **VALIDATE**: the drift check is clean; `change_kind.py --range <base>..HEAD` is clean.

### 6. ADD `docs/reviews/AIUE-61-*` (validation tooling and record, an artifact path)
- `AIUE-61-run_protocol.sh`: every command below.
- `AIUE-61-jworker.py`: one Jacobian, its hash, `NchunksJac`, `ttjstor`.
- `AIUE-61-conv_worker.py`: the `dtreal=1e-9` driver.
- `AIUE-61-timing.py`: the interleaved timing driver with the load rule.
- `AIUE-61-state_probe.py`: G0a.
- `AIUE-61-shared-full.py`: G0b, a copy of AIUE-50's `scan_shared_state.py` sentinel test with the column pair
  replaced by one full `pandf(-1,-1)` in Jacobian mode.
- `AIUE-61-pytests_omp.py`: G9b, the AIUE-53 `pytests_worker.py` sequence with the jac arm, plus the C1-bound
  comparison.
- `AIUE-61-validation.txt`: the results, tool commits, and verbatim RESULT lines.

## Validation protocol (pre-registered; macOS arm64 unless stated; final run on the AIUE-60-combined tree)

**Tools and builds**, pinned in the validation record:
- Harness: the reviewed core, `feature/v9-AIUE-57-omp-ci-job` `8ee189d`.
- Serial check: `feature/v9-AIUE-53-serial-bitwise-check` `15ae327`.
- C1 gate: `docs/reviews/AIUE-56-c1-gate.py`, unchanged.
- Builds: `AIUE-61-omp`, `AIUE-61-serial`, `AIUE-61-chk`.
- References: `base-omp`/`base-serial` (product `0fac655`); `AIUE-56-omp` (the old default); after the rebase, also an
  `AIUE-60-omp` build of AIUE-60's approved commit as the old-default reference for G7.

**Run conditions:**
- Every harness run is a fresh `python -I` process with an empty HOME and `OMP_STACKSIZE=512M` (except G10b).
- Every fixed-mode run passes its settings explicitly, e.g.
  `--ppp '{"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64, "OMPJacMinChunkLen": 300}'`, because the harness
  provenance doesn't record the new switches (`worker.py:246-248`; a harness follow-up).
- At most 2 UEDGE processes at a time, at most 4 threads each; 8-thread runs and all timing runs run alone.

**"Deterministic"** means that everything the harness compares is bitwise equal between the runs: every captured
Jacobian, the post-`exmain` Jacobian, `sfscal`, `suscal`, `yldot`, the RHS probe, the printed `fnrm` sequence and
`get_fnrm`. Thread identity uses the same comparison (`cli.py compare A/run0 B/run0`). **Any determinism or identity
failure is a FAIL, whatever its cause** (Guarantee and its scope).

### Gates (each PASS/FAIL; all must PASS)
| ID | What | PASS when |
|---|---|---|
| **G0a** | P3 again (`AIUE-61-state_probe.py`), serial build `AIUE-61-serial`, **`yl(neq+1)=1` set explicitly**, all packages (`bbb, com, api, aph, wdf, svr, flx, grd, ppp, ncl`) in all 4 regions | after the full `pandf`, only timers/counters and the `Jacobian_restore` scratch differ from the fresh state |
| **G0b** | Shared writes of one full Jacobian-mode `pandf` (`AIUE-61-shared-full.py --sentinel`, all packages) | AIUE-56 base: WRITTEN is a subset of AIUE-60 Probe S Part A (preliminary result: exactly Part A). **Combined tree (pre-registered, AIUE-60 amendment 1): WRITTEN is exactly `com.nfsp` (a sentinel artefact: write-if-changed fires because the sentinel differs from `nisp`) plus the 7 timers `com.totintrv, ttimpfe, ttngfd2, ttngfxy, ttngxlog, ttngylog, ttnpg` (atomic, output only); `areapl` and `TimingPandfOn` drop out.** If AIUE-60's approved final tip differs from amendment 1, the expected set is re-derived from it before the run and recorded. Anything else: STOP and report (a race the reset exposes) |
| **G1** | Defaults unchanged: `serial_check.py --base-python base-serial --new-python AIUE-61-serial --base-omp-python base-omp --new-omp-python AIUE-61-omp --jobs 4` (all 42 cases, both pairs) | `RESULT: AGREE (bitwise identical; complete gate)` |
| **G2** | K=20 determinism, jac arm, 4 threads, one evaluation: `check --preset full`; `check --preset tebox` **with `OMPJacMinChunkLen=1`** (25 chunks) and with the default (1 chunk); `--repeats 20` each | all 20 runs deterministic in every group |
| **G3** | Thread identity. `check`, jac arm, K=3, at **1, 2, 3, 4 and 8** threads, for `full` (default), `tebox` with `OMPJacMinChunkLen=1`, and `tebox` with the default. Compare run0 of each thread count with 4 threads. **G3-sched:** `full` at 4 threads with `OMPLoopJacNchunk=3` against the default 1. **G3-count:** `AIUE-61-jworker.py` records `NchunksJac` at 1/2/4/8 threads for `full` (64), `tebox` (1), and `tebox` with min 1 (25) | AGREE for every pair; every group deterministic; G3-sched AGREE; G3-count shows the same count at every thread count |
| **G4** | Newton path: `check --itermx 3`, `full` and `tebox` (min 1), jac arm, 4 threads, K=5; plus 2 and 8 threads, K=1 each, compared with 4 threads | deterministic; thread pairs AGREE |
| **G5** | `flow --all` (8 configurations, 2/4/8 threads, K=2, both arms, `--max-jobs 2 --cores 8 --gate none`), plus a `compare` of jac run0 at 2 against 4 and 8 threads for every configuration | jac arm: "deterministic: yes" in **every** group, and every thread pair AGREE. jacrhs: report only (R3) |
| **G6** | AIUE-56 C1 gate on every one-evaluation jac run of G2, G3 and G5 | `GATE PASS` everywhere |
| **G7** | Cost (`AIUE-61-timing.py`), see the rules below | the median NEW/OLD `ttjstor` ratio is ≤ **1.10** at 2, 4 and 8 threads. Nothing else decides: there is no "within noise" exemption |
| **G8** | Heap fix (NC3) and the legacy path unchanged (NC4) | as stated in the controls |
| **G9a** | `validate` skill: branch hygiene, drift check, serial build and smoke, D_only with the serial build, **D_only with the OpenMP build** (decks' default switches), and the OpenMP check on the D_only default case (`OMPParallelJac=1, Nthreads=4`, `CheckJac=1`). **The `CheckPandf1=1` part (with `OMPParallelPandf1=1`) is report-only** (amended after implementation review I1-M1): the owner moved all parallel-RHS work to epic AIUE-70 on 2026-10-15 15:35 (`feature/v9-AIUE-8-planning`, `docs/specs/AIUE-8-progress.md:209-212`; Jira AIUE-59 comment 10029) | D_only per-file outcomes identical to the old build (OpenMP) and to `base-serial` (serial); drift check and hygiene clean; `CheckJac` reports no difference. `CheckPandf1`: output quoted verbatim for both builds, not gated |
| **G9b** | `AIUE-61-pytests_omp.py` on `pytests/unittests/D_only/nonog/default`: jac arm, the default and `OMPJacMinChunkLen=1`, at 2 and 4 threads, K=3, plus a serial reference | deterministic; 2 threads = 4 threads; deviation from serial within the C1-gate bounds on all rows. **`CheckJac=1` on the same case is report-only** (L1-m4): its absolute 1e-14 positional comparison (`ppp/parallel.F90:120`) can't express the accepted C2 difference, and it stops at the first entry. Its output is quoted verbatim |
| **G10** | L1-B1 bounds: `AIUE-61-chk` build, jac arm: `tebox` default (1 chunk) at 4 threads, K=1; **`tebox` with `OMPJacMinChunkLen=12` (2 chunks) and `full` with `OMPJacNchunksFixed=2`, both at 8 threads, K=5** (one process at a time). **G10-static:** a script check that `OMPTimeLocalJac(tid+1)` occurs only inside the legacy (`OMPJacFixedChunks=0`) branch of `OMPJacBuilder`. **G10b:** `AIUE-61-omp`, `full` default, 4 and 8 threads, with `OMP_STACKSIZE` removed explicitly (`env -u OMP_STACKSIZE` in the launcher), plus the same runs on `AIUE-56-omp` (default) as a control | no runtime bounds error and no crash; G10-static clean; G10b hashes equal G3's. If G10b crashes on **both** builds, it is recorded as pre-existing and the docs state that `OMP_STACKSIZE` is required; only an AIUE-61-only crash is a FAIL |

**G7 rules (L1-m2):**
- Configurations: NEW = `AIUE-61-omp` default; OLD = the old default (`AIUE-56-omp`, and after the rebase `AIUE-60-omp`);
  LEG = `AIUE-61-omp` with `OMPJacFixedChunks=0`.
- The full problem, one Jacobian per run (`com.ttjstor`, and `exmain` wall time), at 2, 4 and 8 threads.
- **At least 5 valid repeats per configuration at 2 and 4 threads, and at least 9 at 8 threads**, in one shuffled,
  interleaved order, one process at a time.
- **Wait for quiet (L2-m1):** before each run, poll the 1-minute load average every 15 s until load1 ≤ 14 − T (the
  host has 14 CPUs: 10 performance, 4 efficiency). Time out after 20 min, record the wait and the load at the start,
  and give up on the slot after a timeout.
- If a cell can't reach its count today, G7 is "not run (machine busy)". It is rescheduled with the coordinator for a
  quiet window, never passed, and the threshold is never relaxed.
- The runs are ordered as shuffled NEW/OLD pairs, with LEG interleaved.
- Report every sample with its load and wait; the medians, min–max, and the ratio of medians NEW/OLD and LEG/OLD; and
  the **median of the paired NEW/OLD ratios** (adjacent pairs). The gate uses the ratio of medians; the paired ratio is
  reported next to it.
- Secondary, report-only: the mean `ttjstor` per Jacobian from runs with `itermx=3`, 3 repeats per configuration at 4
  and 8 threads.

### Negative and positive controls (each must behave as stated, or the gate that relies on it is void)
| ID | Run | Expected |
|---|---|---|
| NC1 | `OMPJacChunkReset=0`, `full`, jac, 2 and 4 threads, K=2 | thread pair **MISMATCH** (P2-neg). Shows that G3 detects thread dependence |
| NC2 | `OMPJacFixedChunks=0` (legacy), `full`, jac, 8 threads, K=5 | **not deterministic** (study: 5 distinct hashes in 5 runs). Shows that G2 detects variation; a deterministic outcome is "control inconclusive", never a pass |
| NC3 | `full`, jac, 4 threads, `OMPJacNchunks=16, OMPAutoBalance=0`, no `ulimit`: `AIUE-56-omp` against `AIUE-61-omp` with `OMPJacFixedChunks=0` | AIUE-56 crashes (a signal, no record); AIUE-61 completes and passes the C1 gate |
| NC4 | jac arm, **1 thread**, `full` and `tebox`: `AIUE-56-omp` (default) against `AIUE-61-omp` with `OMPJacFixedChunks=0` | bitwise AGREE (with one thread both run the legacy path in serial column order, so the heap fix changes no value) |
| NC5 | `AIUE-61-chk`, legacy `OMPJacNchunks=2`, `tebox`, 4 threads, K=5 | at least one run stops with a bounds error on `OMPTimeLocalJac` (F-61-2). Shows that G10 can see this array; if none trips, G10 is void and reported so |
| C-isjr | `full`, jac, 4 threads, `bbb.isjacreset=0` against the default | AGREE; its time is reported |
| C-guard | the deck with `OMPParallelJac=1` plus `ismcnon=4`; plus `isimpon=5` | `exmain` stops with the roadblock messages before any Jacobian |
| C-ser | every `check` includes a serial reference | for R1 |

### Reported, not gated
- **R1:** deviation from serial for each configuration and thread count: entries, rows by equation, and worst ratio,
  compared with `AIUE-56-validation.txt`.
- **Pre-registered for the combined tree (I1-M2.5):** AIUE-60 changes the clip test in `LocalJacBuilder` from
  `sfscal(iv)` to `sfscal(ii)` (`ppp/parallel.F90:288,292` on AIUE-60). With the default `jaccliplim=0`
  (`bbb/bbb.v:3308`), which the reproducer deck doesn't change, the test is `jacelem≠0` either way, so the full-problem
  hash **`8761cd9e36658ee1`** (P2/G3) and R2's bits are expected to be unchanged on the combined tree. A change is
  investigated, not explained away.
- **R2:** the `dtreal=1e-9` scenario (`AIUE-61-conv_worker.py`), new default, 4 threads K=2, and 2 and 8 threads K=1.
  Pre-registered from P5: step 1 fails (`iterm=4`) in all four runs, with final `get_fnrm` `0x1.aa0e230edbab4p-2` and a
  bitwise-equal final state. **Identical outcomes are required (owner Q3), and a difference is a G3 FAIL.** Convergence
  is not required.
- **R3:** the jacrhs arm (G5) against the AIUE-56 build, read alongside AIUE-58's R1. Regressions go to AIUE-58.
- **R4:** sensitivity:
  - `OMPJacNchunksFixed` 32 and 128 at 4 and 8 threads, 3 interleaved repeats;
  - the Te box `ttjstor` with the default (1 chunk) and with min 1 (25 chunks);
  - the D_only time with the default;
  - **mid-size effect of Q5 (L2-m3):** `full` with `OMPJacNchunksFixed` 8 and 16 at 8 threads, 3 interleaved repeats
    each, against the old default (it stands in for problems with neq ≈ 2 400–4 800, which get 8–16 chunks).
- **R5:** Linux x86-64, if Docker is free (AIUE-62 scripts; Debian, `LDFLAGS=-fopenmp`, `--cpus 5`, one container at a
  time, coordinated with AIUE-64):
  - `check` runs: `tebox` (min 1) and `full`, jac, 4 threads, K=5; `full` jac at 2 and 8 threads, K=2; `up` jac at 4
    and 8 threads, K=5 (M3, AIUE-65); thread-pair compares.
  - Expected: `tebox` and `full` bitwise equal to serial and deterministic. M3 either disappears or appears
    deterministically.
  - A determinism or identity failure there is a G2/G3 FAIL. Not run → "Linux not run" in the PR.
- **Findings for others, not fixed here:**
  - **F-61-1** (RCA, AIUE-60): `jacobian_reset` restores six scalars that were taken from the box's last cell, so it
    writes them to the wrong cell (`bbb/pandf_plasma_energy.m:574-575,597,771,909,927`, `bbb/pandf_jacobian.m:87-93`).
    It happens in serial too, and it is a history carrier.
  - **F-61-2** (follow-up): legacy `OMPTimeLocalJac(tid+1)` overflows when `NchunksJac` is smaller than the team (NC5).

### Run order and estimate
1. Implement on the AIUE-56 base. Build the three venvs (≈ 15 min). Development checks: G0a, G0b, G3 (`full`/`tebox`
   at 2/4), NC1, NC3, NC4, G10 and NC5 (≈ 60 min) — an early warning, not the final record.
2. When AIUE-60's implementation is approved: rebase, rebuild, then the **final run on the combined tree:**
   - G0a and G0b (10 min)
   - **G-common and G-iotable** (AIUE-60's gates, run because AIUE-61 edits `ppp/ppp.v`): AIUE-60's static
     `/ompcommonscalarcopy/` check `docs/reviews/AIUE-60-common-check.py` and its probe
     `docs/reviews/AIUE-60-iotable-probe.py`, on the combined OpenMP build, with the PASS criteria AIUE-60 states;
     record the extensions that define `_ompcommonscalarcopy_` and their block sizes (minutes)
   - G1 (35 min)
   - NC1–NC5, C-isjr, C-guard (30 min)
   - G2 (30 min)
   - G3 and G3-sched (40 min)
   - G4 (25 min)
   - G5 (60–90 min)
   - G6 (minutes)
   - G7, alone (about 70 runs, ≈ 60 min) and R4
   - R2 (≈ 40 min)
   - G9a and G9b (30 min)
   - G10 (15 min)
   - R5 (≈ 60 min)

## AI-layer facts affected
- `.claude/context/openmp-jacobian.md`: the Jacobian bullet (task 5) and the moved `ppp/omp_parallel.F90` refs
  (`:908`, and `:959-961` in rule 4).
- `.claude/context/mppl-fortran.md:69` (`ppp/omp_parallel.F90:908-936`): `--fix`.
- `architecture.md` (the `ppp` file list is unchanged), `CLAUDE.md`, `testing.md`: no change.
- After the rebase, merge with AIUE-60's edits to the same file and re-lock.

## Acceptance criteria (Jira AIUE-61, mapped)
- [ ] AIUE-53 serial check AGREE, both builds, complete gate (G1)
- [ ] K=20 bitwise-identical runs, Te box and full problem, 4 threads (G2)
- [ ] The same Jacobian at 2/4/8 threads, plus 1 and 3 (G3)
- [ ] `flow --all` deterministic in every configuration (G5)
- [ ] Also deterministic over 3 Newton iterations (G4)
- [ ] AIUE-56 C1 gate PASS (G6, G9b); deviation from serial reported (R1)
- [ ] Cost against the old default, interleaved at 2/4/8 threads, within about 10 % (G7)
- [ ] Effect on M3 (R5) and on the `dtreal=1e-9` scenario reported, the latter deterministic (R2)
- [ ] Heap fix: `OMPJacNchunks≠0` no longer crashes (NC3)
- [ ] Legacy behaviour available and documented (`OMPJacFixedChunks=0`, NC4)
- [ ] No out-of-bounds write with fewer chunks than threads (G10)
- [ ] Owner Q5: the minimum chunk length is implemented and tested (tasks 1–2, G3-count)
- [ ] New variables visible from Python with `[none]` units and descriptions (task 1)
- [ ] `openmp-jacobian.md` updated; drift check clean (task 5)
- [ ] Final gates run on the tree combined with AIUE-60, or the PR says the claim is unproven until then
- [ ] The PR states: the OpenMP default change (decision 9, an owner-approved exception, comment 10021); D1; the
      trade-off against the old default's occasional bitwise agreement; that small problems no longer parallelise the
      Jacobian, or only partly (under the Q5 rule a problem with neq < 300·T can't use all T threads, and below 600
      it runs as one chunk; R4's mid-size numbers); that problems with neq up to ~5 000 at 8 threads may build the Jacobian up to ~2x slower (neq < 600 ~3x, D_only)
      than OMPJacFixedChunks=0, with the knobs; that the parallel-RHS self-check on small grids is affected by a
      pre-existing out-of-bounds write in MakeXptChunks (AIUE-70, implementation review I2-M1); that the resets add CPU time summed over threads to the full-RHS timers (which can then
      exceed wall time); findings F-61-1
      and F-61-2

## Notes
- Rejected:
  - literal `static,1` without a reset (P1);
  - one chunk per thread (+70–108 %, study);
  - replay (E, +27–98 %, study);
  - `schedule(runtime)` (it crashed in the study's build, and isn't needed);
  - a settings-changed guard (Solution 7).
- Scratch artefacts to remove after the ticket: `uedge-wt/AIUE-61-probe`, `venvs/AIUE-61-probe`,
  `uedge-wt/scratch-AIUE-61`. All of them were created during this ticket's planning, and nothing in them is committed.
