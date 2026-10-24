# OpenMP Jacobian reproducer (AIUE-8)

This directory holds the case that shows the OpenMP Jacobian (`ppp.OMPParallelJac=1`) disagreeing with the serial
Jacobian, and changing from run to run, in the electron-energy (Te) rows. Epic: AIUE-8. PRD: Confluence page 1540097.
The test flow that compares OpenMP with serial (AIUE-49, AIUE-52) and the serial old-vs-new check (AIUE-53) build on
this case.

## The case

`case/input_mod4.py` is the owner's deck: upper single null, nx×ny = 70×42 (72×44 with guard cells), D plus carbon (`isimpon=6` while the arrays
are populated, then `isimpon=7` with `afracs`), drifts and potential on. It

1. restores the state from `b0p1.hdf5` and runs a populate `exmain` (`issfon=0`, `ftol=1e20`);
2. sets `issfon=1`, `ftol=1e-8`, the albedo/recycling settings and the diffusivities from `b0p1.hdf5`;
3. restores `save_input_mod4.h5` and raises the D⁺ diffusivity in the core/near-SOL region.

It does **not** call `exmain` at the end: the caller does. With all equations on, `neq = 44352` and the Jacobian
has 3 190 290 nonzeros. Every run prints two `iter= 0` lines: the first (`fnrm≈2.7e8`) is the populate `exmain` in
the deck, the second is the caller's.

| File | Content |
|---|---|
| `case/input_mod4.py` | The deck. The only change from the owner's copy: the rate directories (below). |
| `case/b0p1.hdf5` | Trimmed to `restore/bbb/{ngs,nis,phis,tes,tgs,tis,ups}` and `diffusivities/` (1.1 MB; the original was 11.7 MB) |
| `case/save_input_mod4.h5` | Trimmed to `bbb/{ngs,nis,phis,tes,tgs,tis,ups}`, which is all `hdf5_restore` reads (0.6 MB) |
| `case/gridue.hdf5` | Grid (`com.isgriduehdf5=1`) |
| `case/mist.dat` | POST93 carbon radiation data, read from the working directory by `api/apip93.m` |
| `case/testscript*.py`, `case/comp*.sh` | The owner's scripts, kept for reference (`testscript1.py`/`testscript2.py` need `uetools`) |
| `tools/trim_case_data.py` | How the two HDF5 files were trimmed |
| `tools/fingerprint.py` | SHA-256/`float.hex` fingerprint of one evaluation (yldot, jac, jacj, jaci, sfscal, suscal, fnrm) |
| `linux/` | AIUE-62: Dockerfiles and scripts for the Linux (libgomp) runs; run order in `linux/README.md` |
| `tools/scan_ompcopy.py` | AIUE-50: static coverage of the `OmpCopy*` copy of every `+threadprivate` variable, copy-order hazards, and a generated worker-vs-master checker for scratch builds |
| `tools/scan_shared_state.py` | AIUE-50: non-threadprivate variables written during a local `pandf` (before/after diff and sentinel) |
| `tools/scan_saved_locals.py` | AIUE-50: SAVE/DATA/COMMON locals in routines reachable from `pandf` |
| `tools/tsan_summary.py` | AIUE-50: groups ThreadSanitizer race reports by location |

The trimmed files give **bitwise the same** serial results as the originals: the `tools/fingerprint.py`
output and the printed `fnrm` lines match for the full problem (`ftol=1e20`), the Te box and three Newton
iterations (`itermx=3`). The check was run with the `--serial` build of `v9-develop` at `0fac655` on macOS arm64
with gfortran 15.

### Rate files

The deck needs `ehr2.dat` (hydrogen rates, `aph.aphdir`) and `C_rates.adas` (carbon rates, `api.apidir`). Both are
already tracked in the repository in `builder/test/Forthon_cases/Forthon_case5/`, and the deck points there by
default (a path relative to the deck file). To use another directory holding both files, set
`UEDGE_OMP_RATES_DIR`. **Set it whenever the deck is copied out of this tree** (a temporary run directory, for
example), because the default path is relative to the deck. `aphdir`/`apidir` hold at most 120 characters: in a
deeper checkout the deck falls back to the path relative to the working directory (a relative `UEDGE_OMP_RATES_DIR`
also works). The deck stops with an error if a rate file is missing or no form of the path fits. The case thus depends
on the legacy `builder/test/` directory; moving or deleting those files breaks it.

### Provenance of the data

The owner's originals (not committed) had SHA-256 `e0e4d590e415c3b6b4fbc73a8601fcc432bbed1f4c5e56786fb2806b7d9abaf5`
(`b0p1.hdf5`, 11.7 MB) and `0283e4b91c4266afe513b5c92134ac650654ad577b81cbfa9a48080ff4b032bc` (`save_input_mod4.h5`).
The state in them was written by UEDGE 8.1.2-beta.0. `tools/trim_case_data.py` applied to those files reproduces the
committed files byte for byte, and every kept dataset is byte-equal to the original one (checked in the AIUE-46
review).

## Environment

