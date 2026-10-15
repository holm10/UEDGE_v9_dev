# Feature: AIUE-61 — Reproducible OpenMP Jacobian: fixed chunk partition (decision 9, option F)

Validate the patterns and file references below before implementing. Line numbers are those of this branch's base
(`bugfix/v9-AIUE-56-omp-jacobian-fix` at `1553e75`).

## Summary
**Type**: Numerics/Parallel (OpenMP-only code path), plus the `OMPJacNchunks≠0` stack-crash fix
**Complexity**: Low (code, ~40 lines in `ppp/`), High (validation)
**Default results**:
- **Serial build and OpenMP build with `OMPParallelJac=0`: unchanged.** The changed routines run only with
  `ppp.OMPParallelJac=1` in the OpenMP build. The new `.v` variables are inert elsewhere.
- **OpenMP Jacobian (`OMPParallelJac=1`): changed on purpose. This is the owner's decision 9 (2026-10-15),
  an explicit, owner-approved exception to the PRD/`CLAUDE.md` rule against changing defaults.** The default OpenMP
  Jacobian becomes bitwise reproducible and independent of the thread count. On macOS arm64 it still differs from
  serial at round-off (C2: about 12 000 entries in 78 rows of the full problem, worst 4.6e-9 × row max, probe P2).
  On Linux x86-64 it is expected to equal serial bitwise (to be checked, G10). The old behaviour stays available
  through `ppp.OMPJacFixedChunks=0`. The PR states this in its first paragraph.
**Packages / files**: `ppp/ppp.v`, `ppp/omp_parallel.F90` (`InitOMPJac`, `jac_calc_omp`, `OMPJacBuilder`, new
`OMPFixedSplitIndex`), `ppp/parallel.F90` (`LocalJacBuilder`), `.claude/context/openmp-jacobian.md` (code facts),
`docs/reviews/AIUE-61-*` (validation scripts and record)
**Branch / worktree**: `bugfix/v9-AIUE-61-omp-static-partition` @ `/Users/holma/Documents/uedge/src/uedge-wt/AIUE-61`
(base: `bugfix/v9-AIUE-56-omp-jacobian-fix` `1553e75`, stacked; the PR targets that branch until AIUE-56 merges, then
`git rebase --onto v9-develop bugfix/v9-AIUE-56-omp-jacobian-fix`). Venvs: `venvs/AIUE-61-omp` (this tree),
`venvs/AIUE-61-serial` (second tree `uedge-wt/AIUE-61-serial`, detached at the same commit, as AIUE-56 did).

## Owner decisions this plan relies on, and one deviation that needs the owner (D1)

- **Decision 9 = option F** (Jira AIUE-61): fixed contiguous chunks, a chunk count that doesn't depend on the thread
  count (capped at `neq`), boundaries that don't move between Jacobians, heap fix, new default, old behaviour behind
  a documented OpenMP-only switch, serial unchanged. All of this is implemented as decided.
- **D1, deviation for the owner to confirm before implementation:** decision 9 names `schedule(static,1)` and
  assumes that "the Jacobian depends only on the chunk count". **The cost study's own data refutes that
  assumption** (P1 below). The same 64 chunks give a different Jacobian at 4 and at 8 threads. So static round-robin
  alone can't meet the acceptance criterion "the same Jacobian at 2/4/8 threads". This plan adds a **fresh full `pandf`
  on the thread at the start of every chunk**. That makes each chunk's columns a pure function of `yl` and the chunk
  boundaries. The result then doesn't depend on the schedule either, so the plan keeps the existing
  `schedule(dynamic,OMPLoopJacNchunk)` loop, which balances load better than static round-robin at the same chunk
  count. The study measured static round-robin with 64 chunks at +24 % at 8 threads, and dynamic at −4 %. This
  also removes the loop duplication the prototype needed. If the owner insists on literal `static,1`, it is a
  one-clause change in task 3. The reset stays in either case, because without it the thread-count criterion fails.

## Pre-plan probes (scratch, macOS arm64, gfortran 15; not reviewed; reproduce in phase 2)

Scratch files are in `/Users/holma/Documents/uedge/src/uedge-wt/scratch-AIUE-61/`. The prototype tree is
`uedge-wt/AIUE-61-probe` (detached at `1553e75` plus the design below), with `venvs/AIUE-61-probe` (OpenMP). The
case is the reviewed AIUE-57 harness case (`full`: neq 44352, numvar 14; `tebox`: neq 25).

