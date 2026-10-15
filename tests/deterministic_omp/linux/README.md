# Linux (libgomp) runs for AIUE-62

These files reproduce the records in `docs/rca/AIUE-8-data/linux/`. They are Docker images and shell scripts for
`linux/amd64`. The original runs used Docker Desktop on macOS arm64, so x86-64 was emulated by Rosetta. Results and
their scope are in `docs/rca/AIUE-8-omp-jacobian-nondeterminism.md`, §Linux characterisation.

| File | Purpose |
|---|---|
| `Dockerfile` | Debian 12 image: `python:3.11-bookworm` pinned by digest, plus `gfortran` 12.2 |
| `Dockerfile.ubuntu` | Ubuntu 24.04 image (pinned by digest): gcc/gfortran 13.3, the CI runner's distribution |
| `clone_harness.sh COMMIT` | clones the read-only repo into `/work/harness` at the reviewed harness commit |
| `build_uedge.sh NAME COMMIT` | clones into `/work/src-NAME` and makes `/work/venv-NAME` with the CI pip dependencies, then runs `python -m pip install -v .`. Honours `LDFLAGS` |
| `build_uedge_sed.sh NAME COMMIT FILE EXPR` | the same, with one `sed -E` edit first (the control builds) |
| `run_flow.sh BUILD NAME ARGS…` | one `harness/cli.py flow` run into `/out/BUILD/NAME`, logged to `/out/flows.log` |
| `fma_scan.sh BUILD` | counts FMA/AVX instructions per extension (`objdump -d`) and records `NEEDED`, `.comment` and the compile flags |
| `run_all.sh` | Debian main flows: K=20 Te box and full problem, then `flow --all` K=2 |
| `run_controls.sh` | Debian control builds (`fixtp`, `fixfma`) and their flows |
| `run_ubuntu.sh` | Ubuntu: the import check without `LDFLAGS`, then the AIUE-56 build with `LDFLAGS=-fopenmp`, the FMA scan, and Te box and full problem at K=5 |
| `gate_flows.py GATE LINKROOT HARNESS NAME=FLOW…` | runs the AIUE-56 C1 gate (`docs/reviews/AIUE-56-c1-gate.py` on `1553e75`) on every jac group |
| `gate_summary.py FILE` | summarises the gate output per group |

## Run order (as run)

```bash
R=/path/to/UEDGE_v9_dev; OUT=/path/to/out; S=$R/tests/deterministic_omp/linux   # any checkout holding the commits
docker build --platform linux/amd64 -t aiue62:amd64 -f $S/Dockerfile $S
docker run -d --name aiue62-amd64 --platform linux/amd64 --cpus 5 --memory 7g -v $R:/mnt/repo:ro \
  -v $OUT/amd64:/out -v $S:/scripts:ro -v aiue62-amd64-work:/work aiue62:amd64 sleep infinity
X="docker exec aiue62-amd64"
$X /scripts/clone_harness.sh 8ee189d76b0232cedfe17088574935b10b857df5
# default build (no LDFLAGS): fails to import (AIUE-64), see build_info.txt
$X /scripts/build_uedge.sh fix 1553e756539bb4e66b2241b840fc697e23101a36
$X /scripts/build_uedge.sh base 3865c79c959b18c346111ea62dc146de0671815b
$X bash -c 'for b in fix base; do HOME=/tmp/h /work/venv-$b/bin/python -I -c "import uedge" 2>&1 | tail -1; done'
# the builds actually measured
$X env LDFLAGS=-fopenmp /scripts/build_uedge.sh fixld 1553e756539bb4e66b2241b840fc697e23101a36
$X env LDFLAGS=-fopenmp /scripts/build_uedge.sh baseld 3865c79c959b18c346111ea62dc146de0671815b
$X bash -c 'for b in fixld baseld; do /scripts/fma_scan.sh $b > /out/fma_$b.txt 2>&1; done'
$X /scripts/run_all.sh
$X /scripts/run_controls.sh
C="--cores 5 --max-jobs 1 --gate none"
$X /scripts/run_flow.sh fixld up_threads_k5 --configs up --threads 4,5,6,8 --repeats 5 --arms jac $C
$X /scripts/run_flow.sh fixld up_t8_static_k5 --configs up --threads 8 --repeats 5 --arms jac \
  --ppp '{"OMPJacNchunks": -1, "OMPAutoBalance": 0}' $C
docker stop aiue62-amd64
# Ubuntu 24.04
docker build --platform linux/amd64 -t aiue62-ubuntu:amd64 -f $S/Dockerfile.ubuntu $S
docker run --rm --platform linux/amd64 --cpus 5 --memory 7g -v $R:/mnt/repo:ro -v $OUT/ubuntu:/out -v $S:/scripts:ro \
  aiue62-ubuntu:amd64 bash -c 'mkdir -p /work && /scripts/run_ubuntu.sh > /out/driver.log 2>&1'
# records (host, any Python with numpy; the harness checkout at 8ee189d for the gate's check_arm)
cd $OUT/amd64 && python $R/docs/rca/AIUE-8-data/make_prefix_data.py --out <data dir> NAME=FLOWDIR ...
python $S/gate_flows.py <AIUE-56-c1-gate.py> <new link dir> <harness>/tests/deterministic_omp NAME=FLOWDIR ...
```

The `NAME=FLOWDIR` pairs are the data set names in `docs/rca/AIUE-8-data/linux/records/`, for example
`amd64_fix_k20_tebox=fixld/k20_tebox`, `ctl_fixfma_k5_full=fixfma/k5_full` and `ubuntu_fix_k5_full=fixld/k5_full`.
`make_prefix_data.py` writes `prefix_runs.csv`/`prefix_stats.txt`; these were renamed to `runs.csv`/`stats.txt`.

## Not scripted, and deviations

- The `docker run`/`exec` lines above were typed by hand. The Ubuntu import check of the first session was only
  printed to the console. It is scripted in `run_ubuntu.sh` now and saved in its records.
- `gate_flows.py` changed after it produced `c1_gate.txt` for the Debian runs: the gate script's path became the first
  argument (it used to be found next to the script). The comparison logic is unchanged. `c1_gate.txt` also had the
  scratch link-directory prefixes removed with `sed`.
- `forthon` and `h5py` are not pinned (`forthon>=0.10.7`, as in CI). The versions that were installed are in each
  build's `pip freeze`, and the Debian one is quoted in `build_info.txt`.
- The arm64 run (`run_arm64.sh` in the session scratch) was stopped during its builds and is not committed.