| Setting | Why |
|---|---|
| `OMP_STACKSIZE=512M` | During planning the OpenMP Jacobian crashed with SIGBUS at the default thread stack. The AIUE-46 review could not reproduce that at 4 and 8 threads, but per-thread automatic arrays scale with `neq`, so set it anyway. |
| `OMP_NUM_THREADS=N` and `ppp.Nthreads` | `Nthreads` is clamped to `OMP_GET_MAX_THREADS()`. Record both. |
| `HOME` set to an empty directory, `python -I` | `import uedge` runs `~/.uedgerc.py` or `./.uedgerc.py` if present, and `-I` also ignores `PYTHON*` variables. With `-I` the script's folder is not on `sys.path`, so add the case directory explicitly. |
| A fresh process per run | Forthon module state is global. |
| Build on macOS with gcc-15 | gcc-15's default C23 mode fails on `bbb/exmain.c`. Use `CC` set to Homebrew LLVM's clang (`/opt/homebrew/opt/llvm/bin/clang`, which also provides `libomp`), or `CFLAGS=-std=gnu17`. |

## Running it

Copy the case to a scratch directory and run from there:

```bash
cp -R tests/deterministic_omp/case /tmp/omp_case && cd /tmp/omp_case
export UEDGE_OMP_RATES_DIR=$OLDPWD/builder/test/Forthon_cases/Forthon_case5
export OMP_STACKSIZE=512M OMP_NUM_THREADS=4 HOME=/tmp/emptyhome
python -I $OLDPWD/tests/deterministic_omp/tools/fingerprint.py --tebox            # serial Te box (25 equations)
python -I $OLDPWD/tests/deterministic_omp/tools/fingerprint.py --tebox --omp-jac  # OpenMP Jacobian (needs the OpenMP build)
python -I $OLDPWD/tests/deterministic_omp/tools/fingerprint.py                    # full problem, ~30 s serial
```

`fingerprint.py` writes `fingerprint.json` in the working directory and prints the same object. Its `yldot` is the
residual `exmain` left, hashed before `get_fnrm()` re-evaluates the RHS serially, so with `--omp-jac` it shows the
solver's last residual, not a parallel-RHS evaluation (the harness of AIUE-49 has an explicit RHS probe). Use the file:
when stdout is redirected to a file, the Fortran runtime's buffered output can overwrite what Python printed.
The Fortran output also contains NUL bytes, so use `grep -a` on captured logs.

## Harness: does OpenMP equal serial, and where not?

`harness/` (AIUE-49) runs a configuration in a fresh process per run and compares the results bitwise. It needs only
the build's Python (numpy, h5py, uedge); it sets the environment itself (copied case, empty `HOME`, `python -I`,
`OMP_NUM_THREADS`, `OMP_STACKSIZE=512M`, `UEDGE_OMP_RATES_DIR` defaulting to the in-repo rate files).

```bash
PY=/path/to/venv/bin/python           # the build under test
H=tests/deterministic_omp/harness/cli.py
$PY $H check --preset tebox --arm jac --threads 4 --repeats 2 --python $PY --out /tmp/chk   # ~5 s
$PY $H check --preset full  --arm jac --threads 4 --repeats 2 --python $PY --out /tmp/chkf  # ~70 s
$PY $H run   --preset tebox --arm serial --python $PY --out /tmp/r1                         # one run
$PY $H compare /tmp/r1 /tmp/chk/run0 --json /tmp/cmp.json                                    # two runs
```

- **Presets** (`harness/config.py`): `full`, `tebox` (the owner's 25-equation box), `te`, `ti`, `ni`, `up`, `ng`
  (one group alone, other switches 0, `isphiofft=1`), `te_phi` (Te and phi). Phi alone fails in serial ("Jacobian
  row = 0"), and so do phi with ni+up, phi with ni+up+ti and the full problem without Te: phi runs only with Te, so
  while the Te bug exists a phi isolation can't get a verdict of its own.
- **Arms:** `serial` (both OpenMP switches 0, 1 thread), `jac` (`OMPParallelJac=1`), `jacrhs`
  (`OMPParallelPandf1=1`, which forces `OMPParallelJac=1`). `--ppp '{"OMPJacNchunks": -1}'` sets extra `ppp`
  variables; `--itermx N` runs exactly N Newton iterations instead of one evaluation (`ftol=1e20`).
- **Forced iterations** (`config.force_newton`, AIUE-169): an `--itermx N` run sets `ftol=1e-19` and `stptol=1e-30`,
  so nksol stops only at `itermx`, however converged the state is. At the deck's tolerances the `ni` and `ng`
  isolations start converged (iteration-0 fnrm ~1e-11 on Linux) and made no Newton step, which kept the nightly red,
  and how converged a state is depends on platform round-off. Both tolerances are needed (0 selects nksol's
  defaults): with only a tiny `ftol`, nksol stops on the step test (`iterm=2`, default `stptol` ≈ 3.7e-11), and a
  short step with a stale preconditioner skips the `itermx` test, so the run overshoots N (`svr/nksol.m` `nkstop`).
  `stptol` also sets the line search's minimum step (`lnsrch`, `inexct`), so a failing line search backtracks
  further before it gives up. Every record holds `iterm` (why nksol stopped: 1 ftol, 2 stptol, 3 line search,
  4 `itermx`), `ftol` and `stptol`. Near convergence the forced iterations run at the noise floor: tiny steps, still
  compared bitwise.
- **`check`** runs a serial reference of the same build and K ≥ 1 OpenMP runs, and reports agreement with serial and
  determinism (run 0 vs run k) separately. The ticket's measurement is `--itermx 3` (several Jacobians and the
  fnrm sequence); the default (one evaluation) is the fast check. Each record says how many Jacobians were made
  (`ijactot`, the capture list) — an "it0" run can still iterate when the iteration-0 residual exceeds `ftol`. It writes `check.json` with every report and the provenance (commit,
  platform, thread and chunking settings).
- **What is compared, bitwise** (`harness/compare.py`): every Jacobian the run produced, as sets of (row, column)
  entries: the raw Jacobians of AIUE-47's capture hook (`bbb.jaccapture`, one per `sfsetnk`/`psetnk` call, before
  scaling, row normalisation and reordering; recorded with the routine that produced them, `jac_calc` or
  `jac_calc_parallel`) when the build has the hook, and the post-`exmain` `bbb.jac` arrays always. So a
  changed sparsity pattern shows up as entries "only in a/b"; `sfscal`, `suscal`, `yldot`; one more RHS evaluation
  through the solver path (`ffun`, the parallel RHS on the `jacrhs` arm); the final `get_fnrm()` as `float.hex`; and
  the `fnrm` sequence nksol printed. ±0 count as different and any NaN/Inf fails, except in `yldot` and the RHS
  probe when a run used the parallel RHS, where `REDUCTION(+)` turns a serial −0.0 into +0.0, so ±0 are equal there
  and counted as `signed_zero_differences` (`--rhs-signed-zero-equal` overrides).
