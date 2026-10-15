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
- RHS: `OMPPandf1Rhs` (`ppp/omp_parallel.F90:908`) splits the grid into bulk chunks plus special **X-point
  chunks** (`Make2DChunks`, `ppp/omp_parallel.F90:3`), runs `OMPPandf`/`OMPPandf_XPT` per chunk with `FIRSTPRIVATE(ylcopy,yldotcopy)`,
  and sums only the `iv` indices each chunk owns (`REDUCTION(+:yldottot)`).
- Jacobian: `jac_calc_omp` / `OMPJacBuilder` (`ppp/omp_parallel.F90:495`, `ppp/omp_parallel.F90:645`) — each thread builds columns with its own copy of
  module state; `Selec` ranges are `copyin`'d (`ppp/omp_parallel.F90:649`, `ppp/omp_parallel.F90:721`).
- Per-thread copies of module variables come from `+threadprivate` in `.v`. The `OmpCopy<pkg>` modules used by
  `ppp` are generated at build time (Forthon `--omp`, `setup.py` `OMPargs`), not stored in the repo.
- **Copy order matters.** `OMPJacBuilder` copies the master's threadprivate state to the workers before the column
  loop, scalars first (`OmpCopyScalar<pkg>`), then arrays (`OmpCopyPointer<pkg>`). The generated
  `OmpCopyPointer<var>` writes `(1:n)` on each worker with the worker's own copy of a threadprivate bound `n`, so the
  bounds must already be there (AIUE-8 root cause C1: the `api` `Imslwrk` spline tables). A new threadprivate array
  whose bounds are threadprivate scalars is safe only with this order; with the debug switches `OMPCopyScalar=0,
  OMPCopyArray=1` the hazard comes back. `OMPPandf1Rhs` never copies: its workers run on what the last
  `OMPJacBuilder` copy left (`OMPParallelPandf1=1` forces `OMPParallelJac=1`, `ppp/parallel.F90:30-36`). In an nksol
  run the RHS evaluations before the first Jacobian are serial only because `OMPPandf1Rhs` falls back to `pandf`
  while `ijactot` is 0, and `exmain` resets `ijactot` only when `icntnunk=0`: with `icntnunk=1`, or an RHS call from
  Python after an earlier `exmain`, the parallel RHS runs on whatever worker state the previous Jacobian left.
- **Clip rule, serial vs parallel.** `LocalJacBuilder` keeps an entry when `abs(jacelem*sfscal(ii)) > jaccliplim`
  with `ii` the row (equation), as `jac_calc` does (`ppp/parallel.F90:292`, `bbb/oderhs.m:1187`; AIUE-60 fixed a
  column index there). Keep the two loops in step. Known remaining differences (not races): the parallel builder
  subtracts the diagonal `1/dtuse` for every `svrpkg` and `nufak` also for `cvode`; both agree for `nksol`. The
  PETSc path (`svr/petsc-uedge.F90`) still clips with `sfscal(iv)` (AIUE-69).
- `emcoef` is also in the loop's `copyin` (`ppp/omp_parallel.F90:721`): it pointer-assigns the workers' `emcoef` to the
  master's array, which persists after the loop, so from the second Jacobian on `OmpCopyPointeremcoef` has the
  workers write identical values into the master's array (benign; redundant since the scalars-first copy).

## Rules for code in the `pandf` tree

1. Any module variable **assigned** during RHS evaluation must be `+threadprivate`. Missing it = data race that
   shows up only with `Nthreads > 1`. Exception: a shared scalar that every call recomputes to one value may instead
   be written only when it changes, so threads only read it in the loop (`nfsp`, `bbb/pandf.m:48-51`). The `com`
   timers (`com.ttimpjf`, …) stay shared and are updated through `acctim` (`com/misc.m`), whose `c$omp atomic` makes
   the update atomic in the OpenMP build: under OpenMP they report thread-seconds summed over threads. **Don't**
   make a value that is set outside `pandf` (geometry, user inputs) threadprivate to silence a write in `pandf`: workers would see it only through the
   `OMPJacBuilder` copy, and the parallel RHS never copies (stale values, see above). Compute it into a local instead.
2. Use `ixm1/ixp1` and the `Selec` ranges; padding around chunk edges and X-point cuts depends on the stencil width.
   A new term with a wider stencil (e.g. second neighbours) requires increasing the padding/`xlinc`/`yinc`.
3. No `save`d locals or accumulation into module arrays across calls.
4. `psorcxg`, `psorrg`, `psordis` are zeroed per chunk (`ppp/omp_parallel.F90:959-961`) — similar global
   accumulators need the same treatment.
5. **Threadprivate scalars only in `bbb`.** Forthon's `--omp` copy routines give every package the same common block
   `/ompcommonscalarcopy/`, sized by that package's threadprivate *scalars* (arrays are not affected). The extensions
   are imported `RTLD_GLOBAL` (`src/uedge/__init__.py`), so the first definition loaded serves every package: a
   package loaded before `bbb` (`com`, `grd`, `flx`) must not have threadprivate scalars, and no later package's block
   (`api`, `aph`, `ppp`, …) may be larger than `bbb`'s, or a copy writes past the block (AIUE-60: `com` timers made
   `bbb`'s copy overwrite `com`'s `/iotable/`). Check: `docs/reviews/AIUE-60-common-check.py`. Upstream: AIUE-71.

## Known OpenMP-unsafe paths

- `exmain` stops OpenMP runs with `isimpon` other than 0/2/6/7, `ismcnon>0`, `ishosor>0`, `ispsorave>0` or
  `cfvisxneoq/v≠0` (`bbb/odesetup.m:6727-6772`). Behind it: the `isimpon=5` reduced-ion path (`mombal`/`fmombal`:
  shared `Reduced_ion_*` arrays and SAVE locals) and the Monte Carlo neutral coupling write shared state in `pandf`.
- Not blocked, still racy (AIUE-69): full double null (`nxpt=2`) writes the shared `com` `ghxpt/gvxpt/sxyxpt` on every
  call; coupled wall sources (`iscpli/iscplo=1`) write `iwalli/iwallo/fngysi/fngyso` in `wsmodi/wsmodo`.

## Verifying a change touches this correctly

```python
from uedge import bbb, ppp
ppp.OMPParallelPandf1 = 1; ppp.OMPParallelJac = 1; ppp.Nthreads = 4
ppp.CheckPandf1 = 1   # compares parallel vs serial RHS every call (ppp/ppp.v:15)
ppp.CheckJac = 1      # compares parallel vs serial Jacobian (ppp/ppp.v:9)
bbb.exmain()
```

Test with a double-null / snowflake case too: X-point chunks are where regressions hide.
Serial build (`--serial`) is what CI tests — it will **not** catch OpenMP races.
