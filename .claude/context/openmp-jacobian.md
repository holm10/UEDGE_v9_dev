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
  with `ii` the row (equation), as `jac_calc` does (`ppp/parallel.F90:296`, `bbb/oderhs.m:1187`; AIUE-60 fixed a
  column index there). Keep the two loops in step. Known remaining differences (not races): the parallel builder
  subtracts the diagonal `1/dtuse` for every `svrpkg` and `nufak` also for `cvode`; both agree for `nksol`. The
  PETSc path (`svr/petsc-uedge.F90`) still clips with `sfscal(iv)` (AIUE-69).
- `emcoef` is also in the loop's `copyin` (`ppp/omp_parallel.F90:742`): it pointer-assigns the workers' `emcoef` to the
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
  - Cost: the full problem (64 chunks) is within about 3 % of the old partition at 2-8 threads. Smaller problems get
    fewer chunks (`neq/300`): with neq up to about 5 000 at 8 threads the Jacobian may take up to about 2x the old
    partition's time, and below neq 600 (one chunk, e.g. the D_only pytests case) about 3x, a few tens of ms. Lower
    `OMPJacMinChunkLen` (each chunk then pays one more full `pandf`) or set `OMPJacFixedChunks=0`.
  - `OMPJacFixedChunks=0` restores the earlier partition (`OMPJacNchunks`, `OMPAutoBalance`; it varies from run to
    run).
  - `OMPJacChunkReset=0` (debug, `ppp/ppp.v:41`) skips the reset, and the Jacobian then depends on the thread count.
  - In fixed mode `OMPTimeLocalJac` is indexed per chunk, not per thread: the team can be larger than `NchunksJac`.
  - Each chunk writes straight into its own column `iJacCol(:,ichunk)`/`rJacElem(:,ichunk)`: there are no
    per-thread automatic copies. Those copies overflowed the master's stack for `OMPJacNchunks≠0`.

## Raw-Jacobian capture (`bbb.jaccapture`, off by default)

`bbb.jac` after `exmain` is not the matrix `jac_calc` returned: `sfsetnk` scales its columns by `1/suscal`,
and `psetnk` also scales rows by `sfscal`, normalises rows and factorises it. To get the unscaled matrix, set
`bbb.jaccapture = K` (group `Jacobian_capture`, `bbb/bbb.v:4221`). `jac_calc_interface` (`bbb/oderhs.m:4676`) then
copies each CSR Jacobian returned by `jac_calc` or `jac_calc_parallel` (`bbb/oderhs.m:4716`, routine
`jac_capture` at `bbb/oderhs.m:4738`) into slots `1..bbb.jaccapn`:

- What is captured is the `jac_calc`/`jac_calc_parallel` output: finite-difference `d(yldot)/d(yl)` including the
  `-1/dtuse`, `-1/dtphi` and `-nufak` diagonal terms, with entries `|J*sfscal| <= jaccliplim` dropped (`sfscal`
  of the row in both `jac_calc` and `ppp/parallel.F90` `LocalJacBuilder`; see the clip rule above), so the
  pattern depends on `sfscal`.
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

`CheckJac` uses an absolute tolerance of 1e-14 and aborts on the first mismatching Jacobian entry; `ForceSerialCheck`
is a separate serial-vs-serial reproducibility check (two serial evaluations of the Jacobian: the first into the
solver's `jac`, the second into a local copy for the comparison); `CheckPandf1` applies an absolute then a relative 1e-14 test
and aborts after scanning all entries. They change solver state, so they are diagnostics, not a baseline. The bitwise check against serial is the harness below.

Test with a double-null / snowflake case too: X-point chunks are where regressions hide.
The serial build (`--serial`) that `build-test-wheel.yml` tests will **not** catch OpenMP races. The OpenMP CI job
`.github/workflows/build-test-omp.yml` (AIUE-57) does: it runs the flow below through
`tests/deterministic_omp/ci/run_omp_ci.sh` on the default OpenMP build and gates on the `jac` arm, bitwise.

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

**Bitwise OpenMP-vs-serial test flow** (AIUE-8 reproducer, `tests/deterministic_omp/README.md`): with the OpenMP
build's Python `PY`, `$PY tests/deterministic_omp/harness/cli.py flow --configs tebox --threads 4 --python $PY --out DIR`
answers "does OpenMP equal serial here, and where not?" in seconds; without `--configs` it runs the quick set (`tebox`,
`full` at 2 and 4 threads), `--all` every configuration (`tebox`, `full`, `te`, `ti`, `ni`, `up`, `ng`, `phi`) at 2,
4, 8 threads. Each (configuration, arm, threads) group runs K fresh processes (`--repeats`, default 2) against one serial
reference of the same build and must agree with serial and across repeats. There is one verdict per arm (`jac` =
`OMPParallelJac`, `jacrhs` = plus `OMPParallelPandf1`); the exit code follows `--gate jac|jacrhs|all|none` (default
`jac`): 0 pass, 1 fail, 2 harness error. Every record goes through the harness's `check_arm` against the requested
spec (the arm's switches and `ParallelJac`/`ParallelPandf1`, `Nthreads`, `OMP_NUM_THREADS`, diagnostic switches off,
the capture source, iterations recorded), so a run where the arm did not take effect (e.g. a `--serial` build) is a
harness error, never a pass; so is a comparison report with errors. Output: `summary.md` (first mismatch as equation and cell) and `flow.json`.
The code is `tests/deterministic_omp/harness/flow.py`; its unit tests need no build
(`python -m pytest tests/deterministic_omp/harness`).
In CI (`run_omp_ci.sh`; locally `PYTHON=$PY tests/deterministic_omp/ci/run_omp_ci.sh pr`) a failing `jac` group is
reported as configuration, arm, threads, equation and cell of the first mismatch; `jacrhs` only warns.

## Serial old-vs-new bitwise check (`tests/deterministic_omp/harness/serial_check.py`)

**Serial results must not change.** Any change to Fortran, a `.v` file or `ppp/` (including an OpenMP fix) must
leave the serial path bitwise identical to `v9-develop`, in the `--serial` build and in the OpenMP build with
`OMPParallelJac = OMPParallelPandf1 = 0`. Prove it with `tests/deterministic_omp/harness/serial_check.py`. It needs
four venvs (base and change, `--serial` and default). Exit 0 only for the complete gate (both pairs, `--cases all`,
two different builds from clean committed trees, base on `origin/v9-develop`). The gate includes Newton-iteration cases, so `psetnk` and the preconditioner are covered.
See `testing.md` and `tests/deterministic_omp/README.md`.
OpenMP-vs-serial agreement of one build is a separate check (`tests/deterministic_omp/harness/cli.py check`).
