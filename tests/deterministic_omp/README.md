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
  variables; `--itermx N` runs N Newton iterations instead of one evaluation (`ftol=1e20`).
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
  the `fnrm` sequence nksol printed. ±0 count as different and any NaN/Inf fails, except for the RHS probe of a
  parallel RHS, where `REDUCTION(+)` turns a serial −0.0 into +0.0, so ±0 are equal there (`--rhs-signed-zero-equal`
  overrides).
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
  recovered from the installed binaries (macOS Mach-O keeps no `.comment` section), so they are not recorded. Diagnostic switches (`CheckJac`, `CheckPandf1`, `ForceSerialCheck`) are never set
  by the harness.

Unit tests (no UEDGE build needed): `python -m pytest tests/deterministic_omp/harness`.

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
