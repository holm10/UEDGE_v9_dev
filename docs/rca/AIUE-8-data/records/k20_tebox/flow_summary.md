# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| tebox | jac | 4 | FAIL | 0/20 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) [agreement (serial vs run0)] |
| tebox | jacrhs | 4 | FAIL | 0/20 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |

ARM jac: FAIL  (report only)
ARM jacrhs: FAIL  (report only)

runs 74.9 s wall, total 75.0 s, exit code 0 (gate none)
