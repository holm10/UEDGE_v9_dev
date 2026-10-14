# Architecture — package map, build pipeline, RHS call graph

## Packages (Forthon build order, `Makefile.Forthon:12`, `src/uedge/__init__.py:22-33`)

| Pkg | Role | Key files |
|---|---|---|
| `com` | Shared constants/dims/geometry used by every package (`nx`, `ny`, `nxpt`, `ixm1/ixp1`, `iprint`) | `com.v`, `comutil.m`, `misc.m`, `blasext.m`, `petscMod.F90` |
| `aph` | Hydrogenic atomic rates (reads `rates/aph/*.dat`, `aph.crmdir` set in `__init__.py`) | `aphrates.m`, `aphread.m` |
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

1. `pip install .` → `setup.py` `uedgeBuild.run` (`setup.py:697`).
2. `mppl2f90` converts every `*.m` → `*.F` in place via the `M2F` rule list (`setup.py:631-673`).
3. `make -f Makefile.Forthon` runs `Forthon3` per package with `--interfacefile <pkg>/<pkg>.v`, producing `uedge/<pkg>py.so` and the `uedgeC` module.
4. `src/uedge/__init__.py` imports each `<pkg>py` with `RTLD_GLOBAL` so cross-package symbols resolve; order matters.

BASIS build (legacy, CI via Docker `build-basis.yml`) uses `*/Package`, `*/PackageMake`, `uedge.pack`.

## Python layer (`src/uedge/`)

| Module | Purpose |
|---|---|
| `__init__.py` | Loads packages, sets `bbb.uedge_ver`, `aph.crmdir`, runs `.uedgerc.py`, banner/provenance |
| `hdf5.py` | `hdf5_save`, `hdf5_restore`, `hdf5_dump`, `hdf5_restore_dump` |
| `rundt.py` | `UeRun` / `rundt()` — robust time-step continuation driver |
| `balance.py` | `UeBalance` / `checkbal()` — particle & power balance diagnostics |
| `gridue.py`, `uedgeplots.py`, `uedge_lists.py` | Grid file I/O, plotting, Forthon var-list helpers |
| `_banner.py`, `_provenance.py`, `_checkver.py`, `defaults.yaml` | Startup banner, run provenance, PyPI version check |
