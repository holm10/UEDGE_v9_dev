# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| up | jac | 4 | FAIL | 3/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=16) col up[0](ix=0,iy=17) [agreement (serial vs run0)] |
| up | jac | 5 | FAIL | 2/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=39) col up[0](ix=0,iy=40) [agreement (serial vs run1)] |
| up | jac | 6 | FAIL | 0/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=21) col up[0](ix=0,iy=22) [agreement (serial vs run0)] |
| up | jac | 8 | FAIL | 0/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=15) col up[0](ix=0,iy=16) [agreement (serial vs run0)] |

ARM jac: FAIL  (report only)

runs 150.6 s wall, total 151.0 s, exit code 0 (gate none)
