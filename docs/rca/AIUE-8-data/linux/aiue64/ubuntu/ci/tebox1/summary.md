# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| tebox | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) [agreement (serial vs run0)] |
| tebox | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) [agreement (serial vs run0)] |

ARM jac: FAIL  (report only)

runs 21.5 s wall, total 21.6 s, exit code 0 (gate none)
