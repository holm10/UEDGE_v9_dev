# AIUE-61 implementation review, round 2 (final evidence on the AIUE-60-combined tree)

Reviewer: uedge-reviewer (independent). Branch `bugfix/v9-AIUE-61-omp-static-partition`, tip `4c3d095`, product at
`b717734`, rebased onto AIUE-60's approved tip `f8db593`. Reference: the approved plan
`.claude/plans/AIUE-61-omp-static-partition.md` (amended after round 1) and the Jira AIUE-61 acceptance criteria it
maps. Inputs: round-1 report and response, the FINAL section of `docs/reviews/AIUE-61-validation.txt`, and the run
outputs in `uedge-wt/scratch-AIUE-61/final/`.

## Verdict

**REVISE.** There are no BLOCKERs. The rebase is clean, the product code is the code I approved in substance in
round 1, and every gate in the final record reproduces from the stored data: G0b, G1 provenance, G2, G3, G5, G6, G7
(from the raw samples), R2, R4 and R5. All four round-1 findings are resolved.

One MAJOR finding remains, and it concerns the record, not the gated code. The record says that on the combined tree
the report-only `CheckPandf1` check passes on AIUE-61-omp ("CHECK OK pandf1 iterm 2"). That does not reproduce. I ran
it twice: one run failed with the same two lines as AIUE-60-omp, and the other died with SIGTRAP (exit 133). The
protocol run's own log has no Fortran output at all.

## Summary

The rebase only replays the commits: `git range-diff` shows the product commit `c95342e` identical to `155e562`, and
only the `.claude/context` commits needed merging. The merged `openmp-jacobian.md` keeps AIUE-60's rules 1 to 5, adds
the reset rule as rule 6, and points the clip rule at `ppp/parallel.F90:296`, which is still `sfscal(ii)`. Both hooks
are clean.

On the combined tree, every pre-registered prediction holds:
- the G0b WRITTEN set is exactly the 8 names;
- the full-problem hash is still `8761cd9e36658ee1`;
- R2's `get_fnrm` bits are still `0x1.aa0e230edbab4p-2`.

G7 passes at 2, 4 and 8 threads by the plan's rule. The quiet threshold was respected in every one of the 105 timed
runs, and the timing ran alone before the protocol.

R4 reports honestly that mid-size problems lose a lot at 8 threads: ×1.43 with 16 chunks and ×2.12 with 8. The record
omits one R4 item and does not say how far the stand-in can be trusted (I2-m1). There is a recommendation for the
owner below.

## Findings

### MAJOR

**I2-M1. The `CheckPandf1` result recorded for AIUE-61-omp on the combined tree does not reproduce, and one of my
reruns crashed.**
- **Where:** `docs/reviews/AIUE-61-validation.txt:60-65`: "CheckPandf1 (report only): AIUE-61-omp "CHECK OK pandf1
  iterm 2" ... (On the AIUE-56 base, AIUE-61 failed this check too; on the combined tree it passes. Not investigated
  here ...)".
- **Evidence:**
  1. `scratch-AIUE-61/final/g9a/ompcheck_new_pandf1/run.log` is 484 bytes. It holds the banner, the Python save-read
     lines and `CHECK OK pandf1 iterm 2`, and **no Fortran output at all**: no `Updating OMP Jacobian`, no `Serial and
     parallel pandf are identical`, no `iter=` lines. The other three G9a logs from the same protocol do contain these
     lines. The log alone therefore can't show that a single comparison ran. Its `iterm 2` also differs from the
     `jac` run's `iterm 4` on the same case.
  2. **My rerun 1** used `venvs/AIUE-61-omp`, whose extension hashes still equal the G1 record. I copied the D_only
     default case, ran `env -i`, 4 threads, `OMP_STACKSIZE=512M`, `AIUE-61-ompcheck.py pandf1 4`, and added
     `GFORTRAN_UNBUFFERED_ALL=y`. The result was `CHECK FAILED pandf1 RuntimeError diff in rhsnk` after
     `Updating OMP Jacobian [4|1]: npe = 2`, with exactly the two lines the record quotes for AIUE-60-omp:
     `76 2032.0288514119870 2032.0288330644739 9.03e-9` and `132 -48175.314616658346 -48175.314617835662 2.44e-11`.
  3. **My rerun 2** used exactly the protocol's environment (without the unbuffered flag). It exited with **133
     (SIGTRAP)** before any flushed output: the banner only, with no `CHECK` line. No crash report was written that I
     could read.
  - **Conclusion:** three runs of the same configuration on the same build gave three different outcomes: pass,
    deterministic-looking fail, and crash. The record states one sample as a property of the combined tree.