| # | Question | Result |
|---|---|---|
| P1 | Does static round-robin without a reset give a thread-independent Jacobian? (cost-study records, `OMPJacSchedule=2`, `OMPAutoBalance=0`) | **No.** 16 chunks: same hash at 2/4/8 threads; 32 chunks: same at 4/8. **64 chunks: 4 threads `217b791b…` ≠ 8 threads `8761cd9e…`** (5 runs each, each deterministic). Mechanism: under `static,1` a worker starts chunk k from the state left by chunk k−T. With 64 chunks (693 columns each), chunk k−4 lies within the column-history reach of chunk k (P3), and chunk k−8 does not. |
| P2 | Fixed partition, 64 chunks, **reset (full `pandf` at every chunk start)**, `schedule(dynamic,1)` | **Full problem: identical hash `8761cd9e36658ee1` at 2, 3 and 4 threads and in two runs at 4 threads**, nnz 3 180 971. This equals the study's 64-chunk static run at 8 threads, where every chunk also started from a state without nearby history. vs serial (`0ee4446a…`, nnz 3 190 290): 12 275 mismatching entries in 78 rows, worst 4.59e-9 × serial row max (AIUE-56 C1 gate bound 1e-6). Te box: same hash at 2 and 4 threads, 2 entries in 1 row vs serial, 5.62e-10. Cost at 4 threads: `ttjstor` 9.99/10.06 s vs 9.68 s for the old default in the same batch (single samples). At 2 threads: 19.31 s (the study's old default was 18.4 s). |
| P2-neg | Same partition **without** the reset (`OMPJacChunkReset=0`) | Full problem: 2 threads `48d3f455…` ≠ 4 threads `6ece2e5a…` (nnz 3 184 409 vs 3 181 726). The reset is what removes the thread dependence. |
| P3 | Does a full `pandf(-1,-1)` erase the column-loop history? (serial build `AIUE-56-serial`; snapshot every variable of `bbb, com, api, aph, wdf, svr, flx, grd, ppp`; 3000-column Jacobian-like loops in 4 regions, then a full `pandf`) | **Yes.** The column loop changes about 150 variables (`vsoree`-type carriers, `Selec` ranges, `areapl`, `api.work2/iworki`, …). After the full `pandf`, every variable equals the fresh state except (a) timers/counters and (b) the `Jacobian_restore` scratch (`*old`, `*o`, `*om`). `jacobian_store_*` writes the scratch at the start of each local `pandf` and `jacobian_reset` reads it at the end of the same call (`bbb/pandf_jacobian.m:6-67,69-131`), so it carries no history. `yldot` is bitwise equal. |
| P4 | Cost of the reset | Full `pandf` 23.1 ms, local `pandf` 0.30 ms, serial Jacobian 34.2 s (full problem, 1 thread). 64 resets are about 1.5 s of CPU, which is about 4–5 % of the Jacobian work, spread over the threads. Te box: the reset dominates (`ttjstor` 0.22–0.35 s vs 0.06 s without it), because the grid is full-size while neq is 25. |
| P5 | `dtreal=1e-9` scenario (deck, `full`, 5 × `exmain`, stop at the first failed step), prototype at 4 threads | **64 chunks: step 1 fails, `iterm=4` after 30 iterations, final `get_fnrm` `0x1.aa0e230edbab4p-2`.** These are the same bits as the cost study's 64-chunk static run at 8 threads (failed 3/3), so the failure is reproducible across thread counts. 128 chunks: also fails (`0x1.a9ef9d857899cp-2`). For comparison: serial converges (21, 4, 3, 4, 3); serial with `-ffp-contract=off` fails; the old default converged in 3 of 5 runs at 4 threads. The step is on a knife edge at round-off; the new default falls on the failing side deterministically on this deck (Q3). |

## Problem and solution

**Problem (RCA `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md` §Jacobian RCA, on `feature/v9-AIUE-62-linux-characterisation`):**
after the C1 fix (AIUE-56), the OpenMP Jacobian still differs from serial at round-off and **varies from run to
run** (C2/M2). The serial Jacobian depends on the history inside its column loop: `vsoree` and similar values get a
different last bit in a local loop than in the full-row loop, and later columns read them. OpenMP workers have a
different history, and with the default dynamic one-column chunks it depends on timing. Separately, any
`OMPJacNchunks≠0` crashes the full problem: the `firstprivate` automatic arrays `iJacColCopy`/`rJacElemCopy`
(`ppp/omp_parallel.F90:672,675,720`) sit on the master's 8 MB stack.

