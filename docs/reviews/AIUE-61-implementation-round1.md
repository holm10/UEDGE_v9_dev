# AIUE-61 implementation review, round 1 (preliminary evidence on the AIUE-56 base)

Reviewer: uedge-reviewer (independent). Branch `bugfix/v9-AIUE-61-omp-static-partition` at `1701d31`, base AIUE-56
`1553e75`. Reference: the approved plan `.claude/plans/AIUE-61-omp-static-partition.md` (round 2 APPROVE) and the
Jira AIUE-61 acceptance criteria it maps. Scope of this round: the product code (`155e562`), the code facts (`a00a63a`),
the tools, and the preliminary gates. The final gates on the AIUE-60-combined tree, G7, R2, R4 and R5 are pending
and are not counted against the work. I checked that their plan is sound.

## Verdict

**REVISE.** There are no BLOCKERs. The code is correct and matches the plan, and the preliminary evidence reproduces.
Two MAJOR findings concern the reference and the record, not the code: (1) G9a is recorded as `PASS*` even though its
pre-registered criterion failed; (2) the plan's premise about AIUE-60 and its combined-tree G0b expectation are now
out of date because of AIUE-60 amendment 1. Both can be fixed with text before the round-2 run.

## Summary

The implementation follows the plan line for line:
- the fixed split `min(OMPJacNchunksFixed, max(1, neq/OMPJacMinChunkLen))` with integer boundaries;
- a fresh `pandf(-1,-1)` before each chunk's first column, on the unperturbed `ylcopy` in Jacobian mode, into
  `LocalJacBuilder`'s own `wk`;
- no load weights in fixed mode, and per-chunk `OMPTimeLocalJac(ichunk)`;
- the heap fix, which writes straight into `iJacCol(:,ichunk)`/`rJacElem(:,ichunk)`;
- a legacy path whose only change is that heap fix.

I recomputed from the stored records, independently of the harness:
- the G2/G3 Jacobian hashes: 20/20 identical, and identical at 1/2/3/4/8 threads and with `OMPLoopJacNchunk=3`;
- NC1, NC2 and NC4;
- the full-problem deviation from serial (12 275 entries, 2914/9340/21, 78 Te rows, worst 4.59e-9);
- the te_phi flow deviation (1364 entries, worst 7.15e-9);
- the build provenance (venv extension hashes equal the run records and the G1 summary; the frozen trees are clean
  at `155e562`).

My own two runs used a partition the author never ran: 5 chunks with uneven boundaries, 3 threads, against 4 threads
with `OMPLoopJacNchunk=2` and one idle thread. They agree bitwise. Their deviation from serial is 1114 entries in 19
Te rows, worst 1.42e-9, which is consistent with C2 (fewer chunk starts give fewer deviating rows).

The design does not depend on the `com` timers being threadprivate, but the plan's combined-tree expectations must
be restated (I1-M2).

## Findings

### MAJOR

**I1-M1. G9a is recorded as "PASS\*" although its pre-registered criterion failed. The owner decision that would
justify this is not cited in the plan or the record.**
- **Where:** `docs/reviews/AIUE-61-validation.txt`, line "G9a PASS\*"; the plan's G9a row ("all pass; `CheckPandf1`
  reports no difference").
- **What is wrong:** `CheckPandf1=1` stops with `RuntimeError diff in rhsnk` at iv 76 and 132.
- **Evidence:** I checked `scratch-AIUE-61/prelim/g9a/ompcheck_AIUE-6{1,56}-omp_pandf1/`. Both builds print the same
  two lines (`76 2032.0288514119870 2032.0288330644739 9.03e-9`, `132 -48175.314616658346 -48175.314617835662
  2.44e-11`), so the failure is pre-existing. The owner decision that moves RHS work to epic AIUE-70 exists:
  `AIUE-8-planning/docs/specs/AIUE-8-progress.md:208-212`, "15:35 Owner decisions (2)". Neither the plan nor the
  record cites it. The plan still makes "no difference" a PASS condition, so the round-2 G9a fails by the plan's own
  terms.
- **Resolve:** amend the plan's G9a row so that the `CheckPandf1` part is report-only, citing the owner decision and
  its source. Record G9a as PASS on the remaining parts, with the `CheckPandf1` output quoted verbatim for both
  builds. Alternatively, record it as "FAIL, pre-existing, accepted by the owner (source)". It must not be "PASS\*"
  under an unchanged criterion.
