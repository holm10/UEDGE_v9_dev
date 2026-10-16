# OpenMP test flow

| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | failing sections | first mismatch |
|---|---|---|---|---|---|---|---|---|
| tebox | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |
| tebox | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |
| tebox | jac | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18) [agreement (serial vs run0)] |
| tebox | jacrhs | 2 | FAIL | 0/2 | no | ?,te | fnrm_final,fnrm_printed,jac:post_exmain,jac:post_exmain (permuted indices),jacobian_count,sfscal,yldot,yldot_probe | jacobian_count: ['post_exmain'] vs ['post_exmain (permuted indices)'] [agreement (serial vs run0)] |
| tebox | jacrhs | 4 | FAIL | 0/2 | no | ?,te | fnrm_final,fnrm_printed,jac:post_exmain,jac:post_exmain (permuted indices),jacobian_count,sfscal,yldot,yldot_probe | jacobian_count: ['post_exmain'] vs ['post_exmain (permuted indices)'] [agreement (serial vs run0)] |
| tebox | jacrhs | 8 | FAIL | 0/2 | no | ?,te | fnrm_final,fnrm_printed,jac:post_exmain,jac:post_exmain (permuted indices),jacobian_count,sfscal,yldot,yldot_probe | jacobian_count: ['post_exmain'] vs ['post_exmain (permuted indices)'] [agreement (serial vs run0)] |
| full | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col ni[0](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col ni[0](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jac | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col ni[0](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jacrhs | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=1,iy=1) col ni[2](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jacrhs | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=1,iy=1) col ni[1](ix=1,iy=1) [agreement (serial vs run0)] |
| full | jacrhs | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=1,iy=1) col ni[0](ix=1,iy=1) [agreement (serial vs run0)] |
| te | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=2,iy=1) col te(ix=2,iy=1) [agreement (serial vs run0)] |
| te | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col te(ix=1,iy=1) [agreement (serial vs run0)] |
| te | jac | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col te(ix=1,iy=1) [agreement (serial vs run0)] |
| te | jacrhs | 2 | FAIL | 0/2 | n/a |  | run failed | failed run0: exited with -11 and wrote no record (see run.log) |
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
| up | jac | 8 | FAIL | 0/2 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=24) col up[1](ix=0,iy=24) [agreement (serial vs run0)] |
| up | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| up | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| up | jacrhs | 8 | FAIL | 0/2 | no | up | jac:post_exmain | jacobian:post_exmain value row up[1](ix=1,iy=16) col up[1](ix=0,iy=17) [agreement (serial vs run0)] |
| ng | jac | 2 | PASS | 2/2 | yes |  |  |  |
| ng | jac | 4 | PASS | 2/2 | yes |  |  |  |
| ng | jac | 8 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 2 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 4 | PASS | 2/2 | yes |  |  |  |
| ng | jacrhs | 8 | PASS | 2/2 | yes |  |  |  |
| phi | jac | 2 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col te(ix=1,iy=1) [agreement (serial vs run0)] |
| phi | jac | 4 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col te(ix=1,iy=1) [agreement (serial vs run0)] |
| phi | jac | 8 | FAIL | 0/2 | no | te | fnrm_final,fnrm_printed,jac:post_exmain,sfscal | jacobian:post_exmain value row te(ix=1,iy=1) col te(ix=1,iy=1) [agreement (serial vs run0)] |
| phi | jacrhs | 2 | FAIL | 0/2 | n/a |  | run failed | failed run0: RuntimeError |
| phi | jacrhs | 4 | FAIL | 0/2 | n/a |  | run failed | failed run0: exited with -11 and wrote no record (see run.log) |
| phi | jacrhs | 8 | FAIL | 0/2 | n/a | te | fnrm_final,fnrm_printed,jac:post_exmain,run failed,sfscal,yldot,yldot_probe | jacobian:post_exmain value row te(ix=1,iy=1) col te(ix=1,iy=1) [agreement (serial vs run0)] |

ARM jac: FAIL  (report only)
ARM jacrhs: FAIL  (report only)

runs 980.4 s wall, total 1010.1 s, exit code 0 (gate none)