**Solution (default `OMPJacFixedChunks=1`):**
1. **Fixed partition:** `NchunksJac = min(OMPJacNchunksFixed, neq)` (default 64, independent of `Nthreads`). Chunk i
   covers columns `(i−1)·neq/N + 1 … i·neq/N` (integer division), a pure function of `neq` and `N`. Load weights,
   `OMPAutoBalance`, `OMPLoadBalance` and `OMPSplitIndex` are not used in this mode, so the boundaries never move
   between Jacobians. The study shows that auto-balancing does nothing in today's default anyway: `OMPSplitIndex`
   returns one column per chunk before it reads the weights (`ppp/omp_parallel.F90:766-771`).
2. **Fresh start per chunk:** `LocalJacBuilder` calls `pandf(-1,-1,neq,t,yl,wk)` (unperturbed `yl`, the routine's
   own automatic `wk`) before its first column when its new argument `ifresh=1`. Every chunk then starts from the
   fresh full-RHS state whatever ran before it on that thread (P3), so the Jacobian is a function of `yl` and the
   boundaries only (P2). The debug switch `OMPJacChunkReset=0` turns this off (negative control).
3. **Heap fix (both modes):** drop `iJacColCopy`/`rJacElemCopy`. `LocalJacBuilder` writes straight into
   `iJacCol(:,ichunk)`/`rJacElem(:,ichunk)`, a contiguous column of the module arrays owned by that chunk only, so
   there is no race and no temporary.
4. **Schedule:** unchanged, `schedule(dynamic,OMPLoopJacNchunk)` (see D1).
5. **Legacy (`OMPJacFixedChunks=0`):** today's code path exactly (`OMPJacNchunks`, weights, `OMPSplitIndex`, no reset),
   apart from the heap fix, which changes no values (control NC4).

**Deliberate choices:**
- **`isjacreset` (`bbb/bbb.v:3305`, default 1) is left as it is in both modes.** Its extra local `pandf` per cell
  (`ppp/parallel.F90:320-338`) does not change the Jacobian: it recomputes the same box from the same inputs (RCA
  emulation; control C-isjr below re-checks it). It is a consistency check that aborts if a repeated local `pandf`
  changes `wk`. It is in the old default too, so the timing comparison is like for like. Users can already set
  `bbb.isjacreset=0` to save about 5 %. The serial `jac_calc` ignores it, so changing its default would be an
  unrelated behaviour change.
- **`OMPParallelPandf1` (RHS arm):** untouched. `OMPPandf1Rhs` still runs on whatever state each worker kept from its
  last Jacobian chunk. Under the dynamic schedule, which chunk that is varies from run to run. AIUE-56 showed the
  parallel RHS equal to serial on the Te box and the full problem at 4 threads, but whether it depends on that state
  belongs to AIUE-58. The `jacrhs` arm is report-only here. If its determinism is worse than on the AIUE-56 build,
  that goes to AIUE-58 (option for the owner, Q6: one full `pandf` per thread after the loop).
- **Shared-state race F16 (`areapl`, `bbb/bbb.v:951`, not threadprivate, written and immediately read in the plate BCs
  `bbb/pandf_boundary.m:3091-4281`):** the resets add full evaluations that write it. If a determinism run fails in
  plate rows, that is reported as a probable F16 effect and coordinated with AIUE-60. It is not masked here.

## Context references — read before implementing
- `ppp/ppp.v:18-40` (group `ParallelDebug`), `ppp/ppp.v:42-56` (group `OMPJacSettings`): where the new variables go.
- `ppp/omp_parallel.F90:281-333` `InitOMPJac` (chunk count at `:312-319`, `nnzmxperchunk` at `:320-324`); called from
  `InitParallel` (`ppp/parallel.F90:4-43`) at every `allocate` (`bbb/odesetup.m:369`).
- `ppp/omp_parallel.F90:495-642` `jac_calc_omp` (weights and split at `:545-563`).
- `ppp/omp_parallel.F90:645-754` `OMPJacBuilder` (copies `:678-699`, automatic arrays `:672,675`, init `:706-707`,
  loop `:718-747`).
- `ppp/omp_parallel.F90:759-813` `OMPSplitIndex` (legacy; unchanged).
- `ppp/parallel.F90:159-345` `LocalJacBuilder` (arguments `:159-160,185`, `wk` `:195`, loop start `:210-211`).
- `bbb/oderhs.m:1090-1235` serial `jac_calc` column loop (no `isjacreset` call, `:1218-1222` commented out).
- `.claude/context/openmp-jacobian.md` "OpenMP parallelism" (Jacobian bullet, line refs).
- `.claude/context/variables-forthon.md` (units bracket, `#` description, `[none]` for dimensionless switches, e.g.
  `bbb/bbb.v:1334`).