- **Note:** this D_only case has neq 420, so the new default runs it as one chunk. The OpenMP check on D_only
  therefore doesn't exercise multi-chunk fixed mode. G9b with `OMPJacMinChunkLen=1` covers that, and I accept it.

**I1-M2. The plan's AIUE-60 premise and the combined-tree G0b expectation are out of date (AIUE-60 amendment 1,
`cb05472`).**
- **Where:** plan lines 32-33 ("It makes `areapl`, `TimingPandfOn` and the `com` timers threadprivate") and 137-138
  ("Part A, made safe by AIUE-60: … the `com` timers"). Also the G0b row ("on the combined tree: of whatever AIUE-60's
  final version leaves non-threadprivate; `203a5ff` expects Probe S shared writes 161 → 147").
- **What changed:** AIUE-60 amendment 1 (`AIUE-60:cb05472`, after AIUE-60 implementation review I1-B1) removes
  `+threadprivate` from every `com`/`aph` scalar. The timers stay shared and are updated atomically through a new
  `acctim`. `iflag_aph` becomes a local. The amendment adds a static common-block gate and a G-iotable probe.
- **Does AIUE-61 depend on the timers being threadprivate? No.** The timers are output only:
  - `ttimpfe`/`ttimpjf` are read only in prints (`bbb/odesolve.m:985,988`) and the debug dump
    (`ppp/debug_parallel.F90:716-729`);
  - `totintrv` is read only in a print (`com/comutil.m:42`).
  - Nothing in the RHS or the Jacobian reads them, and the AIUE-56-base gates passed with them shared and racing.
- **What must change for the combined-tree run:**
  1. **G0b expected set (pre-register it explicitly):**
     - `bbb.areapl` and `bbb.TimingPandfOn` leave the scan (threadprivate after AIUE-60).
     - The seven timers a full `pandf` writes (`com.totintrv, ttimpfe, ttngfd2, ttngfxy, ttngxlog, ttngylog, ttnpg`)
       stay WRITTEN. They are allowed because they are atomic and output only.
     - `com.nfsp` still shows as WRITTEN under the sentinel method. AIUE-60's "write only when it changes" fires
       because the sentinel differs from `nisp`. This is an artefact of the method, not a race.
     - So the expected WRITTEN set is exactly those 8 names. The "161 → 147" count refers to Probe S, not to G0b, and
       should not be the G0b expectation.
  2. Correct the two premise sentences above. Under amendment 1, "made safe by AIUE-60" means: threadprivate for
     `areapl`/`TimingPandfOn`, atomic for the timers, write-if-changed for `nfsp`.
  3. Correct the PR statement "the resets add time to the full-RHS timers". With atomic accumulation, worker resets
     add CPU time summed over threads, so `ttimpfe` and the others can exceed wall time.
  4. Because AIUE-61 edits `ppp/ppp.v`, run AIUE-60's static `/ompcommonscalarcopy/` gate and the G-iotable probe on
     the combined build, and record the definers. Today `nm` shows only `bbbpy` and `apipy` defining
     `_ompcommonscalarcopy_`; the record says to re-check, but the plan has no gate for it.
  5. Optional: say whether P2's hash and R2's pre-registered `get_fnrm` bits are expected to hold after AIUE-60's
     `sfscal(iv)`→`sfscal(ii)` clip change (`AIUE-60:ppp/parallel.F90:288,292`). With the default `jaccliplim=0`
     (`bbb/bbb.v:3308`) and a deck that doesn't set it, the clip test is `jacelem≠0` either way, so I expect them to
     hold. Pre-register that, so a change would be noticed rather than explained away afterwards.
- **Resolve:** a plan amendment covering points 1-4 (and 5 if adopted) before the final run.

### MINOR

**I1-m1. The Python-visible description of `OMPJacFixedChunks` claims more than the guarantee covers.**
- **Where:** `ppp/ppp.v:60-68`: "Holds where a full pandf resets all state, i.e. the paths the exmain OpenMP checks
  allow (ismcnon=0 and isimpon 0, 2, 6, 7 only)".
- **What is wrong:** `exmain` also allows `nxpt=2`, limiter sputtering, coupled walls and `istabon=5,6`. Those are
  the AIUE-60 B2/B4 and AIUE-69 shared-write paths that `openmp-jacobian.md` correctly calls "not validated". A user
  with a double-null case would read the `.v` text as a reproducibility guarantee.
- **Resolve (optional):** add "not validated for nxpt=2, limiter sputtering, coupled walls, istabon=5,6", or replace
  "i.e." with a pointer to the list in `openmp-jacobian.md`. The plan approved this wording, so this is a minor point.

**I1-m2. The verbose output in fixed mode prints stale load weights.**
- **Where:** `ppp/omp_parallel.F90:578-585`.
- **What is wrong:** with `OMPJacVerbose>0`, the per-chunk table prints `OMPLoadWeight(ichunk)`, which fixed mode
  never sets or uses. The output is cosmetic and misleading.
- **Resolve (optional):** print it only in legacy mode, or note in the table that it is unused in fixed mode.

## Status of previous findings

Round 1 of the implementation review; this section does not apply. The plan-review findings were closed in plan
round 2.

## Not independently verified (environment)

- **Pending, not counted against the work in this round:** the final gates on the AIUE-60-combined tree, G7 (cost),
  R2 (`dtreal=1e-9`), R4 (chunk-count sensitivity), and R5 (Linux x86-64). The plan for them is sound apart from
  I1-M2.
- **G1:** not re-run. I checked `prelim/g1.txt` (`RESULT: AGREE (bitwise identical; complete gate)`, 42 cases, both
  pairs). I also recomputed the serial-check extension hashes of the current venvs: `AIUE-61-omp` `ca1de3bd6704ba6c`
  and `AIUE-61-serial` `484d786df24d366b`, equal to the G1 summary. The frozen trees `uedge-wt/AIUE-61-omp` and
  `-serial` are at `155e562` with 0 dirty files.
- **G0a/G0b, NC3, NC5, G10/G10b (bounds-checked and no-`OMP_STACKSIZE` runs):** not re-run, because of the run
  budget. What I did check:
  - the G0b JSON: WRITTEN equals the 10 Part A names, `outside_probe_S` is empty, and `yl_neq_plus_1` = 1.0;
  - NC3: the old-build log (exit -11, no record) and the new-build record (`Updating OMP Jacobian [4|16]`, completes);
  - the NC5 and G10-static lines in the record.
- **Timing hints in the record:** not checked. They are not G7.

## What was checked and how

1. **Code against the plan** (`git diff 1553e75..HEAD -- ppp/`, and a full read of `InitOMPJac`, `jac_calc_omp`,
   `OMPJacBuilder`, `OMPFixedSplitIndex`, `OMPCollectJacobian` and `LocalJacBuilder`):
   - **Chunk count.** `NchunksJac=min(OMPJacNchunksFixed,max(1,neq/OMPJacMinChunkLen))` (`omp_parallel.F90:317`),
     with `xerrab` on non-positive inputs. The count does not depend on the team size.
   - **Split.** `ivmin(i)=((i-1)*neq)/N+1` and `ivmax(i)=(i*neq)/N`. The chunks are contiguous by construction: the
     next chunk starts one past where this one ends. Each is non-empty when N≤neq, which is guarded. The 8-byte
     default integers avoid overflow.
   - **Reset.** `pandf(-1,-1,neq,t,yl,wk)` runs before `loopiv` (`parallel.F90:214`):
     - `yl` is the thread's `firstprivate` `ylcopy`, copied from the caller's `yl` with `yl(neq+1)=1` set by the
       `jac_calc` callers (`bbb/oderhs.m:1716,1939,2325`);
     - `wk` is `LocalJacBuilder`'s automatic `wk(neq)`, and each column re-initialises `wk(ii1:ii2)` from `yldot00`;
     - `pandf` writes `yldot` only up to `neq`;
     - `ParallelPandfCall` (`bbb/bbb.v:4131`) is set only inside `OMPPandf1Rhs` (`omp_parallel.F90:990,1039`), so it
       is 0 here and the reset uses the full ranges.
   - **Fixed mode.** `jac_calc_omp` skips the weights and `OMPSplitIndex`. `OMPTimeLocalJac(ichunk)` is written only
     in fixed mode, and `(tid+1)` only in the legacy branch.
   - **Heap fix.** `iJacColCopy`/`rJacElemCopy` are removed, and the chunk's section `iJacCol(:,ichunk)` (a
     contiguous column of an explicit-shape dummy, so no temporary) is passed. `OMPCollectJacobian` reads only
     `1:nnz-1` (`:483-487`), so the dropped zero-init and the copy of element `nnzlocal` change no value.
   - **Legacy path.** It is identical apart from the heap fix: `ifresh=0`, and the same timing and print.
