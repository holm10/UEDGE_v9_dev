# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| full | jac | 4 | FAIL | 0/20 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col ni[0](ix=1,iy=1) [agreement (serial vs run0)] |

ARM jac: FAIL  (report only)

runs 1292.1 s wall, total 1755.0 s, exit code 0 (gate none)