- Prototype for the heap fix: the cost study diff (`OMPJacBuilder` hunks only; its `OMPJacSchedule`/`OMPJacReplay`
  scratch switches are **not** brought over). The probe tree `uedge-wt/AIUE-61-probe` holds the design below as an
  uncommitted diff (`git -C …/AIUE-61-probe diff`). It is a reference, not a source to copy blindly: its `.v` texts
  are placeholders.

## Patterns to mirror
- Switch with a documented legacy value: `OMPCopyArray integer /1/ # For Debug purpose: …` (`ppp/ppp.v:35`).
- Fatal input check in `InitOMPJac`: `call xerrab('Nthread must be >0')` (`ppp/omp_parallel.F90:305`).
- Free-form F90 rules (`.claude/context/mppl-fortran.md` "Hand-written free-form sources"): `!` comments, `&`
  continuation, `USE …, ONLY:`. Default integers are 8-byte (`-fdefault-integer-8`, `ISZ=8` in the build line), so
  `(i-1)*neq` doesn't overflow.

## Step-by-step tasks

### 1. UPDATE `ppp/ppp.v`
- **IMPLEMENT** in `OMPJacSettings`, after `OMPLoopJacNchunk` (`:54`):
  ```
  OMPJacFixedChunks   integer [none] /1/  # [1] (default): split the Jacobian columns into OMPJacNchunksFixed fixed
                                          # contiguous chunks (at most neq) and start every chunk from a fresh full
                                          # pandf on its thread, so the OpenMP Jacobian is bitwise reproducible and the
                                          # same for any Nthreads; OMPJacNchunks, OMPLoadBalance and OMPAutoBalance are
                                          # ignored. [0]: the partition used before AIUE-61 (OMPJacNchunks chunks, load
                                          # balancing), which varies from run to run at round-off. OpenMP build only.
  OMPJacNchunksFixed  integer [none] /64/ # Number of chunks when OMPJacFixedChunks=1, capped at neq. Independent of
                                          # Nthreads; use at least about 8 chunks per thread for load balance.
  ```
  Append `(OMPJacFixedChunks=0 only)` to the descriptions of `OMPJacNchunks`, `OMPLoadBalance`, `OMPAutoBalance`,
  `OMPBalanceStrength` (`:43-51`).
  In `ParallelDebug`, after `OMPCopyScalar` (`:38-40`):
  ```
  OMPJacChunkReset  integer [none] /1/  # For debug, OMPJacFixedChunks=1 only: [1] evaluate the full RHS (pandf) on
                                        # the thread before each chunk, so every chunk starts from the same state;
                                        # [0] skip it (the Jacobian then depends on Nthreads and the schedule)
  ```
- **GOTCHA**: no `#` inside descriptions; none of these is written inside `pandf`, so they are not `+threadprivate`.
- **VALIDATE**: after task 4's build: `python -c "from uedge import ppp; print(ppp.OMPJacFixedChunks, ppp.OMPJacNchunksFixed, ppp.OMPJacChunkReset)"` → `1 64 1`, in both venvs.

### 2. UPDATE `ppp/omp_parallel.F90` — `InitOMPJac`, `jac_calc_omp`, new `OMPFixedSplitIndex`
- **IMPLEMENT** `InitOMPJac` (`:312`): a new first branch
  ```fortran
  if (OMPJacFixedChunks.gt.0) then
      if (OMPJacNchunksFixed.le.0) call xerrab('*** InitOMPJac: OMPJacNchunksFixed must be > 0 ***')
      NchunksJac=min(OMPJacNchunksFixed,neq)
  elseif (OMPJacNchunks.eq.0) then   ! legacy branches unchanged
  ```
  (`USE OMPJacSettings` is already whole-module.) `nnzmxperchunk` keeps its formula (same total storage as today).
- **IMPLEMENT** `jac_calc_omp` (`:545-563`): `if (OMPJacFixedChunks.gt.0) then call OMPFixedSplitIndex(neq,NchunksJac,OMPivmin,OMPivmax) else <weights block and OMPSplitIndex unchanged> endif`.
  Add `OMPJacFixedChunks` to the `USE OMPJacSettings, ONLY:` list (`:509-510`).
- **IMPLEMENT** `SUBROUTINE OMPFixedSplitIndex(neq,N,ivmin,ivmax)` next to `OMPSplitIndex` (outside `#ifdef _OPENMP`,
  like it): `ivmin(i)=((i-1)*neq)/N+1`, `ivmax(i)=(i*neq)/N`, for i=1..N. Comment: the boundaries depend only on neq and N, never on weights or timings.