- **Localisation:** every mismatch is mapped through `igyl` and the `idx*` tables to equation, species and cell, and
  counted per (row equation, column equation) pair, e.g. `te/ni: 387007; first value row te(ix=1,iy=1) col
  ni[0](ix=1,iy=1)`.
- **Is it really the arm it claims?** Every comparison first checks each record (`compare.check_arm`): OpenMP arms
  need `ParallelJac=1` (and `ParallelPandf1=1` plus a parallel RHS probe on `jacrhs`), captured Jacobians from
  `jac_calc_parallel`, an OpenMP runtime in the build; the serial arm needs all four switches 0; `Nthreads` and
  `OMP_NUM_THREADS` must equal the requested threads; `CheckJac`/`CheckPandf1`/`ForceSerialCheck` must be 0. Any
  violation (e.g. `--python` pointing at a serial build) is a harness error, never AGREE.
- **Strictness:** `yldot`, `sfscal`, `suscal`, the equation maps and the iterations are mandatory; a quantity present
  in one record only, a duplicate CSR entry, or a different number of Jacobians is a mismatch; a different problem
  (neq, preset, itermx, equation map) or an out-of-range index is a harness error. The post-`exmain` Jacobian after a
  `psetnk` is RCM-permuted (`ireorder=1`): it is compared by position and labelled "permuted indices", not mapped to
  cells; the raw captured Jacobians are always in natural order.
- **Provenance:** the build under test (the installed uedge's source tree from pip's `direct_url.json`, its git HEAD
  and dirty state read at run time, a SHA-256 over the extension modules, whether they link an OpenMP runtime, and
  the compiler string where the binaries keep one — Linux/ELF; empty on macOS), the harness commit and
  dirty state, Python and platform, and every OpenMP and chunking switch.
- **Exit codes:** 0 everything agrees, 1 at least one mismatch, 2 harness error (missing or corrupt file, failed run,
  wrong arm, any unexpected exception).
- **Capture slots:** `RunSpec.capture` (default 16) raw Jacobians are kept; a run that produces more is a harness
  error, never a silent truncation. A build without the hook compares the post-`exmain` Jacobian only.
- **Limits:** the per-iteration `fnrm` is available only as the 16 digits nksol prints. `fnrm_final` is
  `get_fnrm()` at the final state: the serial `pandf` residual times `sfscal`, a fingerprint of the final state, not
  nksol's own value on the `jacrhs` arm. The RHS arm is checked through the `exmain` residual and one RHS probe
  (`ffun`) after `exmain`, not through every parallel RHS evaluation of the solve. The compiler and its flags can't be
  recorded on macOS (Mach-O binaries keep no `.comment` section); on Linux/ELF builds the compiler string is recorded,
  the flags never are. `provenance.build.extensions_sha256` (a SHA-256 over the extension modules) is what identifies
  the binary under test. Diagnostic switches (`CheckJac`, `CheckPandf1`, `ForceSerialCheck`) are never set
  by the harness.

Unit tests (no UEDGE build needed): `python -m pytest tests/deterministic_omp/harness`.

## Test flow: the configuration matrix with per-arm verdicts

`cli.py flow` (AIUE-52, `harness/flow.py`) runs a set of configurations on both OpenMP arms at several thread
counts, K fresh-process repeats each, against **one serial reference per configuration** of the same build, and
gives **one verdict per arm**:

```bash
$PY $H flow --configs tebox --threads 4 --python $PY --out /tmp/flow_tebox   # Te box, ~5 s: "where does it differ?"
$PY $H flow --python $PY --out /tmp/flow                                     # quick set: tebox, full at 2, 4 threads
$PY $H flow --all --python $PY --out /tmp/flow_all                           # every configuration at 2, 4, 8 threads
$PY $H flow --list                                                           # the configuration table
```

