# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| up | jac | 8 | FAIL | 0/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=16) col up[0](ix=0,iy=17) [agreement (serial vs run0)] |
| up | jacrhs | 8 | FAIL | 0/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=19) col up[1](ix=0,iy=20) [agreement (serial vs run0)] |
| full | jac | 8 | FAIL | 0/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=28) col up[0](ix=0,iy=29) [agreement (serial vs run0)] |
| full | jacrhs | 8 | FAIL | 3/5 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=36) col up[1](ix=0,iy=37) [agreement (serial vs run1)] |

ARM jac: FAIL  (report only)
ARM jacrhs: FAIL  (report only)

runs 373.0 s wall, total 379.5 s, exit code 0 (gate none)
