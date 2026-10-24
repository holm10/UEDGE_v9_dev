# Architecture — package map, build pipeline, RHS call graph

## Packages (Forthon build order, `Makefile.Forthon:12`, `src/uedge/__init__.py:22-33`)

| Pkg | Role | Key files |
|---|---|---|
| `com` | Shared constants/dims/geometry used by every package (`nx`, `ny`, `nxpt`, `ixm1/ixp1`, `iprint`) | `com.v`, `comutil.m`, `misc.m`, `blasext.m`, `petscMod.F90` |
| `aph` | Hydrogenic atomic rates (reads the CRUMPET files `rates/aph/*.dat`, installed as `uedge/rates/aph/`; `aph.crmdir` points there, set in `__init__.py`) | `aphrates.m`, `aphread.m` |
| `api` | Impurities: rates, sputtering, force balance (`fmombal`) | `apifcn.m`, `sputt.m`, `fmombal.m`, `inelrates.m` |
| `flx` | Flux-surface construction from EFIT eqdsk | `flxcomp.m`, `flxdriv.m`, `flxread.m` |
| `grd` | Mesh generation from flux surfaces, `gridue` I/O | `grdcomp.m`, `grddriv.m`, `grdread.m` |
| `bbb` | **All plasma/neutral physics, BCs, solver driver** | see below |
| `svr` | Solvers: `nksol` (Newton–Krylov), `vodpk`, `daspk`, ILUT precond. | `nksol.m`, `svrut*.m` |
| `ppp` | OpenMP-parallel RHS + Jacobian (J. Guterl, GA) | `omp_parallel.F90`, `parallel.F90`, `ppp.v` |
| `wdf` | Wall/dust coupling stubs | `wdf.m` |
| `ncl` | NCLASS neoclassical transport | `ncl_driver.m`, `nclass_mod.f` |

`bbb` depends on `com`; `svr` depends on `bbb`; `ppp` depends on `com`+`bbb` (`Makefile.Forthon:27-44`).

## `bbb/` layout

| File | Contents |
|---|---|
| `odesetup.m` (~8k lines) | Problem setup, allocation (`gchange`), indexing `yl`↔(ix,iy,eq), `exmain` prelims |
| `odesolve.m` | `exmain`/`uedriv` — solver loop, time stepping |
| `oderhs.m` | Rates, sources, MC-neutral glue, misc RHS helpers |
| `pandf.m` | **RHS driver** `pandf(xc,yc,neq,time,yl,yldot)` (`bbb/pandf.m:513`), `initialize_ranges` (`bbb/pandf.m:31`), `calc_rhs` (`bbb/pandf.m:251`), `add_timestep` (`bbb/pandf.m:390`) |
| `pandf_plasma_{continuity,momentum,energy}.m` | Ion continuity, parallel momentum, Te/Ti equations |
| `pandf_gas_{continuity,energy}.m` | Neutral gas equations |
| `pandf_potencur.m` | Potential & currents (`calc_currents`, `calc_fqp`) |
| `pandf_boundary.m` (~5k lines) | `bouncon` — all boundary conditions |
| `pandf_jacobian.m` | Finite-difference Jacobian helpers (`jacobian_store_*`) |
| `geometry.m`, `griddubl.m` | Metric coefficients; grid refinement/interp |
| `convert.m` | `convsr_vo`/`convsr_aux`: unpack `yl` → `ni`, `up`, `te`, … |
| `turbulence.m`, `ext_neutrals.m` | Anomalous-transport models; external/MC neutrals coupling |

## RHS evaluation order (`bbb/pandf.m:513-747`)

`initialize_ranges(xc,yc,…)` → (`jacobian_store_*` if local) → `convsr_vo` / `convsr_aux` (unpack `yl`) →
`calc_plasma_diffusivities` → `initialize_driftterms` / `calc_driftterms` → `calc_currents`, `calc_fqp` (if `isphion`) →
`calc_friction` → … equation residuals … → `bouncon` → `calc_rhs` → `add_timestep`.

`xc = yc = -1` → full-domain RHS. Otherwise only a box around `(xc,yc)` is evaluated (Jacobian column).