- **Configurations** (`flow.CONFIGS`): `tebox`, `full`, `te`, `ti`, `ni`, `up`, `ng`, `phi`. `phi` is the potential
  isolation; its preset is named once, in `flow.PHI_PRESET` (`te_phi`). `--configs`, `--threads`,
  `--arms jac,jacrhs` and `--repeats K` (default 2) select the matrix; duplicates are dropped, and empty lists or
  values below 1 (`--threads`, `--repeats`, `--cores`, `--max-jobs`) are rejected before anything runs (exit 2).
- **phi has no verdict of its own while the Te Jacobian bug exists.** phi cannot be isolated from Te on this case,
  so the `phi` group fails on its Te rows whatever phi does. Read phi from the "mismatch rows" column: `te` alone
  means the phi rows agreed. Whether phi should get its own verdict (a Te-restricted preset, or a verdict per row
  equation) is open for the owner (review AIUE-52 round 1, I1-m4).
- **Group verdict** (configuration, arm, threads): PASS when all K runs agree bitwise with serial **and** with each
  other (the first successful run vs every later one). An OpenMP run that fails in the build while the serial
  reference ran (UEDGE error or solver stop, crash by signal, non-zero exit, timeout) is a FAIL. ERROR (harness,
  cannot judge) is: a failed serial reference; a run whose record fails `compare.check_arm` against the spec the
  flow requested (the check described under "Is it really the arm it claims?" above, so a serial build gives ERROR,
  never PASS); a comparison report with `errors` (missing quantity, different problem, wrong arm), shown with its
  first error; an unreadable or truncated record (`unreadable record.json/npz`); a harness-side failure (existing run
  directory, `OSError`, a Python error in the worker or driver). **Arm verdict:** ERROR if any group is ERROR, else
  FAIL if any group fails, else PASS.
- **Exit code** (`--gate`, default `jac`): 2 if a gated arm is ERROR, 1 if a gated arm FAILs, 0 otherwise; the other
  arm is still run and reported. `--gate jacrhs` and `--gate all` gate on that arm or on both, `--gate none` only
  reports (0). Bad arguments, an existing `--out`, or a gate with nothing to judge give 2.
- **Concurrency:** runs share a core budget (`--cores`, default all cores; a run takes `threads` cores, serial 1)
  and at most `--max-jobs` (default 8; a full-problem run peaks at ~1.4 GB) run at a time. Serial references and the
  expensive configurations start first. `--max-jobs 1` runs everything one after the other. Ctrl-C sends SIGTERM to
  the running workers and exits with 130.
- **Output** in `--out`: `summary.md` (also printed: configuration, arm, threads, verdict, runs agreeing with serial,
  deterministic, row equations with mismatches, failing sections, first mismatch with equation and cell),
  `flow.json` (settings, provenance, timings, verdicts, every comparison report), and the run directories
  `<config>/serial` and `<config>/<arm>_t<threads>/run<k>`.

On `v9-develop` (`0fac655`, macOS arm64, gfortran 15, K=2, 2/4/8 threads) the Jacobian arm fails for `tebox`,
`full` and `te` with mismatches only in Te rows that also differ between repeats, and passes for `ti`, `ni`, `up`,
`ng`; with Te and phi, only Te rows differ. The Jacobian + RHS arm passes for `ti`, `ni`, `up`, `ng`, fails for `tebox`
and `full` (also in the Te rows of `yldot`), and crashes for `te` and Te + phi. The AIUE-52 validation record is
kept in the tag `archive/AIUE-8-docs` (`git show archive/AIUE-8-docs:<path>`; find the path with
`git ls-tree -r --name-only archive/AIUE-8-docs | grep AIUE-52-validation`); the results are summarised on the
Confluence page "Validation summary: AIUE-8 tickets" (space SD, under the AIUE-8 PRD).

## Serial old-vs-new check: does a change leave serial results bit for bit as they were?

`harness/serial_check.py` (AIUE-53) is the "nothing may change" gate of epic AIUE-8. **Run it for every PR that
touches Fortran (`*.m`, `*.F90`, hand-written `*.f`), a `.v` file or `ppp/`**, and paste its build lines, its
`RESULT` line and any `first mismatch` lines into the PR. Only `RESULT: AGREE (bitwise identical; complete gate)`
meets the gate. A tolerance-based regression suite (`rtol=1e-5`) is no substitute.

It takes four interpreters: the `--serial` build and the default (OpenMP) build of the base (`v9-develop`) and of the
change. Build them in separate venvs from clean, committed trees first (`pip install . -C "--build-option=--serial"`
and `pip install .`; the tool does not build). Then:

```bash
H=tests/deterministic_omp/harness/serial_check.py
python $H --base-python BASE_SERIAL/bin/python --new-python NEW_SERIAL/bin/python \
          --base-omp-python BASE_OMP/bin/python --new-omp-python NEW_OMP/bin/python \
          --jobs 4 --out /tmp/serial_check          # --cases all is the default; ~10 min (both pairs, --jobs 4)
python $H ... --cases quick --partial-ok --out DIR  # a quick look while developing (~40 s), not the gate
python $H --list                                    # the case set
```