- **Is it AIUE-61's doing? A hypothesis, not verified:**
  - D_only has neq 420, so the new default builds the Jacobian as **one** chunk. One dynamically chosen thread carries
    column history afterwards; the others hold only the master state copied in.
  - `OMPPandf1Rhs` hands out RHS chunks with `schedule(dynamic)` (`ppp/omp_parallel.F90:1005-1006`) and runs on
    whatever worker state the Jacobian left (`openmp-jacobian.md`, the `ijactot` bullet). Whether an RHS chunk lands
    on the "dirty" thread then varies from run to run.
  - Under the old default (420 chunks over 4 threads) every worker was dirty, and the failure was the same in every
    build and run on record.
  - So AIUE-61 plausibly turns a deterministic failure of the non-default parallel-RHS check into an intermittent one.
    This is within the owner's RHS decision (epic AIUE-70) and doesn't touch the default (`OMPParallelPandf1=0`) or
    any Jacobian gate.
  - The SIGTRAP has no explanation yet. I can't tell from one sample whether AIUE-60-omp shows it too.
- **Why MAJOR, not BLOCKER:**
  - The `CheckPandf1` part is report-only by the recorded owner decision, and every gating part of G9a reproduces.
  - But a report-only result must be quoted correctly. A crash on the new build, in the configuration the `validate`
    skill's OpenMP check uses, has to be characterised before the owner can accept it.
- **Resolve:**
  1. Remove "on the combined tree it passes".
  2. Run the `pandf1` check at least 5 times on each of AIUE-61-omp and AIUE-60-omp, recording the exit status, with
     `GFORTRAN_UNBUFFERED_ALL=y` so the Fortran output survives. Quote the distribution verbatim.
  3. If the SIGTRAP occurs only on AIUE-61-omp: get a backtrace (`lldb`, or the `.ips` report outside the sandbox),
     then either fix the cause or have the owner accept it explicitly as AIUE-70 scope with a ticket or comment.
  4. Add one line to the PR and the AIUE-70 hand-off: with `OMPParallelPandf1=1` and `NchunksJac < Nthreads`, the RHS
     self-check may now vary from run to run.

### MINOR

**I2-m1. R4 leaves out one item the plan lists and does not say how far its stand-in can be trusted.**
- **Where:** `AIUE-61-validation.txt:94-99`; plan R4.
- **What is missing:**
  - The plan's R4 includes "the D_only time with the default". The final record doesn't report it. D_only has neq 420,
    so it runs as one chunk, which is the clearest case of "small problems no longer parallelise".
  - The mid-size stand-in forces 8 or 16 chunks onto the **full** grid (neq 44 352, chunks of 2 772 to 5 544 columns).
    There a reset costs about 22-26 ms. I estimate this from R4's 128- vs 64-chunk runs: +0.354 s × 4 threads / 64
    resets at T=4, and +0.206 s × 8 / 64 at T=8. That is under 1 % of a chunk, so the stand-in measures pure load
    imbalance.
  - A real grid of neq 2 400 to 4 800 has a cheaper reset but chunks of only 300 columns, and its column costs vary
    along `iv` in a different pattern. The ×1.43/×2.12 numbers could be too high or too low for real cases.
- **Resolve:** add the D_only line (or "not run"). Add one sentence on what the stand-in represents. Ideally, add one
  direct measurement on a real mid-size case, e.g. pytests `slab` (neq 4 522, 15 chunks) or `full-d_c-16x8` (neq 2 340,
  7 chunks), NEW against OLD at 8 threads.

**I2-m2. The docstring of the G9a tool contradicts the amended plan.**
- **Where:** `docs/reviews/AIUE-61-ompcheck.py:3-4`.
- **What is wrong:** the docstring says `pandf1` is "gating" and `jac` is "report only". The amended G9a has it the
  other way round: `CheckJac` gates and `CheckPandf1` is report-only.
- **Resolve:** a text fix. Ideally also record the process exit status, which bears on I2-M1.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| **I1-M1** G9a recorded "PASS\*" under an unchanged criterion | **Resolved** | See below. |
| **I1-M2** AIUE-60 premise and G0b expectation out of date | **Resolved** | See below. |
| **I1-m1** `.v` text overclaims | **Resolved** | `ppp/ppp.v:63-65` now reads "Validated only where exmain allows OpenMP ... and NOT for nxpt=2, limiter sputtering, coupled walls, istabon=5,6 (AIUE-60/69)". This agrees with `openmp-jacobian.md` ("Not validated: ..."). |
| **I1-m2** verbose table prints unused weights | **Resolved** | See below. |

