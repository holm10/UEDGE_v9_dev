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
- RHS: `OMPPandf1Rhs` (`ppp/omp_parallel.F90:957`) splits the grid into bulk chunks plus special **X-point
  chunks** (`Make2DChunks`, `ppp/omp_parallel.F90:3`), runs `OMPPandf`/`OMPPandf_XPT` per chunk with `FIRSTPRIVATE(ylcopy,yldotcopy)`,
  and sums only the `iv` indices each chunk owns (`REDUCTION(+:yldottot)`).
- Jacobian: `jac_calc_omp` / `OMPJacBuilder` (`ppp/omp_parallel.F90:501`, `ppp/omp_parallel.F90:665`) — each thread builds columns with its own copy of
  module state; `Selec` ranges are `copyin`'d (`ppp/omp_parallel.F90:669`, `ppp/omp_parallel.F90:742`).
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
- **Fixed partition (default since AIUE-61, `OMPJacFixedChunks=1`, `ppp/ppp.v:60`).** The columns are split into
  `NchunksJac = min(OMPJacNchunksFixed, max(1, neq/OMPJacMinChunkLen))` contiguous chunks (defaults 64 and 300;
  `ppp/omp_parallel.F90:317`), with boundaries from `neq` and the count only (`OMPFixedSplitIndex`,
  `ppp/omp_parallel.F90:793`). No load weights are used. Each chunk starts with a full `pandf(-1,-1)` on its thread
  (`LocalJacBuilder`, `ppp/parallel.F90:214`). The serial column loop depends on its own history: a local `pandf`
  leaves last-bit differences, e.g. in `vsoree`, that later columns read (AIUE-8 root cause C2). The reset makes
  every chunk independent of what its thread evaluated before. So the Jacobian is bitwise reproducible and the same
  for any number of OpenMP threads and any schedule (`schedule(dynamic,OMPLoopJacNchunk)` is kept). It is **not**
  equal to serial on macOS arm64: it differs at round-off in the C2 rows.
  - The guarantee holds only where a full Jacobian-mode `pandf` resets all state and no shared variable carries
    results. `exmain` already refuses OpenMP with `ismcnon≠0` or `isimpon` not in {0, 2, 6, 7}
    (`bbb/odesetup.m:6727-6745`). Not validated: `nxpt=2` and coupled walls (still racy, AIUE-69, see "Known
    OpenMP-unsafe paths"), limiter sputtering and `istabon=5,6` (made thread-safe by AIUE-60, not tested here).
  - The three inputs take effect at the next `exmain` (`InitOMPJac` runs from `allocate`).
  - `OMPJacFixedChunks=0` restores the earlier partition (`OMPJacNchunks`, `OMPAutoBalance`; it varies from run to
    run).
  - `OMPJacChunkReset=0` (debug, `ppp/ppp.v:41`) skips the reset, and the Jacobian then depends on the thread count.
  - In fixed mode `OMPTimeLocalJac` is indexed per chunk, not per thread: the team can be larger than `NchunksJac`.
  - Each chunk writes straight into its own column `iJacCol(:,ichunk)`/`rJacElem(:,ichunk)`: there are no
    per-thread automatic copies. Those copies overflowed the master's stack for `OMPJacNchunks≠0`.

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
4. `psorcxg`, `psorrg`, `psordis` are zeroed per chunk (`ppp/omp_parallel.F90:1008-1010`) — similar global
   accumulators need the same treatment.
5. **No threadprivate scalars before `bbb`; no later block larger than `bbb`'s.** Forthon's `--omp` copy routines give every package the same common block
   `/ompcommonscalarcopy/`, sized by that package's threadprivate *scalars* (arrays are not affected). The extensions
   are imported `RTLD_GLOBAL` (`src/uedge/__init__.py`), so the first definition loaded serves every package: a
   package loaded before `bbb` (`com`, `grd`, `flx`) must not have threadprivate scalars, and no later package's block
   (`api`, `aph`, `ppp`, …) may be larger than `bbb`'s, or a copy writes past the block (AIUE-60: `com` timers made
   `bbb`'s copy overwrite `com`'s `/iotable/`). `api` (12 scalars, 96 B) is an allowed later, smaller block; new
   threadprivate scalars go in `bbb`. Check: `docs/reviews/AIUE-60-common-check.py`. Upstream: AIUE-71.
6. A full `pandf(-1,-1)` must recompute every module variable a later local `pandf` reads (the fixed partition relies
   on it, see above). State that only a local evaluation sets and a full one leaves alone would make the OpenMP
   Jacobian depend on the thread count.

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
ppp.CheckJac = 1      # compares parallel vs serial Jacobian (ppp/ppp.v:9); absolute 1e-14, entry by entry:
                      # with the fixed partition it can stop on the expected C2 round-off difference
bbb.exmain()
```

Test with a double-null / snowflake case too: X-point chunks are where regressions hide.
Serial build (`--serial`) is what CI tests — it will **not** catch OpenMP races.
