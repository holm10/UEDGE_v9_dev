# AIUE-61 plan review round 2 — response

The verdict was APPROVE (0/0/5). All five optional minors are folded into the plan (revision 3) before
implementation, as the coordinator asked.

| Finding | Fixed where |
|---|---|
| L2-m1 G7 load rule | G7 rules: poll until load1 ≤ 14 − T before each run (every 15 s, 20 min timeout, wait recorded) instead of re-queueing. Shuffled NEW/OLD pairs; the median of the paired ratios is reported next to the ratio of medians. If there are no quiet windows today, G7 is "not run"; the threshold is never relaxed. |
| L2-m2 G10 power | The 2-chunk cases (Te box with `OMPJacMinChunkLen=12`, `full` with `OMPJacNchunksFixed=2`) run at 8 threads with K=5. New G10-static: `OMPTimeLocalJac(tid+1)` may only occur in the legacy branch. |
| L2-m3 Mid-size effect of Q5 | R4 adds `full` with `OMPJacNchunksFixed` 8 and 16 at 8 threads against the old default. The PR adds a sentence that small problems no longer parallelise the Jacobian, or only partly. |
| L2-m4 G10b | `env -u OMP_STACKSIZE` in the launcher, and the same runs on `AIUE-56-omp` as a control: a crash on both builds is pre-existing (and the docs then require `OMP_STACKSIZE`); only an AIUE-61-only crash is a FAIL. |
| L2-m5 Slips | Task 2's range is `:547-563`, and `OMPTotTimeJacCalc = tick()` stays outside the branch. The `.v` text says "ismcnon=0 and isimpon 0, 2, 6, 7 only". G0b expects "whatever AIUE-60 leaves non-threadprivate". Solution 7 says `allocate` runs under `ismpion=0` (`bbb/odesetup.m:6646-6650`). |
