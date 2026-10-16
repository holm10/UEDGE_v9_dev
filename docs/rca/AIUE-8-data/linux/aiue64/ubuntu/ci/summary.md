## OpenMP determinism CI: PASS (set custom, gate none, bitwise)

Report-only arm(s), not gating:

- [tebox1] configuration tebox, arm jac, threads 2: FAIL: first mismatch in equation te, cell (ix=4,iy=18); 0/2 runs agree with serial; jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) [agreement (serial vs run0)]
- [tebox1] configuration tebox, arm jac, threads 4: FAIL: first mismatch in equation te, cell (ix=4,iy=18); 0/2 runs agree with serial; jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) [agreement (serial vs run0)]

| flow | configurations | threads | repeats | itermx | runs wall s | total wall s |
|---|---|---|---|---|---|---|
| tebox1 | tebox | 2,4 | 2 | one evaluation | 21.5 | 21.6 |

Wall time of all flows (run_omp_ci.sh): 25 s

### Flow `tebox1`

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| tebox | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) [agreement (serial vs run0)] |
| tebox | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) [agreement (serial vs run0)] |

ARM jac: FAIL  (report only)

runs 21.5 s wall, total 21.6 s, exit code 0 (gate none)