- **What runs:** every case once per build, each in a fresh `python -I` process with an empty `HOME`, on the serial
  path: `ppp.OMPParallelJac = ppp.OMPParallelPandf1 = 0`, `Nthreads = 1`, `OMP_NUM_THREADS = 1`, the diagnostic
  switches 0. `compare.check_arm` verifies this in every record, and a record that shows anything else is a harness
  error. Pair `serial` compares the two `--serial` builds, pair `omp0` the two OpenMP builds with both switches 0
  (both builds have the `ppp` package).
- **Evaluation cases** (`ftol=1e20`: one RHS and the `sfsetnk` Jacobian):
  - `repro-<preset>` for every preset of `harness/config.py`.
  - `yldot-*` (AIUE-106): a family of the yldot suite, `tests/yldot/families/<family>/`, run by
    `harness/family_worker.py`. The worker imports `uedge` in the empty run directory, changes to the family
    directory (the decks read `../../data` by relative paths), execs `input.py` and then the case's settings file, if
    it has one. It then sets the serial arm, allocates, restores the family's `reference_state.h5`, sets
    `restart=1`, `issfon=1`, `ftol=1e20` and runs `exmain()` twice. `com.iprint` stays as the deck sets it, so the
    `fnrm` lines are printed.
  - Families: `d_only`, `d_c` (D+C on the 16x8 mesh; it stands for the 8x4 D+C unit case too), `d_mols`, `ortho`
    (orthogonal mesh) and `slab_phi`.
  - Settings variants: `yldot-d_only-<v>` (19) and `yldot-d_mols-<v>` (2), each turning on boundary-condition,
    transport or drift switches. A settings file in `settings/<family>/<v>.py` holds the lines the upstream
    regression suite's variant deck adds to its default deck, in order (taken once from `origin/pytests` f695acd;
    its header names the deck). The two drift decks (`tg_atom_drifts`, `tg_mol_atoms_drift`) are in this form too and
    start from the family state, which is not converged for drifts. Owner decisions of 2026-10-24 (AIUE-106 ticket
    page): the settings form, `reference_state.h5` for every case, `d_c` for both D+C cases, the owner families by
    name only. Never edit a value in a settings file to make a case pass.
- **Solver cases** (`-itN`): exactly N Newton iterations (forced, as `--itermx` above), so `psetnk` (row normalisation, `jac_reorder`),
  the ILU preconditioner, the Krylov solve and the line search run too. The whole `fnrm` sequence is compared,
  together with the final state (`yldot`, `fnrm` at the final `yl`) and every Jacobian. A solver case whose record
  shows fewer than 2 printed iterations, or a post-`exmain` Jacobian not from `psetnk`, is an ERROR: it would
  silently cover only the evaluation path.
  - Reproducer: `repro-tebox-it5`, `repro-te-it3`, `repro-full-it3`.
  - Families: `yldot-{d_only,d_c,d_mols,slab_phi}-it5`. These run the final `exmain` with `itermx=5` and the forced
    tolerances.
- **Case sets:** `all` (the default, and the gate) is everything above, 41 cases. `quick` = `repro-tebox`,
  `repro-tebox-it5`, `yldot-{d_only,d_c,d_mols}`, `yldot-{d_only,d_c}-it5`.
  - Ad hoc names: `repro:<preset>[@itN]` and `yldot:<family>[+<settings>][@itN]`.
  - The owner families `large_dd2c`, `dnull_imp2` (double null) and `imp7` (neq 27k-44k) are not in `all`; they run
    by name (`yldot:dnull_imp2`) once `python tests/yldot/tools/fetch_data.py` has fetched their states. Without the
    data the case is a harness error that says so.
- **No regression-suite checkout** is read: the families, their states and the settings files are in this
  repository.
- **What is compared:** `compare.compare_records` (above), bit for bit:
  - **Raw captured Jacobians:** every `sfsetnk`/`psetnk` Jacobian captured by the AIUE-47 hook, when both builds
    have the hook. If only one has it, nothing is captured on either side and a warning says so.
  - **The post-`exmain` `bbb.jac`:** the `sfsetnk` Jacobian times `1/suscal`, or after iterations the last `psetnk`
    one (compared by position when `jac_reorder` permuted it).
  - **Vectors and norms:** `sfscal`, `suscal`, `yldot`, one more RHS through `ffun`, the final `fnrm` (`float.hex`)
    and the printed `fnrm` sequence.
  - ±0 differ and any NaN/Inf fails.
  - **Limit:** the scaled Jacobian is not equivalent to the raw one, because multiplying by `1/suscal` can round away
    a 1-ulp raw difference. Until both builds have the AIUE-47 hook (base `v9-develop` does not yet), such a
    difference can hide in an evaluation case. It still shows in the solver cases if it changes anything downstream.
