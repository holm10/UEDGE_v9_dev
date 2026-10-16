# OpenMP RHS/Jacobian and local evaluation — the risky pattern

Most subtle bugs in v9 come from here (see recent commits: "Fixes X-point boundaries for RHS OMP",
"Fixes RHS padding for arbitrary chunking", "Fixes core boundary X-pt cut padding").

## Two evaluation modes of `pandf` (`bbb/pandf.m:513`)

- **Full RHS:** `xc = yc = -1`.
- **Local (Jacobian column):** `xc, yc ≥ 0` — `initialize_ranges` (`bbb/pandf.m:31-248`) shrinks loop bounds
  `i1..i8`, `j1..j8` (module `Selec`) to a stencil box around the perturbed cell using `xlinc`, `xrinc`, `yinc`.
  Every loop in the `pandf` tree must use these ranges, or the Jacobian is either wrong (too small) or slow (too big).
- `jacobian_store_momentum` / `jacobian_store_volsources` save/restore state between columns (`bbb/pandf.m:565-568`).

## OpenMP parallelism (`ppp/`)

- Switches in `ppp/ppp.v`: `OMPParallelPandf1` (RHS, `ppp/ppp.v:6`), `OMPParallelJac` (Jacobian, `ppp/ppp.v:7`), `Nthreads` (`ppp/ppp.v:14`).
- RHS: `OMPPandf1Rhs` (`ppp/omp_parallel.F90:902`) splits the grid into bulk chunks plus special **X-point
  chunks** (`Make2DChunks`, `ppp/omp_parallel.F90:3`), runs `OMPPandf`/`OMPPandf_XPT` per chunk with `FIRSTPRIVATE(ylcopy,yldotcopy)`,
  and sums only the `iv` indices each chunk owns (`REDUCTION(+:yldottot)`).
- Jacobian: `jac_calc_omp` / `OMPJacBuilder` (`ppp/omp_parallel.F90:495`, `ppp/omp_parallel.F90:645`) — each thread builds columns with its own copy of
  module state; `Selec` ranges are `copyin`'d (`ppp/omp_parallel.F90:649`, `ppp/omp_parallel.F90:715`).
- Per-thread copies of module variables come from `+threadprivate` in `.v`. The `OmpCopy<pkg>` modules used by
  `ppp` are generated at build time (Forthon `--omp`, `setup.py` `OMPargs`), not stored in the repo.

## Raw-Jacobian capture (`bbb.jaccapture`, off by default)

`bbb.jac` after `exmain` is not the matrix `jac_calc` returned: `sfsetnk` scales its columns by `1/suscal`,
and `psetnk` also scales rows by `sfscal`, normalises rows and factorises it. To get the unscaled matrix, set
`bbb.jaccapture = K` (group `Jacobian_capture`, `bbb/bbb.v:4221`). `jac_calc_interface` (`bbb/oderhs.m:4676`) then
copies each CSR Jacobian returned by `jac_calc` or `jac_calc_parallel` (`bbb/oderhs.m:4716`, routine
`jac_capture` at `bbb/oderhs.m:4738`) into slots `1..bbb.jaccapn`:

- What is captured is the `jac_calc`/`jac_calc_parallel` output: finite-difference `d(yldot)/d(yl)` including the
  `-1/dtuse`, `-1/dtphi` and `-nufak` diagonal terms, with entries `|J*sfscal| <= jaccliplim` dropped (serial
  `jac_calc` uses `sfscal` of the row, `ppp/parallel.F90` `LocalJacBuilder` of the column), so the pattern
  depends on `sfscal`.
- Python: `bbb.jaccapv[:nnz,k]`, `bbb.jaccapj[:nnz,k]`, `bbb.jaccapi[:neq+1,k]` with `nnz = bbb.jaccapnnz[k]`
  and `neq = bbb.jaccapneq[k]`. These use the same 1-based CSR convention as `jac/jacj/jaci`.
- `jaccapsrc[k]`: 1 = `jac_calc`, 2 = `jac_calc_parallel` (`bbb/bbb.v:4261`). With `ppp.ForceSerialCheck>0`,
  `jac_calc_parallel` returns a serial result. `jaccapfrom[k]`: 1 = `sfsetnk`, 2 = `psetnk` (`bbb/bbb.v:4264`).
  `jaccapseq[k]` is the Jacobian's sequence number.
