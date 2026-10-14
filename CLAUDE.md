# CLAUDE.md — UEDGE (v9)

UEDGE is a 2D fluid code for edge plasma and neutrals in magnetic fusion devices. It solves for density, momentum, ion and electron temperature, potential, and neutral gas with a fully implicit Newton–Krylov solver.
The physics is written in **MPPL Fortran** (`*/*.m`). `setup.py` converts it to `.F`, and **Forthon** wraps it as the Python package `uedge` (`bbb`, `com`, `grd`, `flx`, `svr`, `api`, `aph`, `wdf`, `ppp`, `ncl`).

## Naming conventions

- **Packages** are three-letter directories. Each one has `<pkg>.v` (variables and Python-callable routines), `*.m` sources, `Package` and `PackageMake` (BASIS build files), and `<pkg>.h` (`bbb/bbb.h`).
- **Variable groups** in `.v` files are `***** GroupName:` (for example `***** Compla:` at `bbb/bbb.v:1622`). Fortran pulls a group in with `Use(GroupName)` (`bbb/pandf.m:535-544`).
- **Equation switches** are `is<eq>on`: `isnion`, `isupon`, `isteon`, `istion`, `isngon`, `istgon`, `isphion` (`bbb/bbb.v:217-222`). Their per-cell versions are `is<eq>onxy` (`bbb/bbb.v:236`).
- **Multipliers on terms** are `cf<term>`: `cfneut`, `cfvisx`, `cfvisxy` (`bbb/bbb.v:279,331,336`). Differencing methods are `meth<eq>`: 22 = central, 33 = upwind, and so on (`bbb/bbb.v:33-41`).
- **Index names:** `ix` is poloidal, `iy` is radial, `ifld` is ion species, `igsp` is gas species. Neighbours come from `ixm1(ix,iy)` and `ixp1(ix,iy)`, never from `ix-1` (`bbb/pandf_plasma_continuity.m:387-388`).
- **Saved variables** end in `s`: `nis`, `ups`, `tes`, `tis`, `ngs`, `tgs`, `phis`. The live working arrays are `ni`, `up`, `te`, and so on.
- **Physics files** in `bbb/` are split by equation: `pandf_<plasma|gas>_<continuity|momentum|energy>.m`, `pandf_boundary.m`, `pandf_potencur.m`, `pandf_jacobian.m`.

## Core code patterns

- **MPPL source layout** (`bbb/pandf_plasma_continuity.m:1-21`): `c!include` headers come first, then `IMPLICIT NONE`, local declarations, and `Use(...)` lines. `setup.py`'s `MoveDecs` rule reorders declarations ahead of the uses (`setup.py:217`).
- **Comments:** `c` in column 1 marks a full-line comment. `#` starts an inline comment and is rewritten to `!` (`setup.py:635`). Continuation lines use `.` in column 6 (`bbb/pandf.m:561-562`).
- **Fatal errors** use `call xerrab('*** message ***')` (`bbb/pandf_plasma_continuity.m:29`). Informational output uses `call remark(...)` (`bbb/convert.m:345`). There is no other error mechanism in Fortran.
- **Dynamic arrays** are declared in `.v` with a leading `_` (`_real`, `_integer`) and allocated with `call gchange("Group",0)` (`bbb/odesetup.m:87`).
- **The RHS and Jacobian go through `pandf(xc, yc, neq, time, yl, yldot)`** (`bbb/pandf.m:513`). `xc,yc = -1` evaluates the full RHS. Otherwise it evaluates locally around the perturbed cell for the finite-difference Jacobian. Loop ranges come from `initialize_ranges` (`bbb/pandf.m:31`). New terms must use those ranges and must not loop over the whole grid.
- **Shared state written inside `pandf`** must be marked `+threadprivate` in `.v` (`bbb/bbb.v:1628`), or the OpenMP RHS and Jacobian will race.
- **The Python layer** (`src/uedge/`) imports with `from uedge import bbb, com` (`src/uedge/hdf5.py:2`). It reports through `print`, raises plain `Exception` (`src/uedge/hdf5.py:27`), and has no logging framework.

## Build & validation commands

```bash
# Build and install (OpenMP by default; needs gfortran with -fopenmp; on macOS set CC to a libomp-capable clang)
pip install -v .
pip install . -C "--build-option=--serial"        # what CI builds (build-test-wheel.yml)
pip install . -C "--build-option=--debug"         # -fcheck=all, FPE traps, -Og (setup.py:84-91)
pip install . -C "--build-option=--checkbounds"

# Smoke test
python -c "import uedge; from uedge import bbb; print(bbb.uedge_ver)"

# Regression tests live on a separate branch (upstream/pytests), not in this repo
git worktree add ../uedge-pytests upstream/pytests
pip install pytest pytest-isolate
cd ../uedge-pytests && pytest --isolate --tb=long pytests/unittests/D_only -s
#   suites: fulltests, unittests/{D+C, D_mols, D_only, slab_D_only}
```

