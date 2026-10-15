# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| up | jac | 8 | FAIL | 0/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=18) col up[0](ix=0,iy=19) [agreement (serial vs run0)] |
| up | jacrhs | 8 | FAIL | 0/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=19) col up[0](ix=0,iy=20) [agreement (serial vs run0)] |
| full | jac | 8 | FAIL | 2/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=16) col ni[1](ix=0,iy=17) [agreement (serial vs run0)] |
| full | jacrhs | 8 | FAIL | 1/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=34) col up[1](ix=0,iy=35) [agreement (serial vs run1)] |

ARM jac: FAIL  (report only)
ARM jacrhs: FAIL  (report only)

runs 353.7 s wall, total 361.3 s, exit code 0 (gate none)