- Stores the Jacobians numbered `jaccapskip+1 .. jaccapskip+jaccapture`. `jaccapture=1, jaccapskip=k-1` keeps
  only the k-th. `exmain` does not reset the counters; set `jaccapcount = jaccapn = 0` to restart, and also after
  `bbb.gfree("Jacobian_capture")` (the stored slots are gone; the next capture reallocates zero-filled arrays).
- Memory: slots are allocated as they are filled (`jaccapnslot` doubles, capped at `jaccapture`, which is only a
  cap). Each slot is about `16*nnz + 8*(neq+1)` bytes (8-byte reals and integers): ~51 MB on the 44352-equation
  reproducer. A growth briefly holds the old and the new arrays; a failed allocation makes Forthon exit.
- Only `sfsetnk` and `psetnk` (the `nksol` path) call `jac_calc_interface`. The Jacobian routines of the
  other solvers (`jacd1`, `jacd2`, `jacnw`, `jacvd`, `FPRECO`) call `jac_calc` directly and are not captured.
- The capture runs on the master thread outside any parallel region, so the group is **not** `+threadprivate`.
- With `ftol=1e20`, `nksol` stops before `psetnk`, so `raw * (1/suscal)[ja-1]` equals the post-`exmain`
  `bbb.jac` bit for bit. `tests/deterministic_omp/tools/capture_check.py` checks this and fingerprints runs.

## Rules for code in the `pandf` tree

1. Any module variable **assigned** during RHS evaluation must be `+threadprivate`. Missing it = data race that
   shows up only with `Nthreads > 1`.
2. Use `ixm1/ixp1` and the `Selec` ranges; padding around chunk edges and X-point cuts depends on the stencil width.
   A new term with a wider stencil (e.g. second neighbours) requires increasing the padding/`xlinc`/`yinc`.
3. No `save`d locals or accumulation into module arrays across calls.
4. `psorcxg`, `psorrg`, `psordis` are zeroed per chunk (`ppp/omp_parallel.F90:953-955`) — similar global
   accumulators need the same treatment.

## Verifying a change touches this correctly

```python
from uedge import bbb, ppp
ppp.OMPParallelPandf1 = 1; ppp.OMPParallelJac = 1; ppp.Nthreads = 4
ppp.CheckPandf1 = 1   # compares parallel vs serial RHS every call (ppp/ppp.v:15)
ppp.CheckJac = 1      # compares parallel vs serial Jacobian (ppp/ppp.v:9)
bbb.exmain()
```

`CheckJac` uses an absolute tolerance of 1e-14 and aborts on the first mismatching Jacobian entry; `ForceSerialCheck`
is a separate serial-vs-serial reproducibility check (two serial evaluations of the Jacobian: the first into the
solver's `jac`, the second into a local copy for the comparison); `CheckPandf1` applies an absolute then a relative 1e-14 test
and aborts after scanning all entries. They change solver state, so they are diagnostics, not a baseline. The bitwise check against serial is the harness below.

Test with a double-null / snowflake case too: X-point chunks are where regressions hide.
Serial build (`--serial`) is what CI tests — it will **not** catch OpenMP races.

## Bitwise OpenMP-vs-serial harness (`tests/deterministic_omp/harness/`)

The AIUE-8 reproducer (`tests/deterministic_omp/case/`) plus a harness that runs one configuration per fresh
`python -I` process and compares runs bit for bit, localising every mismatch to equation, species and cell
(usage and presets: `tests/deterministic_omp/README.md`):

```bash
PY=<venv>/bin/python   # OpenMP build
$PY tests/deterministic_omp/harness/cli.py check --preset tebox --arm jac --threads 4 --repeats 2 --python $PY --out /tmp/chk
```

Exit 0 agree, 1 mismatch, 2 harness error. Set `OMP_STACKSIZE` (the harness uses 512M): per-thread automatic arrays
scale with `neq`. On `v9-develop` this case fails in the electron-energy rows (AIUE-8).