- **Build and source guard:** each interpreter is probed first (`harness/build_probe.py`). The probe records:
  - the path, `uedge.__file__` and version, the SHA-256 of every compiled extension, and whether it is an OpenMP
    build;
  - whether it has the capture hook;
  - the source tree pip installed it from (`direct_url.json`), with that tree's git HEAD and dirty state. These are
    read when the check runs, not at build time, so build from a clean committed tree and don't touch it until the
    check is done.

  Harness errors (exit 2):
  - a serial build in the `omp0` pair, or an OpenMP build in the `serial` pair;
  - base and new that are the same build, the same source tree, or the same clean commit (`--allow-same-build`
    overrides this, for self-tests, but the run is then not the gate);
  - a record whose build differs from the probed one (for example, a reinstall during the check).

  Not the gate (`RESULT: INCOMPLETE`, exit 2; with `--partial-ok` `AGREE, PARTIAL`; the RESULT line names the
  reason):
  - an unknown source on either side. A wheel or PyPI install has no source directory, so the same-source and base
    checks cannot run, and two rebuilds of one commit always differ in their extension hashes;
  - a dirty tree, or one whose dirty state could not be read: the provenance cannot be reproduced;
  - a base HEAD that is not `origin/v9-develop` or an ancestor of it, or whose ancestry check failed. Stacked-branch
    comparisons therefore need `--partial-ok`;
  - a build whose extensions are older than its source tree's HEAD commit. The tree was committed after it was
    built, so the recorded HEAD may not be what was built: reinstall.

  Warnings: serial and OpenMP builds from different commits (a stale build gets its own wording), and the same
  commit in base and new that differs only by uncommitted changes.
- **Output:** `serial_check.json` (builds, sources, cases, every report, `gate_complete`, `incomplete`) and
  `summary.txt`. The summary has three build lines per build and one line per case, with the number of iterations
  and of Jacobians compared. For a mismatch it adds the first mismatching quantity with its first entry, located
  through `igyl`, and the per-section counts. For an error it gives the cause, which is the last traceback line plus
  UEDGE's last error line. The runs are in `<pair>/<base|new>/<case>/`. `record.npz` of agreeing cases is deleted
  unless `--keep-records`.
- **Exit codes:**
  - 0: the complete gate agrees: both pairs, two different builds from clean committed trees with known sources,
    base on `origin/v9-develop`, and every case of `all`.
  - 1: at least one mismatch.
  - 2: a harness error (bad build pair, missing case or family data, a failed run, a record that is not on the
    serial path, any unexpected exception), or an incomplete gate. An incomplete gate prints
    `RESULT: INCOMPLETE ... not the gate` and lists what was skipped. `--partial-ok` turns an agreeing incomplete run
    into exit 0, `RESULT: AGREE, PARTIAL`.
  - A harness error wins over a mismatch.

The owner's original check, from inside a copy of `case/` (with the environment above):

```bash
./comp.sh          # runs testscript.py twice (OpenMP build); different "iter= 0 fnrm=" lines mean non-determinism
```

### Reference values (serial, `v9-develop` `0fac655`, macOS arm64, gfortran 15)

| Configuration | neq | printed iteration-0 `fnrm` | `get_fnrm()` after `exmain` |
|---|---|---|---|
| Full problem, `ftol=1e20` | 44352 | `1.918820629111277` | `0x1.eb37d428ec4f0p+0` |
| Te box, `ftol=1e20` | 25 | `0.3221264477609989` | `0x1.49db83f93d961p-2` |
| Full problem, `itermx=3` | 44352 | 1.918820629111277, 1.836097068513709, 1.782757715864211, 1.762443625980891 | `0x1.c32f8166a1af7p+0` |

These values are for orientation. Bitwise comparisons are always made against a reference run of the same build on
the same machine, never against this table.

## CI: `build-test-omp.yml` (AIUE-57)

`.github/workflows/build-test-omp.yml` builds the **default OpenMP build** (`pip install -v .`; since AIUE-64 the
Linux build links the extensions with `-fopenmp` itself, so no `LDFLAGS` is needed) on `ubuntu-latest` (4 vCPUs) with
Python 3.11, `numpy==1.26.4` and `h5py`, and calls `tests/deterministic_omp/ci/run_omp_ci.sh`. The script holds every
CI step, so the same steps run locally:

```bash
PYTHON=/path/to/omp-venv/bin/python tests/deterministic_omp/ci/run_omp_ci.sh pr        # the PR set
PYTHON=... OMP_CI_GEN_DIR=$(tests/deterministic_omp/ci/gen_dir.sh /path/to/built/tree) ... run_omp_ci.sh pr  # + common-block check
PYTHON=... OMP_CI_CORES=4 OMP_CI_MAX_JOBS=2 OMP_CI_OUT=/tmp/omp-ci tests/deterministic_omp/ci/run_omp_ci.sh nightly
PYTHON=... OMP_CI_FLOWS='tebox1|tebox|4|2|jac|none|{"OMPJacMinChunkLen": 1}' tests/deterministic_omp/ci/run_omp_ci.sh
PYTHON=... OMP_CI_JAC_TOLERANCE=1e-6 ... run_omp_ci.sh pr       # macOS: tolerance mode (C2), see below
```

Steps: the harness and CI unit tests (`harness/`, `ci/`, no build needed); an import smoke test (empty `HOME`,
`python -I`); a pre-flight check that every key of the flows' `ppp` fields exists in the build (`ci/ppp_keys.py`;
exit 2 naming the key); the **common-block check** (`ci/common_check.py`, AIUE-60's G-common check: the Forthon `--omp`
common block `/ompcommonscalarcopy/` must be defined first by `bbbpy` and no later definition may be larger), run when
`OMP_CI_GEN_DIR` names the build's generated sources (the workflow sets it with `ci/gen_dir.sh`, which requires
exactly one `build/temp.*` with `bbb_p.F90`); the AIUE-52 flow for the selected set; the **C1 bound**
(`ci/jac_bound.py`) on every flow; and `ci/report.py`, which writes the combined `summary.md`, appends it to
`$GITHUB_STEP_SUMMARY`, annotates the run and sets the exit code. The rate files are the tracked ones in
`builder/test/Forthon_cases/Forthon_case5/` (AIUE-46); nothing is downloaded. The harness sets `OMP_STACKSIZE=512M`.