- **GOTCHA**: with N = neq every chunk is one column. That is valid, but each chunk then pays one full `pandf` (P4: the Te box).
- **VALIDATE**: build (task 4). With `OMPJacVerbose=1` the chunk table of a full-problem run shows 64 chunks of 693 columns, the same in two Jacobians of one `--itermx 3` run.

### 3. UPDATE `ppp/omp_parallel.F90` — `OMPJacBuilder` (heap fix, reset flag)
- **IMPLEMENT**: delete `iJacColCopy`, `rJacElemCopy` (declarations `:672,675`, init `:706-707`, `firstprivate`
  `:720`, copy-back `:734-735`). Pass `iJacCol(:,ichunk), rJacElem(:,ichunk)` to `LocalJacBuilder` (`:729-730`).
  New local `integer :: ifresh`, set before the loop: `ifresh = merge(1,0, OMPJacFixedChunks.gt.0 .and. OMPJacChunkReset.gt.0)`
  (or an `if`), passed as the new last argument. It is shared and read-only in the loop. Add `OMPJacFixedChunks`, and
  `OMPJacChunkReset` from `ParallelDebug`, to the `USE` lists (`:646-647`). Comment at the call: why the chunk starts fresh (AIUE-8 C2: column history; P3).
  Keep `schedule(dynamic,OMPLoopJacNchunk)` (D1; literal decision 9 would be `schedule(static,1)` here).
- **GOTCHA**: `iJacCol(:,ichunk)` is a contiguous column, so no copy-in temporary; each `ichunk` is written by one
  thread only. `iJacCol` entries beyond `nnz(ichunk)-1` keep the old values, and `OMPCollectJacobian` reads only
  `1:nnz-1` (`:477-482`). The remaining `firstprivate` arrays (`ylcopy`, `iJacRowCopy`, `TimeJacRowcopy`, size neq) are unchanged (not this ticket).
- **VALIDATE**: task 4's build, then NC3 (the crash is gone).

### 4. UPDATE `ppp/parallel.F90` — `LocalJacBuilder`
- **IMPLEMENT**: new argument `ifresh` (`integer,intent(in)`, appended to the argument list `:159-160` and the declaration
  `:185`). Before `loopiv` (`:211`): `if (ifresh.gt.0) call pandf (-1, -1, neq, t, yl, wk)`, with the comment "start this chunk
  from the fresh full-RHS state, so the columns don't depend on what this thread evaluated before (AIUE-61)". `wk`
  is the routine's automatic array (`:195`). Every column re-initialises `wk(ii1:ii2)` from `yldot00` (`:236-238`), so the reset's `wk` contents are never read.
- **GOTCHA**: `yl` here is the thread's `firstprivate` `ylcopy`, unperturbed between columns. `LocalJacBuilder` has no other caller (`grep -rn LocalJacBuilder ppp bbb`).
- **VALIDATE**: `build_uedge.sh /Users/holma/Documents/uedge/src/uedge-wt/AIUE-61 venvs/AIUE-61-omp omp`; then the second tree
  `git worktree add --detach ../AIUE-61-serial <commit>` → `build_uedge.sh … venvs/AIUE-61-serial serial`. Both
  import; no new warnings in `ppp/*` (`grep -a -i warning` in the build logs for `omp_parallel`/`parallel.F90`). Smoke run: probe P2 again (`jworker.py` in the scratch directory) with the real build: same hash at 2 and 4 threads.

### 5. UPDATE `.claude/context/openmp-jacobian.md` (own commit, trailer `AI-layer: code-facts`)
- **IMPLEMENT**: in the Jacobian bullet, the default is a fixed contiguous partition (`OMPJacFixedChunks=1`,
  `OMPJacNchunksFixed=64`, capped at neq). Each chunk starts with a full `pandf` on its thread (why: column history,
  AIUE-8 C2). The result is bitwise reproducible and independent of `Nthreads`, but not equal to serial on macOS
  arm64. The legacy partition is `OMPJacFixedChunks=0`. `LocalJacBuilder` writes straight into `iJacCol/rJacElem`, so
  there are no per-thread automatic copies. A rule for future code: anything that makes a full `pandf` not reset
  some state (a new history carrier) breaks this guarantee. Then `uv run .claude/hooks/check_context_refs.py
  --changed origin/v9-develop` (`--fix` for the moved `ppp/omp_parallel.F90` lines, then `--update` after re-reading).
- **VALIDATE**: the drift check is clean; `uv run .claude/hooks/change_kind.py --range bugfix/v9-AIUE-56-omp-jacobian-fix..HEAD` is clean.