**I1-M1.**
- The plan's G9a row now makes the `CheckPandf1` part report-only. It cites the 15:35 owner decision, which I checked
  at `AIUE-8-planning/docs/specs/AIUE-8-progress.md:209-212`.
- The record says PASS under the amended criterion, quotes the AIUE-60-omp output verbatim, and records `CheckJac` as
  the gating PASS. My reruns confirm `CheckJac` OK.
- The new problem with the report-only AIUE-61 line is I2-M1.

**I1-M2.**
- Plan lines 32-43 and 141-143 now state amendment 1's facts: `areapl`/`TimingPandfOn` threadprivate, the timers
  atomic through `acctim`, `nfsp` written only when it changes.
- Line 162 corrects the timer sentence.
- The G0b set was pre-registered (G0b row; passed as `AIUE61_G0B_EXPECT`). `g0b/shared_full.json` shows:
  - `expected` and `written` are the same 8 names;
  - `missing_from_expected=[]`, `unexpected=[]`, `outside_probe_S=[]`, `in_part_B=[]`;
  - `yl_neq_plus_1=1.0`.
- G-common and G-iotable ran on the combined build (`gcommon.txt`, `giotable.txt`).
- The clip-survival prediction was pre-registered and holds (see the checks below).

**I1-m2.**
- `git diff c95342e..b717734 -- ppp/` shows a fixed-mode branch that prints `ivmin`, `ivmax` and `OMPTimeLocalJac`.
  The format `(a,I3,a,I7,I7,a,f6.2)` matches its 7 items.
- The change is compiled into the final builds (`AIUE-61-omp` and `-serial` at `b717734`). It was not exercised at
  run time; it is cosmetic.

## Not independently verified (environment)

- **No gate was re-run** apart from my two `CheckPandf1` runs. That covers G1, G2-G6, G9b, G10/G10b, NC1-NC5, R2,
  G-common and G-iotable. I recomputed everything I could from the stored records (see "What was checked").
- **G7 and R4** were not re-timed: the budget forbids it and the machine is shared. I recomputed the medians, ranges
  and paired ratios from `timing/*.jsonl`, and checked the quiet rule on every sample.
- **R5** ran under Rosetta emulation of x86-64, not on native hardware. I verified the stored Linux records:
  - every run of `full` at 2/4/8 threads has the same Jacobian hash as the serial reference (`0d652b95…`);
  - `up` at 4/8 threads equals serial (`8b1560ee…`);
  - `tebox1` equals serial (`adf12639…`);
  - the three thread-pair compares AGREE.

  The first native CI run is still the confirming check, as the record says. The AIUE-56 comparison numbers for M3
  ("up jac 4 threads 3/5, 8 threads 0/5") come from earlier records, which I did not re-check.
- **The SIGTRAP in I2-M1:** no `.ips` report was written that I can read from this sandbox, so I have no backtrace.

## What was checked and how

1. **Rebase.**
   - `git range-diff 1553e75..604a667 f8db593..ad5819b`: 10 of 12 commits are `=`, including the product commit
     `155e562`→`c95342e`. The two `!` commits are the `.claude/context` merges: rule 5 (AIUE-60) kept, the reset rule
     renumbered 6, the refs re-locked.
   - `git merge-base --is-ancestor f8db593 HEAD`: yes.
   - `ppp/parallel.F90:296` is `storage: if (abs(jacelem*sfscal(ii)) .gt. jaccliplim)`.
   - `git diff f8db593..HEAD -- ppp/parallel.F90` shows only AIUE-61's `ifresh` argument and the reset.
   - `openmp-jacobian.md` rules 1-6 are present, in that order.
   - `git diff --stat b717734..HEAD` touches only `docs/reviews` (tools and record). The worktree is clean.
2. **Hooks.**
   - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: `OK`, exit 0. The advisory re-read list
     appears because `origin/v9-develop` doesn't contain AIUE-56/60/61; nothing is stale.
   - `uv run .claude/hooks/change_kind.py --range f8db593..HEAD`: `OK`, class ticket. The process files are only
     `.claude/context/*`, in commits carrying the `AI-layer: code-facts` trailer (`a72694b`, `c564653`, `5e34961`).
3. **Build provenance.**
   - The frozen trees `AIUE-61-omp` and `-serial` are at `b717734` with 0 dirty files.
   - I re-hashed all 11 extensions of each of the 4 G1 venvs against `g1/serial_check.json`: all match (`6351a878…`,
     `8675a4e3…`, `b71788af…`, `141a53db…`).
   - `0fac655` is an ancestor of `origin/v9-develop`, with no product diff between them.
   - `ee76a15` and `f8db593` have no product diff, and the AIUE-60 worktree is clean.
