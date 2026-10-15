# AIUE-64 validation records

These are the records behind the AIUE-64 fix: link the Forthon extensions with `-fopenmp` in the Linux OpenMP
build. The plan is `.claude/plans/AIUE-64-omp-linux-link.md` (§Testing strategy M1–M4, L1–L6).

- Commits: `BASE` = `4faed39` (product tree identical to `0fac655`); `FIX` = `1e8eb78`.
- Harness: AIUE-57 `8ee189d`.
- Linux runs: Docker Desktop on macOS arm64, `--platform linux/amd64` (Rosetta), `--cpus 5 --memory 7g`, one
  container at a time. The repository was mounted read-only and every build cloned its commit (clean tree).
- Images: `aiue62-ubuntu:amd64` (Ubuntu 24.04, gcc 13.3, Python 3.12) and `aiue62:amd64` (Debian 12, gcc 12.2,
  Python 3.11). Both come from AIUE-62 `tests/deterministic_omp/linux/Dockerfile{.ubuntu,}`.

## Results

| Check | Result | Records |
|---|---|---|
| M1 macOS link unchanged (OpenMP and serial) | PASS: link lines, `otool -L`, `otool -hv` and the anchored `nm -u` sets are identical before and after; libomp only in `uedgeC`; omp 4/4/13, serial ppppy 2 | `macos/{before,after}/` |
| M2 macOS import | PASS (both builds, exit 0) | `macos/after/m2_import.txt` |
| M3 AIUE-53 serial check | PASS: `RESULT: AGREE (bitwise identical; complete gate)  [pairs serial+omp0, cases all (42)]` | `serial_check/` |
| L1 Ubuntu red → green | PASS: `base` gives `undefined symbol: GOMP_parallel`, exit 127; `fix` exits 0. `ldd -r` OpenMP filter: `base` apipy/bbbpy/ppppy, `fix` none | `ubuntu/import.txt`, `ubuntu/rec_*/ldd_r_omp.txt` |
| L2 Ubuntu NEEDED and link lines | PASS: apipy/bbbpy/ppppy NEED `libgomp.so.1`; no `not found`; no libomp/libiomp5; `uedgeC` unchanged; Forthon link lines = `base` + one `-fopenmp` | `ubuntu/rec_fix/`, `ubuntu/rec_base/` |
| L3 equals the `LDFLAGS=-fopenmp` workaround | PASS: NEEDED and Forthon link lines identical; `wkld`'s `uedgeC` link has a second `-fopenmp` | `ubuntu/rec_wkld/` |
| L4 Linux serial unchanged | PASS: all records identical; serial ppppy leaves `omp_get_thread_num_`, `omp_get_wtime_` unresolved (AIUE-67) | `ubuntu/rec_{base,fix}-ser/` |
| L5 AIUE-57 CI step replay | PASS: `OMP CI RESULT: PASS (exit 0)`. The jac arm differs from serial, report-only (pre-AIUE-56 code) | `ubuntu/ci_step.log`, `ubuntu/ci/` |
| L5 thread probe, as first registered | **FAIL** `n1-n0 = 0`. A probe-design error: the workers already exist after `import uedge` | `ubuntu/thread_probe*.txt/log`, `ubuntu_diag/` |
| L5 thread probe, amended (plan amendment) | PASS: worker CPU during the Te-box `exmain` is ≥ max(5 × serial-arm control, 1 ms) at N=2 and N=4 | `ubuntu_probe2/thread_probe2.txt` |
| L6 Debian 12 | PASS: import exit 0; `ldd -r` filter empty; NEEDED as in L2; `gcc -dumpspecs` `as-needed` 3 | `debian/` |

## Files

- `scripts/` holds the drivers that produced these records.
  - Linux: `run_ubuntu64.sh` (L1–L5), `run_ubuntu64_diag.sh` (the diagnostic), `run_ubuntu64_probe2.sh` (the
    amended L5 probe) and `run_debian64.sh` (L6). Helpers: `build_uedge.sh NAME COMMIT [serial]`,
    `link_record.sh`, `import_check.sh`, `thread_probe.py`, `diag_probe.py`, `thread_probe2.py`,
    `probe2_verdict.py`, `clone_harness.sh`.
  - macOS: `build_pair.sh` (uses `uedge-wt/build_uedge.sh`) and `mac_record.sh`.
- `rec_<build>/` holds per-extension records:
  - `needed.txt`: `readelf -d` NEEDED;
  - `ldd.txt`;
  - `nm_omp.txt`: undefined `^(GOMP_|omp_)` symbols;
  - `ldd_r_omp.txt`: `ldd -r` undefined `GOMP_`/`omp_` symbols;
  - `links.txt`: the normalised `-shared` link lines from the build log.
- Not committed: the build trees, the full build logs, the harness `record.npz` arrays and the `serial_check`
  run directories.

## How it was run

```bash
R=<UEDGE_v9_dev checkout>; S=<this directory>/scripts; OUT=<scratch>
docker run --rm --platform linux/amd64 --cpus 5 --memory 7g -v $R:/mnt/repo:ro -v $OUT/ubuntu:/out \
  -v $S:/scripts:ro aiue62-ubuntu:amd64 bash -c 'mkdir -p /work && /scripts/run_ubuntu64.sh 1e8eb78 > /out/driver.log 2>&1'
# the same with run_ubuntu64_diag.sh, run_ubuntu64_probe2.sh (Ubuntu) and run_debian64.sh (aiue62:amd64)
python uedge-wt/AIUE-53/tests/deterministic_omp/harness/serial_check.py --base-python venvs/base-serial/bin/python \
  --new-python venvs/AIUE-64-serial/bin/python --base-omp-python venvs/base-omp/bin/python \
  --new-omp-python venvs/AIUE-64-omp/bin/python --jobs 4 --cases all --pytests-dir uedge-pytests --out <dir>
```