A flow spec is `name|configurations|threads|K|arms|itermx|ppp`; `ppp` is JSON passed to the flow as `--ppp` (every
run, serial included). The Te-box flows set `{"OMPJacMinChunkLen": 1, "OMPJacVerbose": 1}`: with the AIUE-61 fixed
partition (`OMPJacFixedChunks=1`) the chunk count is `min(OMPJacNchunksFixed, max(1, neq/OMPJacMinChunkLen))`, so the
25-equation Te box gets **one** chunk by default, which is serial-equivalent and tests nothing; `OMPJacMinChunkLen=1`
gives it 25 one-column chunks on the default code path. `OMPJacVerbose=1` makes every run print its `NchunksJac` to
`run.log`; `report.py` lists the values (`CHUNKS` lines; 25 expected for the Te box).

| Trigger | Set | Flows (in run order; one serial reference per configuration and flow) | Timeout |
|---|---|---|---|
| `pull_request`, `push` to `v9-develop`/`main`, manual `pr` | `pr` | `tebox1`: Te box, 2, 4 threads, K=3, arm `jac`, **one evaluation**, 25 chunks; `tebox`: Te box, 2, 4 threads, K=5, arms `jac` and `jacrhs`, `--itermx 3`, 25 chunks; `up1`: `up` alone, 4 threads, K=3, `jac`, one evaluation (default 21 chunks; where M3 showed before AIUE-61); `full`: 2, 4 threads, K=2, arm `jac`, `--itermx 3` (default 64 chunks) | 30 min (budget 20) |
| `schedule` (03:17 UTC daily), manual `nightly` | `nightly` | `all1`: `--all` (every configuration at 2, 4, 8 threads), K=2, both arms, one evaluation, default partition; `tebox1`: Te box, 2, 4, 8 threads, K=3, both arms, one evaluation, 25 chunks; `all`: `--all`, K=3, both arms, `--itermx 3` | 150 min |

Every flow is gated the same way. The one-evaluation flows locate a defect (their post-`exmain` Jacobian is in
natural order, so the first mismatch is a cell); the `--itermx 3` flows test the Newton path (several Jacobians,
the `fnrm` sequence). Other branches run through their pull request only, so a push to a PR branch does not start
a second, duplicate run. Superseded pull-request runs are cancelled; runs on `v9-develop`/`main` always finish.
The workflow has `permissions: contents: read`.

- **Gating (bitwise on Linux).** The Jacobian arm (`jac`) gates: the job is red when any `jac` group is not bitwise
  equal to serial in all K runs and between runs (exit 1), or when the flow cannot judge (exit 2: failed serial
  reference, an arm that did not take effect, a failed smoke or unit test). On Linux x86-64 the AIUE-61 fixed
  partition is bitwise equal to serial (AIUE-61 R5, AIUE-62; emulated x86-64), so bitwise is the gate there. The
  Jacobian + parallel RHS arm (`jacrhs`) is **report-only**: its known defects are epic AIUE-70 (AIUE-58 R1–R4,
  AIUE-74); its failures appear as warnings and in the summary but do not set the exit code. `OMP_CI_GATE` selects
  the gated arm (`jac`; `all` or `jacrhs` need `jacrhs` in every flow, so they fit only `nightly`).
- **C1 bound, a backstop.** `ci/jac_bound.py` applies AIUE-56's C1 bound to every `jac` run: Te-row magnitude
  ≤ 10 × serial, and every differing entry within 1e-6 × the serial row max, on the **scaled `post_exmain`**
  Jacobian (the matrix the bound was registered on; the raw captured Jacobians are unscaled and are only printed,
  "not judged"). `post_exmain` is the **last** Jacobian of each run: in the one-evaluation flows the first and only
  one; in `--itermx` flows the last, permuted `psetnk` one (bounded against the global max, since its rows are not
  equations); earlier Jacobians are compared bitwise by the flow. A run outside the bound is a gated failure even if
  the flow passed bitwise; a failing group's line says `C1 bound: within` (round-off class) or `EXCEEDED` (a real
  defect such as C1). A missing `bound.json`, group or run entry, or a bound error is exit 2 (fail closed).