2. **Forthon:** the four new variables carry `[none]` and descriptions. I imported both venvs: `1 64 300 1`, and
   `getvardoc` shows the texts. No `+threadprivate` was added (`git diff 1553e75..HEAD -- '*.v'`). `nm` on every
   `.so` in `venvs/AIUE-61-omp`: `_ompcommonscalarcopy_` is defined only in `bbbpy` and `apipy`.
3. **Records recomputed** with my own scripts (`/tmp/rev61/npzhash.py`, `jdiff.py`; numpy over `record.npz`, not the
   harness compare):
   - **G2 full:** run0–19 have the same Jacobian hash `296cec993bd0349c`; serial is `a5475a735d95c20c`.
   - **G3:** `full` at t1/2/3/4/8 and sched3 give the same hash. `tebox1` at t1/2/8 gives `f2c08109…`. `tebox`
     (1 chunk) gives `ac52fa28…`, which equals serial. The run logs show `[T|64]`, `[8|25]` and `[8|1]`.
   - **NC1:** t2 run0 and run1, t4 run0 and run1 give 4 different hashes.
   - **NC2:** 5 distinct hashes.
   - **NC4:** AIUE-56 at 1 thread equals AIUE-61 legacy at 1 thread, which equals serial (full and tebox).
   - **G5 te_phi:** jac t2/t4/t8 and jacrhs t4 give one hash.
   - **Deviation from serial:**

     | Case | Entries | Value / only serial / only OpenMP | Rows | Worst × row max |
     |---|---|---|---|---|
     | `full` | 12 275 | 2914 / 9340 / 21 | 78 Te | 4.59e-9 |
     | te_phi | 1364 | | 75 | 7.15e-9 |

     Both are within the C1 bound of 1e-6.
   - **C2 consistency:** with `jaccliplim=0`, the "only serial" entries are exact zeros in the reset Jacobian where
     serial has history-dependent round-off. The deviation depends on the chunk starts, not on the threads (see
     item 4). One chunk is bitwise serial.
