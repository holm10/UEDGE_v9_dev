# AIUE-64 – notes for the PR description

## The fix

In the Linux OpenMP build, `setup.py` runs the Forthon make with `-fopenmp` appended to `LDFLAGS`, in that
subprocess only. Without it, `apipy`, `bbbpy` and `ppppy` were linked without the OpenMP runtime. On `--as-needed`
toolchains (Ubuntu 24.04, Debian 12), `import uedge` then failed with `undefined symbol: GOMP_parallel`.

What is not affected:
- **Defaults and results:** no Fortran, `.v` or compile-flag change, so defaults are unchanged and no reference case
  moves. The AIUE-53 serial check gives `RESULT: AGREE (bitwise identical; complete gate)` on 42 cases.
- **macOS and serial builds:** the link is unchanged on every platform for the serial build, and on macOS for the
  OpenMP build (link lines, `otool` and `nm` identical).

Records: `docs/rca/AIUE-8-data/linux/aiue64/README.md`.

## Validation that did not come out green (M4, `validate`)

The pre-registered expectation was "`D_only` passes; `--omp` check as on `base-omp`". It deviates, identically on
base.

### `D_only` (uedge-pytests `b535508`)

Result: `5 failed, 120 passed, 1 warning`.

Failing tests:
- `nonog/concap`
- `nonog/ineudif0`
- `nonog/ineudif1`
- `nonog/ineudif3`
- `nonog/tg_atom_cftiexclg0p5`

Three of them raise `ValueError: operands could not be broadcast together with shapes (10,6,2) (10,6)`.

On `base-serial` the `FAILED` lists and all `Returned fnrm`/`Reference fnrm` lines are identical (quoted in
`validate/d_only.txt`). The `ineudif*` failures were already recorded on AIUE-56.

### OpenMP check (CheckPandf1=1, CheckJac=1, 4 threads, `fulltests/nonog_d_c-fb_16x8`, macOS)

Every run reports the Jacobians identical, then stops with `RuntimeError: diff in rhsnk`:
```
 >>>>                  272   387.04448987743109        387.04448987291863        1.1658757793646371E-011
 >>>>                  428  -102.89970684190475       -102.89970639107977        4.3812075279923317E-009
```

- I ran 3 alternating repeats each on the fix build and `base-omp`. All exit 1, and each fix log is identical to the
  base log of the same index.
- Attribution: an RHS-check difference, consistent with AIUE-58 R1 (not shown). The Jacobians are identical. Both
  rows are Ti rows, at (ix=2, iy=1) and (ix=14, iy=1), by the 13-per-cell ordering.

### Two one-off abnormal exits on the fix build

- **Exit 133:** the first run. The `gtimeout` wrapper itself died with SIGTRAP; the log stops after the banner.
- **Exit 139:** happened once, after the same `RuntimeError`. No crash report was found.

Neither recurred in the 3 alternating repeats per build. On macOS the change is inactive by construction.

## Other notes

- **L5 thread probe:** the probe as first registered failed (`n1-n0 = 0`). That was a probe-design error: the
  libgomp workers already exist after `import uedge`. The probe was amended before its re-run, which passed (worker
  CPU 10.1× the serial-arm control at N=2, at least 8.0× at N=4). Both runs are in the records.
- **Not tested:** native x86-64 CI, Linux wheels (cibuildwheel/manylinux; deferred by the owner), arm64 Linux,
  non-`--as-needed` distributions and `CC=clang` on Linux.
- **Follow-up:** AIUE-67 covers the serial build, which links `uedgeC` with `-fopenmp` and leaves the serial
  `ppppy`'s `omp_*` calls unresolved on Linux.
- **Merge precondition:** the branch base is local `v9-develop` `4faed39`. Open the PR only after its 7 AI-layer
  commits are on `origin/v9-develop`.
