# Response to AIUE-55 implementation round 3 (REVISE: 0 blocker, 1 major, 3 minor) — round cap reached

All findings applied (commit after this file). Round 3 was the last round the review loop allows, so the ticket is
**escalated to the owner** instead of a fourth round (unattended run; end-to-end-feature Step 3b).

| Finding | Response |
|---|---|
| I3-M1 F's claim exceeds the evidence (dynamic scheduling, state carries between chunks) | Applied: F's row now says the tested code uses `schedule(dynamic,OMPLoopJacNchunk)` (`ppp/omp_parallel.F90:712`) with carried worker state, that the observed reproducibility is empirical, that a production F needs `schedule(static)` with one chunk per thread or a fixed worker state per chunk start, and "consistent with PRD §11's fallback at 4 threads on this evidence" replaces "meets as written". The contrast with E (history rebuilt regardless of thread) is stated. |
| I3-m1 two unlabelled cost figures; "at best" wrong | Applied: the conclusion paragraph and E's row give the estimated 4.4 % × T (+9 % at 2 threads, +18 % at 4, +35 % at 8, not measured); "at best" removed. |
| I3-m2 table header `||` | Fixed. |
| I3-m3 F's tolerance result missing | Added: AIUE-56 gate PASS on the 16-chunk records, worst 4.59e-9 × row max. |

**Owner:** accept this RCA as revised (the remaining findings were wording about option F and the cost), then take
decision 9 (E / F / A / B-interim / D).