4. **My own runs (2, ≤ 4 threads)** with `venvs/AIUE-61-omp`, harness `run`, `env -i`, empty HOME, `full`,
   `OMPJacNchunksFixed=5` (boundaries 8870/8871):
   - 3 threads, default schedule;
   - 4 threads, `OMPLoopJacNchunk=2` (one thread idle).

   `cli.py compare`: **AGREE** (Jacobian, sfscal, suscal, yldot, RHS probe and fnrm all equal); nnz 3 189 542 in
   both. Against the record's serial: 1114 entries, 19 Te rows, worst 1.42e-9. Against the 64-chunk default: 11 161
   entries, so the chunk count changes the Jacobian at round-off, as the `.v` text says.
5. **AI layer:**
   - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` gives "OK", exit 0. The advisory
     re-read list comes from `origin/v9-develop` (`4faed39`) having moved past this branch's base; the rebase clears
     it.
   - `uv run .claude/hooks/change_kind.py --range 1553e75..HEAD` gives "OK" (`ticket`, product in `ppp/`, process
     files only `.claude/context/*` in `a00a63a` with the `AI-layer: code-facts` trailer).
   - The new `openmp-jacobian.md` references `ppp/omp_parallel.F90:317,501,656,660,733,784,948,999-1001`,
     `ppp/parallel.F90:214` and `ppp/ppp.v:41,60`. I checked each against the source.
   - The post-approval plan commit `e0769d3` only re-targets the AIUE-60 references (`d2fac6e`→`203a5ff`) and
     narrows Part B. I reviewed it here; it is superseded by I1-M2.
6. **AIUE-60 state:** `AIUE-60` at `cb05472` (amendment 1). `git diff 1553e75..HEAD` there touches
   `ppp/parallel.F90:288,292` (the clip index), `com/com.v`, `bbb/bbb.v`, `aph/aph.v` and `bbb/pandf.m`.
7. **Owner decision source for G9a:** `AIUE-8-planning/docs/specs/AIUE-8-progress.md:208-212`.
