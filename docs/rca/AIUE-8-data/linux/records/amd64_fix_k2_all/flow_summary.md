# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| tebox | jac | 2 | PASS | 2/2 | yes |  |  |  |
| tebox | jac | 4 | PASS | 2/2 | yes |  |  |  |
| tebox | jac | 8 | PASS | 2/2 | yes |  |  |  |
| tebox | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| tebox | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| tebox | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |
| full | jac | 2 | PASS | 2/2 | yes |  |  |  |
| full | jac | 4 | PASS | 2/2 | yes |  |  |  |
| full | jac | 8 | PASS | 2/2 | yes |  |  |  |
| full | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| full | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| full | jacrhs | 8 | FAIL | 1/2 | no | up | jac:post_exmain | jacobian:post_exmain only_b row up[1](ix=1,iy=29) col ni[7](ix=0,iy=31) [agreement (serial vs run0)] |
| te | jac | 2 | PASS | 2/2 | yes |  |  |  |
| te | jac | 4 | PASS | 2/2 | yes |  |  |  |
| te | jac | 8 | PASS | 2/2 | yes |  |  |  |
| te | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| te | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| te | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |
| ti | jac | 2 | PASS | 2/2 | yes |  |  |  |
| ti | jac | 4 | PASS | 2/2 | yes |  |  |  |
| ti | jac | 8 | PASS | 2/2 | yes |  |  |  |
| ti | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| ti | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| ti | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |
| ni | jac | 2 | PASS | 2/2 | yes |  |  |  |
| ni | jac | 4 | PASS | 2/2 | yes |  |  |  |
| ni | jac | 8 | PASS | 2/2 | yes |  |  |  |
| ni | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| ni | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| ni | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |
| up | jac | 2 | PASS | 2/2 | yes |  |  |  |
| up | jac | 4 | PASS | 2/2 | yes |  |  |  |
| up | jac | 8 | FAIL | 0/2 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=15) col up[0](ix=0,iy=16) [agreement (serial vs run0)] |
| up | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| up | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| up | jacrhs | 8 | FAIL | 0/2 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=15) col up[1](ix=0,iy=16) [agreement (serial vs run0)] |
| ng | jac | 2 | PASS | 2/2 | yes |  |  |  |
| ng | jac | 4 | PASS | 2/2 | yes |  |  |  |
| ng | jac | 8 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |
| phi | jac | 2 | PASS | 2/2 | yes |  |  |  |
| phi | jac | 4 | PASS | 2/2 | yes |  |  |  |
| phi | jac | 8 | PASS | 2/2 | yes |  |  |  |
| phi | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| phi | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| phi | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |

ARM jac: FAIL  (report only)
ARM jacrhs: FAIL  (report only)

runs 1064.3 s wall, total 1076.0 s, exit code 0 (gate none)
