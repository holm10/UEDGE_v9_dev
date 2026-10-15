# AIUE-61 plan review, round 1

Plan: `.claude/plans/AIUE-61-omp-static-partition.md` at `4dea642` (branch `bugfix/v9-AIUE-61-omp-static-partition`,
base `bugfix/v9-AIUE-56-omp-jacobian-fix` `1553e75`). Stage: plan. Reviewer: uedge-reviewer.

The coordinator relayed the owner's decisions after the review started. I reviewed against them: D1 approved (fixed
boundaries, a fresh full `pandf` at each chunk start, dynamic schedule); Q2 64 chunks by default, user-editable; Q3 a
deterministic non-converging `dtreal=1e-9` step is acceptable; Q4 `isjacreset` unchanged here (AIUE-68); Q5 **add a
minimum chunk length (problem-size-only rule)**; Q6 the post-Jacobian worker reset is out of scope (AIUE-58/AIUE-59).
They reached me through the coordinator, so I can't check that they are the owner's own words (see "Not independently
verified").

## Verdict

**REVISE**: 1 BLOCKER, 3 MAJOR, 6 MINOR.

## Summary

The design is sound and the evidence behind D1 holds up. I re-derived the thread-count dependence of plain
`schedule(static,1)` from the cost study's raw records, and the probe records confirm that the per-chunk reset gives
the same hash at 2, 3 and 4 threads. The heap fix and the legacy path are correct as planned, and every
`file:line` reference I checked is accurate. One problem blocks the plan. Because the chunk count no longer depends
on the thread count, the existing per-thread write `OMPTimeLocalJac(tid+1)` can run past its `NchunksJac`-sized
array. On a node with more than 64 hardware threads this happens under the new default. Once the owner's Q5 minimum
chunk length is in, it happens on any small problem, including the plan's own Te-box gates. The plan also doesn't
yet include Q5 at all. It states the "a full `pandf` erases the history" guarantee more broadly than it holds (it
fails for `ismcnon=4` and `isimpon=5`). And it widens the known shared-state races (AIUE-60) without saying what a
failure would mean for the gates.

## Findings

### BLOCKER

**L1-B1: `OMPTimeLocalJac(tid+1)` writes out of bounds when the team is larger than the chunk count**
(`ppp/omp_parallel.F90:740,744`, `ppp/ppp.v` `OMPTimeLocalJac(1:NchunksJac)`).
- What's wrong: the loop body writes `OMPTimeLocalJac(tid+1)`. The array has `NchunksJac` elements. Under
  `schedule(dynamic,…)` any thread of the team can take an iteration, so `tid+1` can reach the team size. The
  `parallel do` has no `num_threads` clause, and `InitOMPJac` calls `OMP_SET_NUM_THREADS(OMP_GET_MAX_THREADS())`
  (`:296`), so the team is `OMP_NUM_THREADS`, or every hardware thread if that isn't set. `ppp.Nthreads` doesn't limit
  it. Today's default has `NchunksJac = neq`, which is always larger than the team, so it's safe. The plan makes
  `NchunksJac = min(64, neq)` the default:
  - On a host with more than 64 hardware threads and no `OMP_NUM_THREADS` (for example a 128-core CPU node), every
    OpenMP Jacobian writes past the array, which corrupts the heap.
  - With the owner's Q5 decision, small problems get only a few chunks. If the Te box (`neq` 25) gets 1 chunk, then
    G2 and G3 on the Te box at 2–8 threads write `OMPTimeLocalJac(2..8)` into a 1-element array.
- Also: the array is written per thread but read per chunk (`OMPTimeLocalJac(i)`, `i=1..NchunksJac`, in the
  auto-balance block at `:553-556`). That inconsistency already exists, and it stays harmless only while legacy mode
  isn't touched.
- To resolve: in fixed mode, don't index anything by `tid` against a `NchunksJac`-sized array. Index by `ichunk`, or
  skip the write; the weights aren't used in that mode. Leave the legacy path unchanged so NC4 stays bitwise. Add a
  validation run with fewer chunks than threads (for example the Te box with `NchunksJac` at most 2 at 4 threads) in a
  `--checkbounds` or `--debug` build, so that an out-of-bounds write fails a gate.

### MAJOR

**L1-M1: The owner's Q5 decision (a minimum chunk length) isn't in the plan, and it changes the gates.**
- What's wrong: tasks 1–2 compute `NchunksJac = min(OMPJacNchunksFixed, neq)` only. Q5 needs four things:
  - a rule that depends only on problem size, for example `N = min(OMPJacNchunksFixed, max(1, neq / OMPJacMinChunkLen))`
    with integer division;
  - a new `[none]` input in `.v` with its description;
  - the `InitOMPJac` change, which must still be independent of the thread count;
  - an update to `openmp-jacobian.md`.
- Q5 also weakens the existing gates. If the Te box drops to 1 chunk, its G2, G3 and NC1 runs no longer test
  chunk-start behaviour at all: one thread builds everything. The P2/P5 evidence (`8761cd9e…`, the R2 pre-registered
  `fnrm` bits) applies only if the full problem keeps exactly 64 chunks, so the default must be at most 693
  (= 44352/64).
- The "Open questions" section still lists Q1–Q6 as open. They should be recorded as decided, with the source.
- To resolve:
  - Specify the rule, its default (with the reason; P4 gives about 0.77 ms per column against 23 ms per reset, so
    about 300 columns per chunk keeps the reset under about 10 %) and its `.v` text.
  - State that the full problem stays at 64 chunks.
  - Add a Te-box run with the minimum overridden (for example 1) to keep multi-chunk coverage on the small case, and a
    gate showing that the chunk count is the same at every thread count when `neq` is below the minimum length.
  - Record Q1–Q6 as decided.

**L1-M2: The "a full `pandf` erases the history" guarantee is stated more broadly than the evidence and the code
support** (plan P3, task 1 `.v` text, task 5's `openmp-jacobian.md` rule).
- What's wrong: the `.v` description and the code-facts entry will say "bitwise reproducible and the same for any
  Nthreads" with no conditions. Two code paths break the premise that a full `pandf` in Jacobian mode is a pure
  function of `yl`:
  - **`ismcnon=4`**: `initialize_ismcnon` (`bbb/pandf_plasma_continuity.m:124-133`, called at `bbb/pandf.m:570`)
    multiplies `parvis` and `travis` by `pnc_cf*` whenever `yl(neq+1)>0`, and those inputs are never recomputed.
    Only `jacobian_reset` divides them back (`bbb/pandf_jacobian.m:124-133`), and it runs only for local calls
    (`bbb/pandf.m:710`). Each reset (`yl(neq+1)=1`) therefore compounds `parvis` by a further factor of
    `pnc_cfparvis`. That is 64 more factors per Jacobian, on arrays that aren't threadprivate (`bbb/bbb.v:1327-1328`),
    so the writes race as well. The worker state then depends on how many chunks each thread ran: on the schedule and
    the thread count. (The master's existing pre-loop full `pandf` already compounds once, so this was broken before,
    but the reset makes it much worse.)
  - **`isimpon=5`**: `fmombal` has `save`d local arrays (`api/fmombal.m:70,368,1064`). They are static, shared by all
    threads, and keep state between calls (RCA H3).
- The P3 evidence is also narrower than the plan says:
  - only one region (12001–15000) snapshotted all 9 packages; the other three regions snapshotted `bbb`, `com` and
    `api` only (`scratch-AIUE-61/reset1`, `reset2`);
  - it ran in the serial build, on one deck;
  - it used whatever `yl(neq+1)` held after `exmain` (the probe script never sets it), not Jacobian mode (`=1`), which
    the RCA found mattered for its shared-state scan;
  - it can't see `save`d locals or F90 module state.
- To resolve:
  - Either fall back to the legacy path or call `xerrab` for the known exceptions (`ismcnon=4`, `isimpon=5`) in fixed
    mode, or document them in `.v` and `openmp-jacobian.md` as excluded from the guarantee.
  - State the validated scope (the `flow --all` configurations).
  - Re-run P3 in phase 2 with `yl(neq+1)=1` and all packages in every region (it costs minutes).

**L1-M3: The per-chunk resets widen the known shared-state races, and the gate outcome for them is undefined**
(plan "Deliberate choices", F16 bullet).
- What's wrong: until now, workers in the Jacobian arm never ran a full `pandf`. With the reset, up to T threads run
  full-grid evaluations at the same time as other threads' local ones. Those evaluations write the non-threadprivate
  `areapl` (written and then read on the next statement, `bbb/pandf_boundary.m:3091-3095,3166-3179,…`),
  `TimingPandfOn`, the `com` timers and `nfsp`, which is exactly the AIUE-60 list. RCA F8, the evidence that no other
  shared variable is written, covered **local** `pandf` calls only. The `jacrhs` arm's `OMPPandf` (`xc=-1` on
  sub-ranges) is a partial precedent, not a scan.
- The plan says a plate-row failure "is reported as a probable F16 effect … not masked". It doesn't say whether G2
  and G3 then FAIL, or how AIUE-61 is ordered against AIUE-60 (plan `d2fac6e`, which makes `areapl`, `TimingPandfOn`
  and the timers threadprivate).
- To resolve:
  - State that any determinism or thread-identity failure is a FAIL whatever its cause.
  - Name the merge order. Either AIUE-61 rebases onto AIUE-60 before its final G2, G3 and G5, or the PR states that
    the reproducibility claim is unproven until it has been validated together with AIUE-60.
  - List which non-threadprivate variables a full `pandf(-1,-1)` writes: the sentinel mode of
    `scan_shared_state.py` on one full evaluation, or AIUE-60's results if they cover it.

### MINOR

**L1-m1: Factual slips in the probe description.**
- P3 says "`jacobian_store_*` writes the scratch at the start of each local `pandf`". Six of the scratch scalars are
  written somewhere else: `erlizold`, `erlrcold`, `eeliold`, `pradold`, `pwrebkgold` and `pwribkgold`, inside the
  energy loops (`bbb/pandf_plasma_energy.m:574-575,597,771,909,927`).
  - They are written from the box's last cell. `jacobian_reset` (`bbb/pandf_jacobian.m:87-93`) then writes those
    values into `(xc,yc)`. That is a restore of the wrong cell, which already exists and is itself a history carrier;
    the full reset rewrites it.
  - `pradold` is written only when `isimpon≥2`.
  - The conclusion (no history across calls) still holds for the deck tested.
- "Every variable of 9 packages … in 4 regions": see L1-M2.
- Fix the text.

**L1-m2: G7 can't resolve 1.10 at 8 threads with 5 repeats.**
- The study's own 8-thread data: within one batch the old default ran 5.20–6.55 s and 5.31–6.34 s, and its medians
  in the two batches were 5.40 and 5.93 s (a 10 % shift).
- Pre-register:
  - at least 9 repeats at 8 threads;
  - an exclusion or rerun rule based on the recorded load average;
  - what "within noise" means for PASS or FAIL. As written, a ratio of 1.12 with overlapping spreads is a FAIL that
    is labelled as noise.
- Optional secondary measure: the mean `ttjstor` per Jacobian from multi-Jacobian runs, which is tighter (see
  `multi_summary.txt`).

**L1-m3: No direct check that the result doesn't depend on the schedule, the central D1 claim.**
- Add a positive control: new default, full problem, 4 threads, `OMPLoopJacNchunk=1` vs `3`. It must AGREE.
- It costs about 2 runs. It also covers what the owner gave up by not taking `static,1`.

**L1-m4: The G9 `CheckJac` rule misclassifies the expected outcome.**
- The new default differs from serial deterministically at chunk starts (C2). The old default at ≤4 threads often
  equals serial bitwise: in the study, 9 of 10 runs of D at T=4 gave serial's hash, and so did P2's `full_D_t4`.
- So "the same kind of difference on AIUE-56 → pre-existing" will usually find no difference on AIUE-56, which by the
  plan's rule makes the result ❌.
- `CheckJac` uses an absolute tolerance of `1e-14` and stops with `xerrab`.
- Pre-register the accepted case: differences within the C1-gate bounds, in the expected rows, reported verbatim.

**L1-m5: The `.v` and documentation wording.**
- "the same for any Nthreads": `Nthreads` doesn't set the team size (L1-B1). Write "any number of OpenMP threads
  (`OMP_NUM_THREADS`)".
- Also say that `OMPJacFixedChunks` and `OMPJacNchunksFixed` take effect at the next `exmain`/`allocate`, because
  `InitOMPJac` runs from `allocate` (`bbb/odesetup.m:369`, `:6649`).
  - Changing `OMPJacFixedChunks` without re-allocating gives a mixture of the two modes. Fixed mode with
    `NchunksJac=neq` means 44 352 resets, about 17 min per Jacobian.
  - Optional: `jac_calc_omp` calls `xerrab` if the mode differs from the one `InitOMPJac` saw.
- The PR should mention that the resets add to the full-RHS timers (`ttimpfe`, `ttnpg`, `TotTimePandf`, …).

**L1-m6: The worker stack is never tested at the default `OMP_STACKSIZE`.**
- Every harness run sets `OMP_STACKSIZE=512M`. With the reset, workers now run full evaluations, and the
  `Makefile.Forthon` flags include `-Ofast`, which implies `-fstack-arrays`.
- Add one full-problem run with the new default and `OMP_STACKSIZE` unset, as a typical user would run it, or state
  that `OMP_STACKSIZE` is required.

## D1 assessment, for the owner (already approved; the record supports the decision)

- **The thread-count dependence is real.**
  - Raw records: `…/2129e705…/scratchpad/cost/single*/r*_*/timing.json`, tabulated with my own script. With uniform
    boundaries (`OMPAutoBalance=0`, weights 1, 44352/64 = 693 columns), `static,1` with 64 chunks gives
    `217b791b` at 4 threads (`F16s`, 5 of 5 runs) and `8761cd9e` at 8 threads (`F8s`, 5 of 5 runs).
  - With fewer chunks the result doesn't depend on the thread count: 8 chunks give `21b2ae5b` at 2, 4 and 8 threads,
    16 chunks `14b92dd6` at 2, 4 and 8, and 32 chunks `8c88ffe3` at 4 and 8.
  - Under `static,1`, thread t runs chunks t, t+T, …, so chunk k starts from the end state of chunk k−T. This fits a
    column-history reach between 2079 and 4158 columns. The reach is an inference, but the conclusion doesn't depend
    on it.
- **The reset is sufficient within the validated scope.** P2 (records `scratch-AIUE-61/b1/*/jrun.json`) gives
  `8761cd9e` at 2, 3 and 4 threads. That is the same hash as `static,1` without a reset at 8 threads, where no chunk
  sees nearby history. Without the reset, 2 and 4 threads differ (`48d3f455` vs `6ece2e5a`). The limits are L1-M2
  (`ismcnon=4`, `isimpon=5`) and L1-M3 (shared-state races).
- **Literal `static,1` with the reset gives the same Jacobian as dynamic with the reset.** So the choice is about
  speed and diagnostics only.
  - The study measured `static,1` at +24 % and dynamic at −4 % at 8 threads. Each figure is against its own batch's
    old default, and neither run had the reset.
  - `static,1`'s one real advantage: at a fixed thread count, the worker state after the Jacobian is deterministic.
    That would help the `jacrhs` arm (AIUE-58), but the Q6 post-Jacobian reset fixes it fully, at every thread count.
- **A trade-off worth stating in the PR.** On macOS at ≤4 threads, the old default often equals serial bitwise. The
  new one always differs in the C2 rows.

## Recommendations on Q2–Q6 (the owner has decided them; these are notes for carrying them out)

- **Q2 (64 chunks):** agree. Document that at 32 threads or more the dynamic load balance gets thin (2 chunks per
  thread at 32), and that changing the count changes the Jacobian at round-off.
- **Q3:** agree. Keep R2's pre-registered bits. An R2 result that is non-deterministic or depends on the thread count
  stays a G3 FAIL, as the plan says.
- **Q4:** agree (AIUE-68). Keep the C-isjr control.
- **Q5:** use a rule based on `neq`. The reset cost actually scales with the number of grid cells, not with `neq`
  (the Te box has a full grid and `neq` 25), but either is a problem-size rule. Pick the default so that the full
  problem stays at 64 chunks. It depends on L1-B1.
- **Q6:** agree that it's out of scope. R3 (the `jacrhs` arm) is confounded by AIUE-58 R1 (the `hcyn` range bug at
  chunk edges in the RHS path). Report R3 against that, not against AIUE-61.

