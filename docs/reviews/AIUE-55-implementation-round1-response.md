# Response to AIUE-55 implementation round 1 (REVISE: 1 blocker, 2 major, 6 minor)

| Finding | Response |
|---|---|
| I1-B1 "unreachable without changing serial" contradicted; an OpenMP-only remedy not examined | Accepted and done: the replay remedy was prototyped in the threaded code (scratch tree `uedge-wt/AIUE-61-replay`, patches in the session scratchpad `replay/`). Minimal depth: R = `ubw` (= `mu`) passes every case; two grid rows pass only for some chunk boundaries. Threaded: Te box 3/3 bitwise and deterministic (contiguous and default chunks), full problem 3/3 with 16 contiguous chunks; serial of that build bitwise equal to base. Cost ≈ +18 % at one chunk per thread (+70 % at 16 chunks; default one-column chunks unusable). The exit question is restated: bitwise is reachable without changing serial (§9 report for the cost, no §9(a)). C2 is reframed as in-loop history with an inferred trigger; the fix list has both "reproduce the history" (E) and "remove the trigger" (A, A′, C). A pre-existing `OMPJacNchunks≠0` crash (stack) found on the way goes to AIUE-61. |
| I1-M1 B labelled the §11 fallback but doesn't meet it; static partition not offered | Fixed: B is now "tolerance gate, interim CI only", explicitly not meeting §11 (not deterministic). The static partition alone is not deterministic in the replay controls (Te box, contiguous chunks, R=0: 2 mismatches in 2/3 runs), so it isn't offered on its own; with replay it is (option E). |
| I1-M2 exit decision not per configuration / thread / arm | Fixed: a per-configuration × arm × threads table with what each option has shown and what is not run. |
| m1 P3-m3 described inaccurately | Fixed: (a) only shows outside-loop history is wiped by the full RHS; (b) column order wasn't permuted — the in-loop dependence comes from the emulation. |
| m2 "round-off level" understates A; pytests claim unmeasured | Fixed: 3.4e-9 relative fnrm, every Te-box yldot/sfscal changes; pytests effect "not measured". |
| m3 FMA stated as fact | Fixed: "inferred, assembly not inspected" in the table and text. |
| m4 `emcoef` copyin and `fmombal` without a ticket; F9 wording | Fixed: both in AIUE-60's row; `fmombal` reached only via `mombal` (`isimpon=5`). |
| m5 `jac_calc` range; rebase | Fixed: `bbb/oderhs.m:1012-1241` (loop 1100-1226); rebased onto the reviewed AIUE-54/AIUE-50. |
| m6 1e-6 is a margin | Fixed: stated next to the measured spreads (≤ 5.6e-10 Te box, ≤ 4.6e-9 full). |
