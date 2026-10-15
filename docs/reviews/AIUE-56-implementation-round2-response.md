# Response to AIUE-56 implementation round 2 (REVISE: 0 blocker, 1 major, 2 minor)

| Finding | Response |
|---|---|
| I2-M1 residual characterisation lacks size vs ulp, plate adjacency, serial history | Added to the validation record (computed over 10 full-problem and 10 Te-box post-fix runs): size ≈ 1 ulp(yldot)/dyl (median; Te box 0.5; lower bounds); not plate-concentrated (23 % of entries in plate-adjacent cells, 71 distinct cells; Te box single cell (4,20)); history: outside-loop history doesn't matter (P3-m3), the in-loop history mechanism is the AIUE-55 finding (emulation, `vsoree` carrier, FMA), pointer given. |
| I2-m1 context bullet: wrong reason the parallel RHS follows a copy | Fixed in `openmp-jacobian.md` and the record: the pre-Jacobian RHS is serial because of the `ijactot>0` test; with `icntnunk=1` or a Python RHS call after an earlier `exmain`, the parallel RHS runs on the previous Jacobian's worker state. |
| I2-m2 run descriptions | Fixed: timing K=8 (plan said 10) and concurrent with the pytests run (noisy pairs; the reviewer's independent rerun agrees); pytests 117 pass / 3 fail / 5 no summary in both builds; 6 (not 9) directories on cf23ddf, two straddle. |
