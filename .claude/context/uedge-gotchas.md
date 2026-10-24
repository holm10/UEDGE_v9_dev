# UEDGE gotchas: traps that are by design, not bugs

Behaviour that is intended (or at least not a defect to ticket) but has cost a ticket time because a model or a person
assumed otherwise. The Confluence page `UEDGE gotchas` (SD space, page 9437185) is the copy for people. Add a new
by-design trap of UEDGE itself to both, on a `feature/v9-ai-*` branch (owner, 2026-10-21); a trap of the repo's test
tooling (Test tooling, below) is recorded here only (owner, 2026-10-22). Traps that can bite in any session (the MPPL
converter, hooks, the shell) stay in `CLAUDE.md` → Gotchas.

## Running UEDGE from Python

- **Forthon runtime.** Reading an unallocated dynamic array raises `Array is unallocated` (it does not return an empty array). `allocate()` keeps a dynamic array's values when its dimensions are unchanged; when they change, `gchange` keeps the overlapping block and zero-fills the rest (probed on `Interp`, AIUE-141). Importing `Forthon` (e.g. `Forthon.interfaceparser`) parses `sys.argv` and exits with usage when argv has one entry, so set `sys.argv` first. Count `+input`/`+maybeinput` variables with Forthon's parser or the built module's `getvarattr`, not with grep (`.claude/context/variables-forthon.md`).
- **Several cases in one Python process** behave differently from a fresh process, by design (owner, 2026-10-21; also on the Confluence page `UEDGE gotchas`). Check a multi-case run against a fresh process:
  - A second deck's grid is read only if `bbb.newgeo = 1` is set before its `exmain`. `ueinit` sets `newgeo = 0` after reading a grid (`bbb/odesetup.m:1175-1177`) and the decks never set it, so without it the new state runs on the old mesh.
  - Settings the first deck sets and the second does not reset carry over. Example: nonog's `com.isnonog = 1` carried into orthogonal_unittest gives fnrm 1.35 vs 0.128 fresh, with the state copied exactly. When only the mesh should differ, use one deck for both cases.
  - With the default `isgindx = 1` (`bbb/bbb.v:3081`), the normalised mesh `xnrm`/`ynrm` is built from the indices only (`bbb/geometry.m:2775-2803`; `isgindx = 0` uses true distances). Two gridue files with the same nx, ny and X-point indices give identical `xnrm`/`ynrm`, however different their geometry. Interpolation onto a stretched mesh is not a supported path.
  - A deck that calls `bbb.allocate()` before it has set every species count can stop when it runs a second time in the same process, because the values its first run set later in the file are still there. d_mols (`tests/yldot/families/d_mols/input.py:30-134`) sets `com.ngsp = 1`, allocates, then sets `bbb.igspsori[1] = 2` and `com.ngsp = 2`. Run again, that `allocate` stops with `*** igspsori,o refers to igsp > ngsp ***` (`bbb/odesetup.m:203`). Run each evaluation in its own process (the yldot suite does: `child_reuse = false` in every measured `family.toml`, AIUE-86); don't reorder the deck.

## Model layout

- **Inertial neutrals (`isupgon(1) = 1`) live in the ion arrays** (owner, 2026-10-22; also on the Confluence page `UEDGE gotchas`). Indices here are Fortran (1-based):
  - The hydrogenic atoms are ion species `iigsp`, the hydrogenic slot with `zi = 0` (`bbb/odesetup.m:920-921`; `ifld = 2` in large_dd2c, dnull_imp2 and imp7, probed). Their density is `ni(,,iigsp)` under `isnion(iigsp)`, their parallel velocity `up(,,iigsp)` under `isupon(iigsp)`.
  - `ng(,,1)` is a copy of `ni(,,iigsp)` (`bbb/convert.m:282-284`), so `isngon(1) = 0` does not mean the atoms are not evolved.
  - Atom temperature: `istgon(1) = 1` evolves `tg(,,1)` separately; `istgon(1) = 0` sets it from `ti`, whose equation is then a common ion and atom energy equation.
  - Saved states hold the copies: `ngs(,,1) = nis(,,iigsp)` and, with `istgon(1) = 0`, `tgs(,,1) = tis`, bit for bit (every yldot state checked, AIUE-91).
  - Never infer a species slot's meaning from its position: read `ziin`, `znuclin`, `isupgon`, `istgon` from the run, and say which index convention (Fortran or Python) a label uses.
- **A continuity fault shows in the up, te and ti rows of `yldot` too** (owner, 2026-10-23, AIUE-158; also on the Confluence page `UEDGE gotchas`). With the defaults `isflxvar = 0` and `isrscalf = 1` (`bbb/bbb.v:1298,1301`), `pandf` calls `rscalf` (`bbb/pandf.m:724`), which turns the conservative residuals d(nv)/dt and d(nT)/dt into dv/dt and dT/dt (`bbb/oderhs.m:537-692`): `yldot(up)` subtracts `up·nbvdot`, built from `yldot(ni)` and the neighbour's `resco` (`bbb/oderhs.m:612,633`), and te and ti subtract `T·` the summed density derivatives (`bbb/oderhs.m:642-656`). AIUE-89's continuity sign flip fired `ni[1]` 32, `up[1]` 28, `te[1]` 32 and `ti[1]` 32 rows on d_only. A per-block expectation (a mutation header, a coverage matrix, localization by block) includes the coupled blocks; "fires outside its block" is not by itself a defect.

## Test tooling

- **Importing the yldot harness pins OpenMP to one thread.** `tests/yldot/__init__.py` and `tests/yldot/harness/__init__.py` set `OMP_NUM_THREADS=1` at import (`tests/yldot/harness/__init__.py:10`), and libgomp reads it once, while `import uedge` runs (macOS links gcc's libgomp too; probed 2026-10-22: setting it after the import changes nothing). A process that imports anything under `tests/yldot/` before `uedge` is single-threaded whatever its caller set, and `ppp` quietly lowers a larger `ppp.Nthreads` to what is available (`ppp/omp_parallel.F90:299-302`). A multi-threaded run through the yldot tools starts a child with `OMP_NUM_THREADS` in its environment, imports `uedge` before `yldot.harness`, sets `ppp.Nthreads` itself, and checks the effective `ppp.Nthreads` after the run (`tests/yldot/tools/measure_roundoff.py:66-70`, AIUE-87).