### 6. ADD `docs/reviews/AIUE-61-*` (validation tooling and record, artifact path)
- `AIUE-61-run_protocol.sh` (every phase-2 command below), `AIUE-61-jworker.py` and `AIUE-61-conv_worker.py` (the
  probe workers, recreated because the session scratchpad of the cost study is gone), `AIUE-61-timing.py`
  (interleaved timing driver), `AIUE-61-validation.txt` (results, tool commits, verbatim RESULT lines).

## Validation protocol (pre-registered; macOS arm64 unless stated)

**Tools and builds (pinned in the validation record).** Harness: reviewed core at
`feature/v9-AIUE-57-omp-ci-job` `8ee189d` (`/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp/harness/cli.py`).
Serial check: `feature/v9-AIUE-53-serial-bitwise-check` `15ae327` (`harness/serial_check.py`). C1 gate:
`docs/reviews/AIUE-56-c1-gate.py` from the AIUE-56 branch (unchanged). Builds: `AIUE-61-omp`, `AIUE-61-serial`.
References: `base-omp`, `base-serial` (`v9-develop` product `0fac655`) and `AIUE-56-omp` (the old default, C1-fixed).
Every harness run is a fresh `python -I` process with an empty HOME and `OMP_STACKSIZE=512M`. **Every new-mode run passes
its settings explicitly** (`--ppp '{"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64}'`), because the harness
provenance doesn't record the new switches (`worker.py:246-248`; follow-up for the harness, not here).
Budget: at most 2 UEDGE processes at a time and at most 4 threads each, except 8-thread runs, which run alone. Timing runs
one process at a time. Record the load average with each timing run.

