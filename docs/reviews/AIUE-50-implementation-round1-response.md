# AIUE-50 implementation review, round 1: response

Review: `docs/reviews/AIUE-50-implementation-round1.md` (REVISE: 0 BLOCKER, 1 MAJOR, 8 MINOR). All findings were
accepted. Changes are in the commit that adds this file.

| Finding | Response | Where |
|---|---|---|
| I1-M1: C1 also corrupts the parallel RHS | Accepted. §Summary has a new paragraph: `OMPPandf1Rhs` does no copy and inherits the workers' state from the last Jacobian copy, so the parallel RHS is wrong (all 25 Te rows, `fnrm` 0.87e31, an extra Newton step, different `fnrm_final`) until the second Jacobian. It cites the reviewer's `jacrhs` evidence and says the swap build matches serial on that arm. The fix directions now require the `jacrhs` arm and one `--checkbounds` OpenMP run for AIUE-56. The "Not covered" bullet no longer reads as if the parallel RHS were unaffected. | RCA §Summary, fix directions, §Not covered |
| I1-m1: `splinem`, not `readpost`; `k?ords` default `/4/` | Accepted. The Summary names `splinem` (`api/apip93.m:101-107`, called from `bbb/odesetup.m:1130,1150`), gives the `/4/` defaults (`api/api.v:161-165`), and says the knot vectors keep elements 1:5. F2 updated. | RCA §Summary, F2 |
| I1-m2: E4 mechanism of the wrong values | Accepted. `B3VAL` fails its range test and returns 0, so `emissbs = 1.0` exactly (1.9e-35 true value). The wrong value is deterministic per cell; the run-to-run variation comes only from the column-to-thread mapping. | RCA §Summary, §E4 |
| I1-m3: guard regex and count | Accepted. The regex now matches only `... .le.size(var)`. The summary prints bbb 430 and api 12 guarded copies; the RCA says 442 and names the 4 unguarded fixed-size arrays. | `scan_ompcopy.py`, RCA coverage summary |
| I1-m4: nksol mode in `scan_shared_state.py` | Accepted. The scan now evaluates with `yl(neq+1)=1` (Jacobian mode) by default, with `--nksol-mode` for the old behaviour, and records the value in the JSON. I re-ran the Te box (diff and sentinel) and the full-problem diff. In Jacobian mode the `PandfTiming` accumulators disappear, which agrees with TSan. `TimingPandfOn`, `nfsp`, the `com` timers including `ttimpfe`, and `areapl` (full problem) remain. F6 is relabelled and adds `ttimpfe`. | `scan_shared_state.py`, RCA Method and F6 |
| I1-m5: `emcoef` in `copyin` | Accepted. F15 now records that `copyin` pointer-assigns the workers' `emcoef` to the master's array. That association persists, so later `OmpCopyPointeremcoef` calls race (same values; harmless) and leak the workers' copies. It is left to AIUE-56 to decide. | RCA F15 |
| I1-m6: no full-problem sentinel | Accepted as disclosed. A follow-up is recorded in "Not covered": a restricted variable list or batched children on plate-adjacent columns. | RCA §Not covered |
| I1-m7: range of the full-problem M2 residual | Accepted. The Summary states the observed range: 0 and 472 (my runs), 860-1037 (main-session harness), 1217 entries in 26 Te rows (reviewer), all at noise level. 472 is not a bound. | RCA §Summary |
| I1-m8: documentation pointers | Accepted. The `scan_ompcopy.py` docstring now points to "How to reproduce" in the RCA instead of the nonexistent `run_tpcheck.md`. The README tool table lists the four new tools. "How to reproduce" and the `scan_shared_state.py` docstring say to set `UEDGE_OMP_RATES_DIR` when running outside the repository. | `scan_ompcopy.py`, `scan_shared_state.py`, README, RCA |

The M2 mechanism itself (follow-up investigation for AIUE-55) is deliberately not added to this branch.