There is no linter, formatter, or type checker. CI installs flake8 but never runs it. Compiler warnings come from `-Wconversion -fimplicit-none` (`setup.py:73-80`).

## On-demand context

| Module | Load when |
|---|---|
| `.claude/context/architecture.md` | You need the package map, the build pipeline, or the `pandf` call graph |
| `.claude/context/mppl-fortran.md` | Editing any `.m` file (dialect and conversion pitfalls) |
| `.claude/context/variables-forthon.md` | Adding or changing a variable, group, or Python-callable routine in a `.v` file |
| `.claude/context/openmp-jacobian.md` | Touching `pandf*`, `ppp/`, Jacobian code, or anything that writes shared arrays during RHS evaluation |
| `.claude/context/testing.md` | Running, writing, or reasoning about tests and CI |
| `.claude/context/physics-workflow.md` | Adding new physics (the spec → implement → review agent pipeline) |
| `.claude/context/python-layer.md` | Editing `src/uedge/*.py` (save/restore, `rundt`, balance, packaging) |

## Workflow (skills and agents)

| Work | Path |
|---|---|
| Start of session | `prime` |
| New physics | agents `uedge-physics` (spec in `docs/physics_specs/`) → `uedge-reviewer` → `uedge-implementer` → `uedge-reviewer` |
| Refactor, numerics, OpenMP, Python, build | `plan-feature` → `execute` → `validate` → `code-review` → `commit` (or `end-to-end-feature`) |
| Bug from a GitHub issue | `rca` → `implement-fix` → `commit` |
| Large epics | `create-prd` → `spec` (Jira/Confluence optional) |
| Process retrospective | `execution-report` → `system-review` |
| Fresh machine | `init-project` |

## Hard rules

- Edit `.m`, `.v`, `.F90` and hand-written `.f` sources only. **Never edit generated `.F` files.** They are overwritten on every build (`*.F` is gitignored).
- **Refactoring and restructuring must not change results.** With default inputs, the output must match the pre-change code to round-off. Any difference means the refactor is wrong.
- **Physics changes may change default results**, but only on purpose. The PR has to say which defaults changed, why, and which reference cases moved.
- New physics needs an approved spec in `docs/physics_specs/` before any Fortran is written (see `physics-workflow.md`).
- Run the `validate` skill (build, smoke test, relevant regression suites, plus the OpenMP check when the `pandf` tree changed) before opening a PR. Report fnrm or diff failures verbatim.
- Branches: `feature/v9-*` or `bugfix/v9-*` off `v9-develop`, rebased before merge. Never commit to `main`, `develop`, `v9-main`, or `v9-develop` (`doc/workflow.md`, `CONTRIBUTING.md`).
- Every new user-facing variable gets a units bracket and a `#` description in `.v`. Forthon builds the Python docs from them.

## Miscellaneous / Gotchas

<!-- Running list — add entries as you discover things the agent repeatedly misunderstands -->
- The MPPL converter does **plain substring replacement** (`setup.py:634-660`). It turns `float` into `real`, `#` into `!` (including inside strings), `break` into `exit`, and `while (` into `do while (`. Avoid identifiers and strings that contain these tokens.
- Adding a new `.m` file needs edits in three places: both the dependency list and the `-f` list in `Makefile.Forthon:27-28`, and the package's `Package` `SM =` list for BASIS (`bbb/Package`).
- `*.f` and `*.c` are gitignored (`.gitignore`), but `com/*.f`, `ncl/*.f` and `uedgeC_Forthon.c` are tracked sources. A new `.f` or `.c` file needs `git add -f`.
- The bundled `real` is double precision (Forthon `--realsize` defaults to 8, gfortran gets `-fdefault-real-8`). Do not add `real*8` or `dfloat`; `dfloat` is rewritten to `real`.
- `import uedge` executes `./.uedgerc.py` or `~/.uedgerc.py` if either exists (`src/uedge/__init__.py:59-67`), which can silently change state in tests.
- `com.iprint = 0` silences solver output (`com/com.v:709`).
- `.claude/settings.json` runs its hooks through `uv run`, so `uv` must be on PATH. The pre-tool hook allows `rm -rf` only on paths inside this repo (never the repo root or `.git/`), and blocks targets it can't resolve (`$VARS`, `xargs`, `find -exec`). It also blocks any command that mentions `.env`-style secret paths or `os.environ`, so put such code in a script file instead of a heredoc. The post-tool hook appends every tool call to `logs/post_tool_use.jsonl` (gitignored).