**"Deterministic"** below means: every quantity the harness compares (every captured Jacobian, the post-`exmain`
Jacobian, `sfscal`, `suscal`, `yldot`, the RHS probe, the printed `fnrm` sequence, `get_fnrm`) is bitwise equal between
the runs (the harness's run-0-vs-run-k verdict). Thread identity uses the same comparison
(`cli.py compare A/run0 B/run0`).

### Gates (each PASS/FAIL; all must PASS)
| ID | What | PASS when |
|---|---|---|
| **G1** | Defaults unchanged: `serial_check.py --base-python base-serial --new-python AIUE-61-serial --base-omp-python base-omp --new-omp-python AIUE-61-omp --jobs 4` (all 42 cases, both pairs) | `RESULT: AGREE (bitwise identical; complete gate)` |
| **G2** | K=20 determinism, jac arm, 4 threads, one evaluation: `check --preset tebox` and `--preset full`, `--repeats 20` | all 20 runs deterministic in both presets |
| **G3** | Thread identity: `check --preset full` and `--preset tebox`, jac arm, K=3 at **1, 2, 3, 4, 8** threads; `compare` run0 of each thread count against 4 threads | AGREE for every pair, and each group deterministic |
| **G4** | Newton path: `check --itermx 3`, full and tebox, jac arm, 4 threads K=5; plus 2 and 8 threads K=1 each, compared with 4 threads | deterministic; thread pairs AGREE |
| **G5** | `flow --all` (all 8 configurations, 2/4/8 threads, K=2, both arms, `--max-jobs 2 --cores 8 --gate none`), plus `compare` of jac run0 at 2 vs 4 vs 8 threads per configuration | jac arm: "deterministic: yes" in **every** group and every thread pair AGREE. jacrhs: report only |
| **G6** | AIUE-56 C1 gate on every one-evaluation jac run of G2, G3, G5 | `GATE PASS` everywhere (magnitude ≤ 10× serial Te-row max; deviation ≤ 1e-6 × serial row max) |
| **G7** | Cost (`AIUE-61-timing.py`): full problem, one Jacobian (`com.ttjstor`) and `exmain` wall; NEW (AIUE-61-omp default) vs OLD (AIUE-56-omp default) vs LEG (AIUE-61-omp, `OMPJacFixedChunks=0`), at 2, 4, 8 threads, **≥ 5 repeats each, one shuffled interleaved order, one process at a time** | median NEW/OLD `ttjstor` ≤ **1.10** at 2, 4 and 8 threads (the ticket's "within about 10 %"). Report median, min–max and every sample. A ratio within 1.10 but with overlapping spreads is reported as "within noise" |
| **G8** | Heap fix (NC3 below) and legacy path unchanged (NC4) | as stated there |
| **G9** | `validate` skill: branch hygiene + drift check clean, serial build + smoke, D_only with the serial build, **D_only pytests with the OpenMP build** (switches at the decks' defaults), OpenMP check (step 4) on the D_only default case with `OMPParallelPandf1=1, OMPParallelJac=1, Nthreads=4, CheckPandf1=1, CheckJac=1` | D_only passes in both builds; the OpenMP check reports no difference. If `CheckJac` reports a round-off difference (its tolerance is an absolute 1e-14, `ppp/parallel.F90:120`), run the same check on `AIUE-56-omp`: the same kind of difference there → ⚠️ pre-existing (C2), reported verbatim; a new kind → ❌ |

### Negative and positive controls (each must behave as stated, or the gate that relies on it is void)
| ID | Run | Expected |
|---|---|---|
| NC1 | AIUE-61-omp, `OMPJacChunkReset=0`, full, jac, 2 and 4 threads, K=2 | thread pair **MISMATCH** (P2-neg). This shows G3 can detect thread dependence |
| NC2 | AIUE-61-omp, `OMPJacFixedChunks=0` (legacy), full, jac, 8 threads, K=5 | **not deterministic** (the study saw 5 distinct hashes in 5 runs). This shows G2 can detect run-to-run variation. A deterministic K=5 outcome is reported as "control inconclusive", not as a pass |
| NC3 | full, jac, 4 threads, `OMPJacNchunks=16, OMPAutoBalance=0`, no `ulimit`: AIUE-56-omp vs AIUE-61-omp (`OMPJacFixedChunks=0`) | AIUE-56: crash (signal, no record); AIUE-61: completes and passes the C1 gate |
| NC4 | jac arm, **1 thread**, full and tebox: AIUE-56-omp (default) vs AIUE-61-omp `OMPJacFixedChunks=0` | bitwise AGREE: with 1 thread both run the legacy path in the same column order, so the heap fix changes no value |
| C-isjr | AIUE-61-omp, full, jac, 4 threads, `bbb.isjacreset=0` vs default | AGREE (isjacreset doesn't change the Jacobian); its time is reported (the size of the optional saving) |
| C-ser | Every `check` includes a serial reference of the same build | for the report: mismatch count, rows, worst deviation vs serial per configuration (expected on macOS: Te rows only, ≤ 4.6e-9 × row max) |

### Reported, not gated
- **R1 Deviation from serial** per configuration and thread count (G2–G5 records): entries, rows by equation (via
  the harness localisation), worst ratio, compared with the AIUE-56 build's numbers (`AIUE-56-validation.txt`).
- **R2 `dtreal=1e-9` scenario** (`AIUE-61-conv_worker.py`: deck, `full`, jac arm, `dtreal=1e-9`, 5 × `exmain`,
  Jacobian recomputed each step): NEW at 4 threads K=2, at 2 and 8 threads K=1. **Expected:** identical per-step
  `iterm`/`fnrm` and a bitwise-equal final state in all four runs. If that
  expectation doesn't hold, it counts as a G3 FAIL. Whether step 1 converges is reported, not gated. **Pre-registered expectation from P5: step 1 fails (`iterm=4`) in all four runs, with identical `fnrm`** (see Q3). The serial build converges
  (21, 4, 3, 4, 3 iterations), serial with `-ffp-contract=off` does not, and the old default converged in 3 of 5.
- **R3 jacrhs arm** (G5): determinism and agreement per group, compared with the AIUE-56 build. Any regression → AIUE-58.
- **R4 Sensitivity:** `OMPJacNchunksFixed` 32 and 128 at 4 and 8 threads, 3 interleaved repeats each (cost and deviation
  only), and the Te box `ttjstor` with and without the reset (P4) — for the owner's Q2/Q5.
- **R5 Linux x86-64 (if feasible):** AIUE-62's Docker setup (`tests/deterministic_omp/linux/README.md` on the AIUE-62 branch;
  Debian image, `LDFLAGS=-fopenmp`, `--cpus 5`, **one container at a time**, coordinated with the AIUE-64 agent).
  Build this branch; `check` tebox and full jac at 4 threads K=5, full jac at 2 and 8 threads K=2, `up` jac at 4 and 8
  threads K=5 (M3, AIUE-65), and thread-pair compares. **Expected:** tebox and full bitwise equal to serial and deterministic
  (no C2 on x86-64, so the fresh chunk start produces serial's values). M3: the `up` rows at the inner plate either
  disappear (as with fixed chunks in `ctl_fix_up_t8_static_k5`) or appear deterministically at every thread count.
  If R5 runs, a determinism or thread-identity failure there counts as a G2/G3 FAIL. If it can't run, the PR says
  "Linux not run" and the first green AIUE-57 CI run is the check.

### Run order and estimate
Build both venvs (≈ 10 min) → G1 (≈ 35 min, `--jobs 4`) → NC3, NC4, C-isjr (≈ 10 min) → G2 (full K=20 at 4 threads ≈ 25 min;
tebox ≈ 2 min) → G3 + NC1 + NC2 (≈ 30 min) → G4 (≈ 25 min) → G5 (≈ 60–90 min) → G6 (script, minutes) → G7 (45 runs ≈ 35 min,
alone) + R4 → R2 (≈ 30 min) → G9 (≈ 20 min) → R5 (≈ 60 min, if Docker is free).

## AI-layer facts affected
- `.claude/context/openmp-jacobian.md`: the Jacobian bullet (new default, reset, legacy switch, no per-thread copies)
  and the moved `ppp/omp_parallel.F90` line refs (`:645`, `:721`, `:908` are cited there; the edits shift `:908`).
  Checked: `.claude/context/mppl-fortran.md:69` cites `ppp/omp_parallel.F90:908-936` (OMPPandf1Rhs), so `--fix` that line
  too. `architecture.md` (`ppp` row: file list unchanged), `CLAUDE.md`, `testing.md`: no change (no new file or build step).

## Acceptance criteria (Jira AIUE-61, mapped)
- [ ] AIUE-53 serial check AGREE, both builds, complete gate (G1)
- [ ] K=20 bitwise-identical runs, Te box and full, 4 threads (G2); the same Jacobian at 2/4/8 threads (G3; 1 and 3 as
      extra); `flow --all` deterministic in every configuration (G5); also over 3 Newton iterations (G4)
- [ ] AIUE-56 C1 gate PASS; deviation from serial reported (G6, R1)
- [ ] Cost vs the old default, interleaved at 2/4/8 threads, within about 10 % (G7)
- [ ] Effect on M3 (R5) and on the `dtreal=1e-9` scenario (R2) reported
- [ ] Heap fix: `OMPJacNchunks≠0` no longer crashes (NC3); legacy behaviour available and documented (`OMPJacFixedChunks=0`, NC4)
- [ ] New variables visible from Python with `[none]` units and descriptions (task 1)
- [ ] `openmp-jacobian.md` updated; drift check clean (task 5)
- [ ] PR states the OpenMP-build default change (decision 9, owner-approved exception) and D1's resolution

## Open questions for the owner
- **Q1 (D1, blocking):** accept the per-chunk reset plus the dynamic schedule instead of literal `schedule(static,1)`?
  The evidence is P1, P2 and P2-neg. Without the reset, the thread-identity criterion fails at 64 chunks. With it, static and
  dynamic give the same Jacobian, and dynamic is cheaper.
- **Q2:** default `OMPJacNchunksFixed` = 64. With the dynamic schedule this is about 8 chunks per thread at 8 threads (the study:
  −4 % vs the old default at 8 threads, before the reset's ≈ 3–4 %). At 16 or more threads users should raise it; any
  change of the count changes the Jacobian at round-off. 128 halves the load-balance risk and doubles the reset cost
  and the number of chunk-start mismatches (R4 measures it).
- **Q3:** with the new default, the `dtreal=1e-9` hard first step of the reproducer deck fails **every time** (P5: 64 and 128 chunks, 2 of 2 configurations), where serial converges and the old default converged in 3 of 5. This is the decision-9 caveat measured on the production design. "Reproducible" here means "reproducibly failing" on this deck (`rundt` would cut the step and retry). It is not a defect of the partition: the trajectory is sensitive at round-off, and an equally valid serial build (`-ffp-contract=off`) fails too. The plan does **not** tune the chunk count to pass this one case. Confirm that this is acceptable for the default.
- **Q4:** `isjacreset` stays (it costs about 5 % in both modes, and the serial loop doesn't do it) — confirm, or open a separate ticket.
- **Q5:** small problems (e.g. the 25-equation Te box on the full grid): the reset dominates the cost (0.22–0.35 s vs 0.06 s per
  Jacobian), small in absolute terms. Accept, or add a minimum chunk length (another input)?
- **Q6:** optional: one full `pandf` per thread after the loop would make the RHS arm's worker state independent of the
  Jacobian schedule (about 23 ms per Jacobian). Not in scope unless the owner wants it here rather than in AIUE-58.

## Notes
- Rejected: literal `static,1` without a reset (P1 thread dependence); one chunk per thread (+70–108 %, study); replay (E,
  +27–98 %, study); the `schedule(runtime)` + `omp_set_schedule` route (crashed in the study's build, and is not needed).
- Scratch artefacts to remove after the ticket: `uedge-wt/AIUE-61-probe`, `venvs/AIUE-61-probe`,
  `uedge-wt/scratch-AIUE-61` (all created by this ticket's planning; nothing in them is committed).