4. **Hash survival and G3-count.** I recomputed the `jworker` hashes from each run's saved `jac.npz`:
   - `cnt_full_t1/2/4/8`, `isjr_def`, `isjr_off` and `nostack_new_t4/t8` all give `8761cd9e36658ee1` (nnz 3 180 971,
     `NchunksJac` 64);
   - tebox gives `b6289bba…` (1 chunk);
   - tebox1 gives `6857dc9b…` (25 chunks) at every thread count;
   - G10 gives `55abc672…` ×5 and `5de8e754…` ×5.
5. **G2/G3/G5/G6/R1** (my `npzhash.py`/`jdiff.py` over `record.npz`, not the harness compare):
   - `full`: 36 OpenMP runs (G2 20, G3 15, sched3 1), one Jacobian hash `296cec99…`. Serial is `a5475a73…`.
   - `tebox1`: 35 runs give `f2c08109…`.
   - `tebox`: 35 runs give `ac52fa28…`, which equals serial.
   - These hashes are identical to the round-1 values on the AIUE-56 base.
   - G5: for each configuration, all 12 runs (2 arms × 3 thread counts × K=2) share one hash. tebox, ti, ni, up and ng
     equal serial; full, te and phi don't.
   - Deviation from serial:

     | Case | Entries | Value / only serial / only OpenMP | Rows | Worst × row max |
     |---|---|---|---|---|
     | `full` | 12 275 | 2914 / 9340 / 21 | 78 | 4.59e-9 |
     | te_phi | 1364 | 338 / 1026 / 0 | 75 | 7.15e-9 |
     | te | 254 | | 31 | 8.42e-10 |
     | tebox1 | 2 | | | 5.62e-10 |

     All are equal to the record.
6. **G7** (recomputed from `timing/g7.jsonl`):
   - 57 runs, 0 skipped, 0 errors. Every `load1_start ≤ 14−T` (0 violations); load1 at start 4.26-7.08; longest wait
     120 s.
   - The timing files end at 18:46:00 and `protocol.log` starts at 18:46:24, so the timing ran alone.
   - T=2 ratio of medians 18.020/17.562 = 1.026, and the paired median of the 5 pairs is 1.022. T=4 and T=8 also match
     the record (1.013/1.010; 1.025/1.034, n=9).
   - g7it3 and r4 match too: 0 violations, and r4 at T=8 n8 = 10.043/4.744 = 2.117.
   - One sample (g7 unit 12, LEG T=2) ended with load1 13.91, which shows an outside burst during the run. It is not
     a NEW/OLD sample, and the rule governs only the start.
7. **R2:** the 4 `state.npz` files hash identically under my own scheme (`4bd29cc5…`). Every `conv.json` has step 1
   with `iterm 4` and `0x1.aa0e230edbab4p-2`.
8. **Controls:**
   - NC1: t2 runs equal each other; the two t4 runs differ.
   - NC2: 5 distinct hashes.
   - NC3: old exits -11 with no record; new completes.
   - NC4: both compares AGREE.
   - NC5: `protocol.log:24-35` shows 4 of 5 runs tripping `omptimelocaljac` index 3/4 > 2. The plan requires at least
     1: met.
   - G0a: 4 regions, `unexpected_after_reset` empty, `yldot_bitwise_equal` true.
9. **G9a D_only:** after normalising the duration suffixes, the per-file outcomes are identical: OpenMP new = old,
   121/4; serial new = old, 120/5. G9b: 8 runs, one hash `9f5f1b18…`, 0 entries different from serial.
10. **`CheckPandf1`:** the two runs described in I2-M1, in `/tmp/rev61r2/new_pandf1{,_b}/run.log`. This used the whole
    run budget: 2 short runs at 4 threads.
11. **R4 recommendation for the owner:**
    - Keep `OMPJacMinChunkLen=300` for this ticket. All the bitwise evidence was gathered with it, and it protects
      masked-box runs: there a reset is a full-grid `pandf` (about 20 ms, from the Te box's 25-chunk time) while a chunk
      has only a few active columns.
    - Before release, state in the PR and in the `.v`/docs text that problems with neq up to about 5 000 at 8 threads
      may build the Jacobian up to about 2× slower than the old default. The knobs are `OMPJacMinChunkLen` (smaller)
      and `OMPJacFixedChunks=0`.
    - Open a follow-up to measure one real mid-size case. If the penalty holds, choose a smaller floor or one that
      depends on `neq` and `nx*ny`. The chunk count must stay independent of the thread count.
