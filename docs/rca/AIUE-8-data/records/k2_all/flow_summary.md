# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| tebox | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) [agreement (serial vs run0)] |
| tebox | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |
| tebox | jac | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |
| tebox | jacrhs | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |
| tebox | jacrhs | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |
| tebox | jacrhs | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |
| full | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col ni[0](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col ni[1](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jac | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col ni[0](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jacrhs | 2 | FAIL | 0/2 | n/a |  | run failed | failed run0: RuntimeError:  ** overflow: SVR routine lusol0 loop 40 |
| full | jacrhs | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=1,iy=1) col ni[1](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jacrhs | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=1,iy=1) col ni[1](ix=1,iy=1) [agreement (serial vs run0)] |
| te | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=2,iy=1) col te(ix=2,iy=1) [agreement (serial vs run0)] |
| te | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col te(ix=1,iy=1) [agreement (serial vs run0)] |
| te | jac | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=2,iy=1) col te(ix=2,iy=1) [agreement (serial vs run0)] |
| te | jacrhs | 2 | FAIL | 0/2 | n/a |  | run failed | failed run0: RuntimeError |
| te | jacrhs | 4 | FAIL | 0/2 | n/a |  | run failed | failed run0: exited with -11 and wrote no record (see run.log) |
| te | jacrhs | 8 | FAIL | 0/2 | n/a |  | run failed | failed run0: exited with -11 and wrote no record (see run.log) |
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
| up | jac | 8 | PASS | 2/2 | yes |  |  |  |
| up | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| up | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| up | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |
| ng | jac | 2 | PASS | 2/2 | yes |  |  |  |
| ng | jac | 4 | PASS | 2/2 | yes |  |  |  |
| ng | jac | 8 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |
| phi_te | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col te(ix=1,iy=1) [agreement (serial vs run0)] |
| phi_te | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col phi(ix=1,iy=1) [agreement (serial vs run0)] |
| phi_te | jac | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col phi(ix=1,iy=1) [agreement (serial vs run0)] |
| phi_te | jacrhs | 2 | FAIL | 0/2 | n/a |  | run failed | failed run0: exited with -11 and wrote no record (see run.log) |
| phi_te | jacrhs | 4 | FAIL | 0/2 | n/a |  | run failed | failed run0: exited with -11 and wrote no record (see run.log) |
| phi_te | jacrhs | 8 | FAIL | 0/2 | n/a |  | run failed | failed run0: exited with -11 and wrote no record (see run.log) |

ARM jac: FAIL  (gated)
ARM jacrhs: FAIL  (report only)

runs 276.5 s wall, total 367.6 s, exit code 1 (gate jac)