## Dependencies on AIUE-58/60 findings (requested check)

- **AIUE-58 R1 (`hcyn` chunk-edge range):** the reset calls `pandf(-1,-1)` with `ParallelPandfCall=0` over the full
  ranges (`bbb/pandf.m` `initialize_ranges`), so the Jacobian design doesn't depend on R1. It affects only R3.
- **AIUE-58 R3 (the dangling `emcoef` from `copyin`):** the plan keeps `copyin(yinc,xlinc,xrinc,emcoef)` unchanged.
  Inside the region, `copyin` re-associates the pointer, and the reset only reads `emcoef`, so nothing new depends on
  it. The use-after-free risk in `OmpCopyPointeremcoef` before the next region already exists.
- **AIUE-60:** see L1-M3. The reset is the change that makes `areapl` and the timers writable concurrently over the
  whole grid.

## Status of previous findings

Round 1: none.

## Not independently verified (environment)

- I made no builds and no UEDGE runs (the budget was read-only). P2, P4 and P5 are accepted as recorded in the
  scratch `jrun.json` files and the cost-study records. I re-read them but didn't reproduce them. Phase 2 reproduces
  them (G3, R2).
- I couldn't check Jira AIUE-61's text (no Atlassian access). The plan's quotation of the scope was taken as given.
- The owner decisions Q1–Q6 reached me from the coordinator. They are not recorded as the owner's in any file I could
  read.