## Build pipeline

1. `pip install .` → `setup.py` `uedgeBuild.run` (`setup.py:755`).
2. `mppl2f90` converts every `*.m` → `*.F` in place via the `M2F` rule list (`setup.py:645-687`), in the build's
   working directory. Before AIUE-163 it returned to `$PWD` instead, so a build whose `PWD` differed from its working
   directory (launched from Python with another `cwd`, or `pip install /path/to/tree` from elsewhere) converted, made
   and packaged the `PWD` tree; builds of such commits still need `PWD` set to the tree.
3. `make -f Makefile.Forthon` runs `Forthon3` per package with `--interfacefile <pkg>/<pkg>.v`, producing the `uedge/<pkg>py.so` extensions (not `uedgeC`). In the OpenMP build on Linux, `setup.py` runs that make with `-fopenmp` appended to `LDFLAGS`, because Forthon passes no OpenMP flag to the extension link (`setup.py:832-864`). macOS relies on `uedgeC` loading libomp. A `--coverage` build adds GCC's coverage runtime to `LDFLAGS` for the same make, because Forthon links without `--fargs`: `--coverage` on Linux (gcc then adds `-lgcov` after the objects), the `libgcov.a` path on macOS (`setup.py:847-862`).
4. `build.run` then builds the C extension `uedgeC` (`setup.py:866,881,897`), linked with `-fopenmp` in the OpenMP build. A `--serial` build removes its OpenMP flags at module level, before `setup()` copies `FLAGS['CARGS']` into the `uedgeC` link arguments (`setup.py:105-110`, AIUE-109).
5. After `build.run`, `uedgeBuild.run` writes the build record `<build_lib>/uedge/_build_info.json`, so the wheel installs it (`setup.py:867-870`, `build_info` at `setup.py:711-742`, AIUE-181): the options, the `--fargs`/`--cargs` strings and `OMPFLAGS` passed to make, make's `LDFLAGS`, `forthon_fopt`, the Fortran compiler and its `--version`, platform, machine, and `git_sha`/`git_branch`/`git_commit_date_iso`/`git_dirty` (only when the source tree has its own `.git`; `git_dirty` counts tracked files only, while `_provenance.py`'s own fallback also counts untracked ones), the keys `src/uedge/_provenance.py` reads. `forthon_fopt` is Forthon's own optimisation flags, which `Forthon3` puts before `--fargs` on every Fortran source compile (not the `*_p.F90` wrappers): `-O3 -ftree-vectorize -ftree-vectorizer-verbose=0`, plus `-fopenmp` in an OpenMP build, in every build kind, since make never passes Forthon `-g`; a later `-O0`/`-Og` from `--fargs` sets the level, but the explicit `-f` flags stay. Forthon's precision and form flags (`-fdefault-real-8`, `-fdefault-integer-8`, `-DISZ=8`, `-fno-second-underscore`, `-ffixed-line-length-132`, `-fPIC` on Linux) are not recorded. Editable installs never run `uedgeBuild.run` (no record).
6. `src/uedge/__init__.py` imports each `<pkg>py` with `RTLD_GLOBAL` so cross-package symbols resolve; order matters.

BASIS build (legacy, no CI since AIUE-178) uses `*/Package`, `*/PackageMake`, `uedge.pack`.

## Python layer (`src/uedge/`)

| Module | Purpose |
|---|---|
| `__init__.py` | Loads packages, sets `bbb.uedge_ver`, `aph.crmdir`, runs `.uedgerc.py`, banner/provenance |
| `hdf5.py` | `hdf5_save`, `hdf5_restore`, `hdf5_dump`, `hdf5_restore_dump` |
| `rundt.py` | `UeRun` / `rundt()` — robust time-step continuation driver |
| `balance.py` | `UeBalance` / `checkbal()` — particle & power balance diagnostics |
| `gridue.py`, `uedgeplots.py`, `uedge_lists.py` | Grid file I/O, plotting, Forthon var-list helpers |
| `_banner.py`, `_provenance.py`, `_checkver.py`, `defaults.yaml` | Startup banner, run provenance, PyPI version check |
