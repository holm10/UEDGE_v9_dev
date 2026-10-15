# Feature: AIUE-62 — Characterise the OpenMP Jacobian on Linux (libgomp), AIUE-54 follow-up

**Type**: Investigation / documentation (artifact only). **Default results**: unchanged (no product code).
**Branch / worktree**: `feature/v9-AIUE-62-linux-characterisation` @ `../uedge-wt/AIUE-62`, stacked on
`feature/v9-AIUE-55-omp-jacobian-rca` (holds the RCA document with the AIUE-54 tables). Epic AIUE-8.

## Question

1. Do the AIUE-54 pre-fix findings (C1: gross Te-row corruption, run-to-run variation) hold on Linux x86-64 with
   libgomp?
2. After the AIUE-56 fix (`4fae2f9`), is the OpenMP Jacobian **bitwise equal to serial** on x86-64 with the default
   flags (`-O3`, no `-march`), i.e. is the residual C2/M2 absent there? On macOS arm64 it is attributed (inferred) to
   FMA contraction; x86-64 baseline has no FMA instructions. This decides option D of decision 9.

## Builds (all inside Docker, one container at a time, `--cpus 5`)

| Build | Source | Product code |
|---|---|---|
| `base` | `origin/v9-develop` `3865c79` (product = `0fac655`, the AIUE-54 build; `3865c79` adds docs only) | pre-fix |
| `fix` | `bugfix/v9-AIUE-56-omp-jacobian-fix` `1553e75` (product change = `4fae2f9`, `ppp/omp_parallel.F90` only) | AIUE-56 |

- Platform **linux/amd64** (required; the CI runner's), emulated by Rosetta in Docker Desktop. Second column
  **linux/arm64** (native; libgomp + FMA) if time allows.
- Image: `python:3.11-bookworm` + `gfortran` (Debian bookworm, gfortran 12), Python 3.11, `numpy==1.26.4`,
  `forthon>=0.10.7`, `h5py`, `pytest` — the CI workflow's pip steps (`.github/workflows/build-test-omp.yml`, AIUE-57).
  Build command as CI: `python -m pip install -v .` (default OpenMP build, `setup.py` `FARGSOPT=-O3`, `-fopenmp`).
  One venv per build. Dockerfile kept in the session scratch dir; committed under `tests/deterministic_omp/` only if
  needed to reproduce the records (decided at the end: the recorded `build_info` must name everything it pins).
- Sources: the repository is mounted read-only; each build is a `git clone` of the mounted repo at the commit, inside a
  container volume (generated `.F` files never touch a worktree). The clone keeps `.git`, so the harness provenance
  records the build commit and a clean tree.
- Harness: the reviewed one at `feature/v9-AIUE-57-omp-ci-job` `8ee189d` (includes AIUE-46/49/52), cloned the same
  way; the case files and rate files come from that clone. The same harness for both builds.

## No-FMA evidence (x86-64)

- `gfortran --version`, the Fortran compile lines from the build log (flags actually used).
- `objdump -d` on every built extension (`*.so` of the `uedge` package): count `vfmadd*`/`vfmsub*`/`vfnmadd*`/
  `vfnmsub*` (FMA3/FMA4) and AVX (`ymm`) usage. Expected 0 on x86-64; on arm64 count `fmadd`/`fmsub`/`fnmadd`/
  `fnmsub`/`fmla`/`fmls` for contrast.
- `/proc/cpuinfo` flags of the emulated CPU (glibc's libm selects FMA variants of `exp`/`log`/`pow` at run time;
  these are pure functions of their arguments, so they cannot create a column-history difference, but it is stated).
- `ldd`: the extension links `libgomp`, not `libomp`.

## Runs (exact AIUE-54 commands; harness `cli.py flow`, `--cores 5 --max-jobs 1`)

Per build, in this order (Te box and full first so the essentials exist if time runs out):
1. `flow --configs tebox --threads 4 --repeats 20` (both arms) — K=20 Te box.
2. `flow --configs full --threads 4 --repeats 20 --arms jac` — K=20 full problem (AIUE-54 `k20_full` was jac only).
3. `flow --all --repeats 2` — 8 configurations × 2 arms × 2/4/8 threads (8 threads oversubscribe the 5 CPUs: valid
   for correctness, not for timing).

`--max-jobs 1`: full-problem runs one at a time (memory). Budget ~4 h for amd64; if the full K=20 does not fit,
reduce K and state it. Order of builds: amd64 `fix` (the decision-relevant one) and amd64 `base` interleaved by step.

## Analysis and records (follow AIUE-54)

- `docs/rca/AIUE-8-data/make_prefix_data.py` (AIUE-54) applied unchanged to the flow directories →
  `docs/rca/AIUE-8-data/linux/{records/<dataset>/…/<run>.json, runs.csv, stats.txt}` (renamed from
  `prefix_runs.csv`/`prefix_stats.txt` since it holds post-fix data too), plus each flow's `summary.md` as
  `flow_summary.md`. Datasets: `amd64_base_k20_tebox`, `amd64_base_k20_full`, `amd64_base_k2_all`, the same with
  `fix`, and `arm64_*` if run. `record.npz` stays in scratch.
- C1 gate: `docs/reviews/AIUE-56-c1-gate.py` (AIUE-56 branch) on every jac group (adapter: a check-layout directory of
  symlinks `serial` + `run*`) → `linux/c1_gate.txt`.
- `linux/build_info.txt`: image digest, compiler, flags, objdump counts, cpuinfo flags, ldd, build times.
- RCA document: a Linux column/rows in the AIUE-54 tables (matrix, K=20 rates) and in the AIUE-55 per-configuration
  table; the C2/M2-on-x86-64 answer under option D. Numbers verbatim from `stats.txt`/`runs.csv`.

## Acceptance

- AIUE-54 tables gain a Linux column from committed records.
- C2/M2 on x86-64 answered: post-fix bitwise agreement count per configuration × threads, with the no-FMA evidence.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` clean.

## Out of scope

No product code; no CI change; no `-march`/`-ffp-contract` builds (only the defaults the CI runner would build);
timing on emulated x86-64 is not a CI budget measurement and is reported only as such.