- Linux x86-64 behaviour (R5).
- The claim that Forthon passes `-fdefault-integer-8`/`-DISZ=8` was checked in the probe build log only, not in a
  fresh build.

## What was checked and how

- The plan, read in full. Line references spot-checked with `sed -n` on `ppp/omp_parallel.F90` (281, 305, 312, 320,
  477-482, 495, 509-510, 545-563, 645-647, 672, 675, 706-707, 718-721, 729-735, 747, 754, 759, 766-771, 813, 908),
  `ppp/parallel.F90` (159-160, 185, 195, 210-211, 236-238, 320-338), `ppp/ppp.v:18-56`, `bbb/bbb.v:951,3305`,
  `bbb/oderhs.m:1090-1235`, `.claude/context/mppl-fortran.md:69`. All accurate.
- Cost-study hashes: a Python script over
  `/private/tmp/claude-501/…/2129e705…/scratchpad/cost/{single,single2,multi,multi2}/r*_*_t*/timing.json`, with the
  configurations decoded from `batch.py` (`F<k>s` = k·T chunks, `OMPJacSchedule=2`, `OMPAutoBalance=0`).
- Probe records: `scratch-AIUE-61/b1/*/jrun.json` (P2, P2-neg, timings) and `reset1`/`reset2/reset_probe.json`
  together with `reset_probe*.py` (P3's regions, packages and leftover variables).
- The probe diff (`git -C uedge-wt/AIUE-61-probe diff`) compared with the plan's tasks.
- Code paths: `OMPSplitIndex` with uniform weights (integer `neq/N`); `nnzmxperchunk` (total storage unchanged);
  `OMPCollectJacobian` reads only `1:nnz-1`; the heap-fix section `iJacCol(:,ichunk)` is contiguous; `InitOMPJac` runs
  at every `exmain` (`odesetup.m:6649` → `allocate` → `:369`); no `num_threads` clause; `OMPTimeLocalJac` indexing;
  `jacobian_store`/`jacobian_reset` and the scratch writes in the energy loops; `initialize_ismcnon` for `ismcnon=4`;
  `fmombal` `save`; the `areapl` sites; `add_timestep` writes only `yldot`; `OMPPandf1Rhs`/`OMPPandf` (`xc=-1` on
  sub-ranges); `CheckJac` uses `1e-14` and `xerrab`.
- Harness: `cli.py` options (`--ppp`, `--repeats`, `--itermx`, `flow --all --max-jobs --cores --gate`), `worker.py`
  (ppp set after the deck, before `exmain`), `runner.py` (`OMP_NUM_THREADS`, `OMP_STACKSIZE`). Pinned tool commits
  `8ee189d` and `15ae327` exist; `docs/reviews/AIUE-56-c1-gate.py` exists at `1553e75`.
- Plan commit scope: `git diff --stat 1553e75 4dea642` shows the plan file only, so no process files are on the
  ticket branch.