- **Tolerance mode (`OMP_CI_JAC_TOLERANCE`, for macOS).** Empty (the workflow's value): bitwise. A value V in
  (0, 1e-6] (capped at the registered C1 bound): in a **one-evaluation** flow (where `post_exmain` is the only
  Jacobian; `--itermx` flows always stay bitwise), a `jac` group that FAILed bitwise counts as **PASS (within
  tolerance V)** only if no run failed, the group is deterministic, every failing section is a Jacobian section,
  and every run is within the bound computed with V; otherwise it stays FAIL. On macOS arm64 the C2 round-off
  remains (full problem 12 275 Te-row entries, worst 4.59e-9 × row max; Te box with 25 chunks 2 entries, 5.6e-10),
  so local replays there need it; on macOS the `--itermx` flows therefore stay red in this mode as well.
- **Common-block check.** Its result (PASS, FAIL, ERROR or skipped) is in the summary (`COMMON-BLOCK` line) and in
  the exit code; the flows run whatever it says, so the summary always shows both.
- **What a failure says.** First one `FIRST MISMATCH` line (and an `::error::` annotation) for the job: the
  configuration, arm, threads, equation and cell of the first mismatch, taken from a one-evaluation group when one
  failed, e.g. `FIRST MISMATCH: configuration tebox, arm jac, threads 2, equation te, cell (ix=4,iy=20) (flow
  tebox1)`. The `FIRST MISMATCH` line is left out when no gated group has a cell location (e.g. a defect seen only in
  the full problem, or an intermittent one that the one-evaluation group happened to miss); the job is still red. Then
  one `GATED` line (and annotation) per failing group, in run order, with the same fields, how many
  runs agreed, the flow's raw first-mismatch text and the C1-bound result. A group whose runs all crashed says so
  (`no comparable mismatch, the OpenMP run(s) failed; ... exited with -11`); an ERROR group (cannot judge, e.g. the
  core's `check_arm` refusing a run of a serial build) gives its reasons and exit 2.
- **`--itermx 3` and the permuted Jacobian.** After Newton iterations the post-`exmain` Jacobian is the `psetnk`
  one: row-normalised and RCM-permuted (`ireorder=1`). The harness core compares it **by position** (section
  `jacobian:post_exmain (permuted indices)`, positions such as `position 12`, not cells), and that comparison is
  part of the gate's verdict like every other section: a bitwise difference at any position fails the group.
  Such a first mismatch has no cell, so `ci/report.py` names the location found by the one-evaluation group of the
  same configuration, arm and threads (`located by the one-evaluation group [tebox1]: equation te, cell
  (ix=4,iy=20)`). Only when there is none does it give the first differing entry that maps to a cell, labelled as
  what it is: `first cell-mapped differing entry (may be downstream of the defect): equation te, cell (ix=3,iy=18)
  [yldot]`. Once the Newton path has moved, `sfscal`/`yldot` differ in every cell, so that entry is just the lowest
  index, not the defect; it is never used for the `FIRST MISMATCH` line. On the full problem it can be an `ni` row.
- **Newton iterations are checked.** For an `--itermx N` flow, `report.py` reads each serial reference's
  `record.json` and fails the job with exit 2 unless it made exactly N Newton iterations (the largest
  `iterations[].iter`), so a set never claims iterations it did not run. OpenMP runs that iterate differently
  already fail the comparison (`fnrm_printed`). Since the iterations are forced (AIUE-169), this catches only an
  early nksol stop (a line-search or Krylov failure) or an overshoot past `itermx`; the message gives the
  record's `iterm`.
- **Artifacts** (`actions/upload-artifact@v4`, also on failure, 30 days): the combined and per-flow `summary.md`,
  `flow.json`, `bound.json`, `ci.log`, `timing.txt` (job and build wall time), and every run's `run.log`,
  `record.json`, `spec.json`. The compared arrays (`record.npz`, ~60 MB per full-problem run) are not uploaded;
  rerun locally.
- **Budget.** The PR job is estimated at about 15–22 min (central ~18; the nightly set about 90–120 min within its
  150-min timeout) on `ubuntu-latest` (derivation in the AIUE-57 validation record, kept in the tag
  `archive/AIUE-8-docs`; all local timings are from a loaded Mac or emulated x86-64, so they are not a prediction); the `Wall time` step writes the measured job
  and build time to the step summary. If it runs over 20 min, cut the `pr` set in `run_omp_ci.sh` in this order:
  drop `up1`, then `tebox` K=5 → 3, then `full` at 4 threads only; the nightly set keeps the full matrix.
- **Replaying the job on Linux.** `tests/deterministic_omp/linux/run_ci_replay.sh` runs these steps in the Ubuntu
  24.04 image (`linux/README.md`).
- **Merge condition.** The workflow merges with or after `bugfix/v9-openmp-determinism-fix` (the fixes it tests), and
  only once the first native `ubuntu-latest` run of its PR is green and inside the budget (all earlier Linux
  evidence ran emulated). If native x86-64 shows C2-like round-off entries, the owner decides.
- **The nightly set is not yet validated on Linux.** Linux bitwise equality with the fixed partition has been shown
  (emulated) for the Te box (25 chunks), `full` and `up` only; the other `--all` configurations (`te`, `ti`, `ni`,
  `ng`, `te_phi`) at 2/4/8 threads, and the nightly `--itermx 3` runs, were never run on Linux. A red first nightly
  is therefore not necessarily a regression: read its summary (bound `within` = round-off class, `EXCEEDED` = a
  defect) and let the owner decide (fix, make that configuration report-only, or accept a tolerance). A manual
  `workflow_dispatch` with `set: nightly` right after the merge gives that answer early.
- **Scheduled runs** start only from the repository's default branch; until the workflow is there, use the manual
  `workflow_dispatch` with `set: nightly`.
- Exit codes of `run_omp_ci.sh`: 0 the gated arm agrees (or is within tolerance), within the bound, common block
  PASS or skipped; 1 a gated mismatch, a bound or a common-block FAIL; 2 setup or harness error.
