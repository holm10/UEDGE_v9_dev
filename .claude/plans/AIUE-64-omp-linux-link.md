# Feature: AIUE-64 — link the Forthon extensions with -fopenmp in the Linux OpenMP build

Validate the patterns and file references below before implementing.

## Summary
**Type**: Python/Build (bug fix in `setup.py`)
**Complexity**: Low (one guarded block in `uedgeBuild.run`); the validation is the larger part
**Default results**: Unchanged. No Fortran, `.v` or compile flag changes. Only the link of the Forthon extensions in
the **Linux OpenMP** build changes. The serial build (every platform) and the macOS OpenMP build are not touched.
**Packages / files**: `setup.py` (product); `.claude/context/architecture.md` + `refs.lock.json` (code-facts);
`docs/rca/AIUE-8-data/linux/aiue64/` (Linux evidence)
**Revision**: round 2, after plan review round 1 (`docs/reviews/AIUE-64-plan-round1.md`, REVISE 0/1/8; response in
`docs/reviews/AIUE-64-plan-round1-response.md`)
**Branch / worktree**: `bugfix/v9-AIUE-64-omp-linux-link` @ `/Users/holma/Documents/uedge/src/uedge-wt/AIUE-64`
(base: local `v9-develop` `4faed39`; product tree identical to `0fac655`, which built the `base-*` venvs:
`git diff 0fac655 4faed39 -- . ':!.claude' ':!CLAUDE.md' ':!docs'` is empty)
**Jira**: AIUE-64 (epic AIUE-8). Blocks the AIUE-57 merge.
**Venvs**: `venvs/AIUE-64-omp`, `venvs/AIUE-64-serial` (`uedge-wt/build_uedge.sh <tree> <venv> omp|serial`)

## Problem and solution

**Symptom (AIUE-62, `docs/rca/AIUE-8-data/linux/build_info.txt` and `ubuntu/import_default_ldflags.txt` on
`feature/v9-AIUE-62-linux-characterisation`).** On Debian 12 (gcc 12.2) and Ubuntu 24.04 (gcc 13.3, the CI runner
distribution), the default OpenMP build `python -m pip install -v .` installs, but
`python -c "import uedge"` dies with
`symbol lookup error: .../uedge/bbbpy.cpython-3xx-x86_64-linux-gnu.so: undefined symbol: GOMP_parallel` (exit 127).
With `LDFLAGS=-fopenmp` the build imports, and `apipy`, `bbbpy` and `ppppy` then list `libgomp.so.1` as NEEDED.

**Root cause, confirmed in the build code.** Two separate links happen, and only one of them gets an OpenMP flag.

1. *The Forthon package extensions* (`compy`, `aphpy`, `apipy`, `bbbpy`, `ppppy`, `flxpy`, `grdpy`, `svrpy`, `wdfpy`,
   `nclpy`) are built by `make -f Makefile.Forthon` (`setup.py:770`), which runs `Forthon3` once per package
   (`Makefile.Forthon:15-52`). `setup.py` hands Forthon three things: `--omp` (`OMPargs`, `setup.py:95`, via
   `OMPFLAGS` in `INSTALLARGS`, `Makefile.Forthon:10`), `--fargs "... -fopenmp ..."` and `--cargs="-fopenmp"`
   (`setup.py:765-768`). None of them reaches the link:
   - `--omp` only appends `-fopenmp` to the Fortran optimisation flags (`Forthon/compilers.py:369-370`
     `linux_gfortran`, `:644-645` `macosx_gfortran`; Forthon 0.10.10) and switches on the `OmpCopy` wrapper
     generation.
   - `--fargs` goes to the gfortran compile lines; `--cargs` goes to `extra_compile_args`
     (`Forthon/Forthon_builder.py:297-298`). Forthon's own comment there (`:299-302`) notes that it never adds an
     OpenMP flag for the C side.
   - The link itself is a `setuptools.Extension` (`Forthon/Forthon_builder.py:497-507`) with
     `libraries = fcompiler.libs + libs` (= `gfortran`, `mvec`, plus `-l` options) and
     `extra_link_args = fcompiler.extra_link_args` (+ `-Wl,-z,lazy` on Linux, `:469-470`). Forthon has no option
     that adds a link argument; its only levers are `-l/--libs` and the environment that setuptools reads.
   - The recorded link line (`build_info.txt`): `gcc -shared ... -lgfortran -lmvec -lreadline -o .../bbbpy....so
     -Wl,-z,lazy` — no `-fopenmp`, no `-lgomp`. The gfortran objects reference `GOMP_parallel`, `GOMP_barrier`,
     `omp_get_thread_num` (macOS `nm -u`: 4 in `apipy`, 4 in `bbbpy`, 13 in `ppppy`, 0 elsewhere), so these three
     extensions are left with undefined OpenMP symbols.
2. *`uedgeC`* is the only extension `setup.py` builds itself (`build.run`, `setup.py:772,781-803`). It is
   *linked* with `-fopenmp` (`extra_link_args=FLAGS['CARGS']+[...]`, `setup.py:799`) but not compiled with it
   (`extra_compile_args=fcompiler.extra_compile_args`, `setup.py:801`; the `uedgeC` compile lines in
   `uedge-wt/logs/build-base-omp.log` carry no `-fopenmp`). Its C sources contain no OpenMP code. Ubuntu 24.04's
   gcc links with `--as-needed` by default (`gcc -dumpspecs`: 3 occurrences, AIUE-62
   `ubuntu/import_default_ldflags.txt`), so the linker drops `libgomp` from `uedgeC` too (AIUE-62
   `ubuntu/fma_fixld.txt`: `uedgeC` NEEDS only `libreadline.so.8 libc.so.6`). On Debian 12 the same import
   failure is observed (AIUE-62 `build_info.txt`); that Debian's gcc also defaults to `--as-needed` is not on
   record and is checked in L6 (`gcc -dumpspecs`, record only).

**Why it works on macOS today (and must keep working the same way).** `src/uedge/__init__.py:21-22` sets
`RTLD_LAZY | RTLD_GLOBAL` and imports `uedgeC` first. On macOS `uedgeC` is linked by LLVM clang with `-fopenmp`
and ld64 keeps the dylib, so `uedgeC` loads `/opt/homebrew/opt/llvm/lib/libomp.dylib` (checked with `otool -L` on
`venvs/base-omp`). The Fortran extensions are flat-namespace bundles (`-flat_namespace` from
`Forthon/compilers.py:641`; `otool -hv bbbpy*.so` shows no `TWOLEVEL` flag) with undefined OpenMP symbols, so dyld
binds `GOMP_parallel` & co. to libomp's GOMP compatibility entry points (`nm -gU libomp.dylib`: 134 `GOMP_*`,
including `T _GOMP_parallel`). There is exactly one OpenMP runtime on macOS (libomp), and no Fortran extension
links one itself. On Linux the same trick fails on `--as-needed` toolchains because `uedgeC` no longer brings
`libgomp` in. (On a toolchain without `--as-needed`, such as RHEL or manylinux, it likely works by accident
through `uedgeC` + `RTLD_GLOBAL`. Not tested here.)

**Side finding (out of scope, not changed).** `setup.py:799` is evaluated when `setup.py` is imported, before
`uedgeBuild.run` removes `-fopenmp` from `CARGS` for `--serial` (`setup.py:735`). So the *serial* build still links
`uedgeC` with `-fopenmp`: `otool -L venvs/base-serial/.../uedgeC*.so` lists `libomp.dylib`. Changing that would
change the serial build, which this ticket must not do. The quirk is also load-bearing: the serial `ppppy` still
calls `omp_get_thread_num_`/`omp_get_wtime_` (`ppp/parallel.F90:213,286,340`; `nm -u` on `venvs/base-serial`),
which on macOS resolve only through the serial `uedgeC`'s libomp, and which on Linux `--as-needed` toolchains are
already unresolved in the serial build (a latent lazy-binding failure if those calls are reached). **Owner decision:
a separate follow-up ticket, AIUE-67** (filed by the main session, carrying review finding L1-m2, so that the
follow-up does not simply drop `-fopenmp` from the serial `uedgeC` link). Not changed here.

**Fix.** In the OpenMP build on Linux only, run `make -f Makefile.Forthon` with `-fopenmp` appended to `LDFLAGS` in
the environment of that one subprocess. setuptools appends `LDFLAGS` from the environment to `LDSHARED` for every
extension link (`setuptools/_distutils/compilers/C/unix.py:233` `ldshared = _add_flags(ldshared, 'LD')`, setuptools
84.0.0; the older `customize_compiler` did the same). `make` passes its environment on to every `Forthon3`, which
calls `setuptools.setup` in the same process (`--build` is the default, `Forthon_options.py`), so all ten Forthon
extensions link with `-fopenmp`. With gcc, `-fopenmp` at link time adds `-lgomp` (and the pthread bits) through
the specs' library section, *after* the objects. That is why it survives `--as-needed`, unlike a bare `-lgomp`
placed early in `LDSHARED`. This is the `LDFLAGS=-fopenmp` workaround that AIUE-62 validated, made automatic and
scoped:
- *Scoped to the Forthon make call*: `os.environ` is not changed, so the outer `build.run(self)` that links
  `uedgeC` sees the same environment as before, and the `uedgeC` link line is unchanged.
- *Linux only* (`sys.platform.startswith('linux')`; `setup.py:14` imports it as `platform`): on macOS, `-fopenmp`
  at link time would make every Fortran extension depend on `libomp.dylib` itself. That is still one runtime, but it
  changes the macOS link, which the ticket rules out. With Apple clang it would not link at all.
- *OpenMP build only*: not under `--serial`.
- *User `LDFLAGS` kept*: ` -fopenmp` is appended to the user's `LDFLAGS` string as is (CI's wheel job sets
  `LDFLAGS: "-L${LIBOMPPATH}/lib"`, `build-test-wheel.yml`), so quoting and whitespace in it are not touched
  (setuptools splits `LDSHARED` shell-style). It is not added if `-fopenmp` is already one of its tokens, so a build
  that uses the AIUE-62 workaround gets an identical link.

**Alternatives considered (rejected).**
- *`--libs gomp` in `OMPargs` (Forthon `-l`)*: hard-codes the GNU runtime name into the link even when `CC` is
  clang (`clang -fopenmp` would pull libomp into `uedgeC`, giving two runtimes on non-`--as-needed` systems), and it
  bypasses the driver's own OpenMP link logic. `-fopenmp` lets the C driver that already links `uedgeC`
  with `-fopenmp` pick its own runtime. That is the same rule `setup.py` already uses for the `uedgeC` link.
- *Force `libgomp` into `uedgeC` (`-Wl,--no-as-needed`)*: it keeps leaning on `RTLD_GLOBAL` cross-library binding
  instead of each extension declaring the library it needs, and it would change the `uedgeC` link.
- *Fix in Forthon* (add `-fopenmp` to `extra_link_args` when `--omp`): the right upstream fix, but outside this
  repo and the `forthon>=0.10.7` pin. Suggested as a follow-up, see Notes.
- *Edit `Makefile.Forthon`*: it has no link-flag hook (`DEBUG`/`INSTALLARGS` are Forthon options, and Forthon has
  no link option). Doing it there would mean exporting `LDFLAGS` in the makefile, which is less visible and harder
  to restrict to Linux than doing it in `setup.py`.

## Context references — read before implementing
- `setup.py:14,46` — `platform` is `sys.platform` (and is copied to `machine`, which `-t` can override; use
  `platform`, the build host).
- `setup.py:69-95` — `FLAGS`: `FARGS`/`CARGS` carry `-fopenmp`, `OMPargs = ['--omp']`.
- `setup.py:704-772` — `uedgeBuild.run`: `--serial` removes the OpenMP flags (`:731-740`), make call (`:769-771`),
  then `build.run(self)` links `uedgeC` (`:772`).
- `setup.py:781-803` — the `uedgeC` Extension; `extra_link_args` at `:799` is module-level (side finding).
- `Makefile.Forthon:10,15-52` — `INSTALLARGS` holds `$(OMPFLAGS)`; one `Forthon3` call per package.
- `src/uedge/__init__.py:21-33` — `RTLD_LAZY | RTLD_GLOBAL`, `uedgeC` imported first.
- Forthon 0.10.10 (`venvs/base-omp/lib/python3.13/site-packages/Forthon/`): `Forthon_builder.py:297-302,469-470,
  497-507`; `compilers.py:336-371` (`linux_gfortran`), `:609-647` (`macosx_gfortran`).
- `.claude/context/architecture.md` §Build pipeline (steps 3-4) — the fact to extend.
- AIUE-62 worktree `uedge-wt/AIUE-62`: `tests/deterministic_omp/linux/{Dockerfile,Dockerfile.ubuntu,build_uedge.sh,
  clone_harness.sh,run_flow.sh,fma_scan.sh,README.md}`; images `aiue62:amd64` (Debian 12, Python 3.11) and
  `aiue62-ubuntu:amd64` (Ubuntu 24.04, Python 3.12) are already built locally.
- AIUE-57 worktree `uedge-wt/AIUE-57` (`8ee189d`): `.github/workflows/build-test-omp.yml` (install and build steps),
  `tests/deterministic_omp/ci/run_omp_ci.sh` (unit tests, smoke test l. 86-94, flows; `OMP_CI_FLOWS`/`OMP_CI_GATE`).
- AIUE-53 worktree `uedge-wt/AIUE-53` (`15ae327`): `tests/deterministic_omp/harness/serial_check.py`, README
  §"Serial old-vs-new check".

## Patterns to mirror
- The existing OpenMP/serial branch in `uedgeBuild.run` (`setup.py:731-740`): `if arglist['serial']: ... else: ...`.
- Subprocess call style: `call([...])` from `subprocess` (`setup.py:13`, `:755`, `:770`); `call` takes `env=`.
- Build messages use plain `print(...)` (`setup.py:754,760`), as in the rest of `setup.py`.

## Step-by-step tasks

### 0. BASELINE (macOS, unmodified branch, before any edit)
- **IMPLEMENT**: build the untouched branch (`4faed39`) as the "before" for the macOS link comparison. Keep the
  verbose logs:
  `build_uedge.sh $WT $V/AIUE-64-omp omp > $SCR/mac_before_omp.log 2>&1` and the same for serial
  (`$V/AIUE-64-serial`, `serial`), where `WT=uedge-wt/AIUE-64`, `V=uedge-wt/venvs`, `SCR=<session scratchpad>/AIUE-64`.
  Record for every `*.so`: `otool -L`, `otool -hv`, `nm -u | grep -E '^_(GOMP_|omp_)'` (anchored, so UEDGE's own
  `_jac_calc_omp_` is not counted; review L1-m1), and the link command lines (`grep -E ' -bundle ' log`) with the
  venv and build-temp paths normalised (`sed` the tree and venv prefixes).
- **GOTCHA**: the task-3 "after" builds reuse the venv names `AIUE-64-omp`/`AIUE-64-serial` and overwrite them.
  Write all "before" records (and copy the two build logs) to `$SCR/mac_before/` before task 3 starts.
- **VALIDATE**: both import (the build script's own smoke line prints `uedge_ver`).

### 1. UPDATE `setup.py` — `uedgeBuild.run`, replace the make call at `setup.py:769-771`
- **IMPLEMENT** (exact intent; keep the wording close to this):
  ```python
        # Linux OpenMP build: link every Forthon extension with -fopenmp (AIUE-64). Forthon's --omp,
        # --fargs and --cargs reach only the compile lines, so bbbpy, ppppy and apipy were linked without
        # the OpenMP runtime; where gcc links with --as-needed (Ubuntu 24.04; also seen on Debian 12), uedgeC
        # drops it as well, and import failed with "undefined symbol: GOMP_parallel". setuptools appends
        # LDFLAGS to every extension link. Set it for the Forthon make only, so the uedgeC link below is
        # unchanged.
        # macOS is left alone: there, uedgeC loads libomp and the flat-namespace extensions bind to it.
        makeenv = None
        if not arglist['serial'] and platform.startswith('linux'):
            makeenv = dict(os.environ)
            ldflags = makeenv.get('LDFLAGS', '')
            if '-fopenmp' not in ldflags.split():
                ldflags = (ldflags + ' -fopenmp').strip()
            makeenv['LDFLAGS'] = ldflags
            print("Linux OpenMP build: linking the Forthon extensions with LDFLAGS='{}'".format(makeenv['LDFLAGS']))
        # Call compiler
        if call(['make',COMPILEFLAGS,OMPFLAGS,'-f','Makefile.Forthon'], env=makeenv) != 0:
            raise SystemExit("UEDGE build failure")
  ```
- **PATTERN**: `setup.py:731-740` (serial/OpenMP branch), `setup.py:770` (make call).
- **GOTCHA**: `env=None` means inherit, so macOS and `--serial` run exactly the old call. Build the dict at call time
  so that `OMP=TRUE` (set at `:740`) and `NOCLEAN` are carried over. Do not change `os.environ`, or the `uedgeC`
  link would change. `platform` is the `sys.platform` string (`setup.py:14`), not the `platform` module. All edits
  stay below `setup.py:697`, so the line references locked in `.claude/context/refs.lock.json` (all ≤ 697) do not
  move. The user's `LDFLAGS` string is appended to, not split and re-joined, so a quoted argument with whitespace
  survives unchanged (review L1-m6). `.strip()` only matters when `LDFLAGS` is unset or empty.
  `--noclean` does not relink: a Linux build tree left over from before the fix keeps its old extensions (the
  `Makefile.Forthon` `*pydep` stamps). The default clean build covers this, and every build in this plan is clean.
- **VALIDATE**: `python -c "import ast,sys; ast.parse(open('setup.py').read())"`; on macOS rebuild both venvs
  (task 3) and run the `--debug`-free macOS checks.

### 2. COMMIT the code
- `git -C $WT commit setup.py` with a repo-style message ("Links the Forthon extensions with -fopenmp in the Linux
  OpenMP build"), body naming AIUE-64, ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Linux
  validation clones this commit from the read-only repo mount.

### 3. VALIDATE on macOS (after the change)
- Build `AIUE-64-omp` and `AIUE-64-serial` from the committed FIX (task 2) with a clean tree: `git -C $WT status
  --porcelain` must be empty before building (commit or move out any pending review files first). Then run M1-M4.
- **ORDERING (review L1-m4)**: run M3 (the AIUE-53 serial check) right after these builds and **before any later
  commit** (task 5 evidence and code-facts commits). `serial_check.py` marks a run `INCOMPLETE` (not a gate) when
  the source tree is dirty or when HEAD was committed after the build was installed (`is_stale`,
  `serial_check.py:233-237,272-275`). If M3 has to be re-run after a later commit (for example after review fixes),
  rebuild both venvs from the then-current HEAD with a clean tree first.

### 4. VALIDATE on Linux (Docker, linux/amd64 emulated, `--cpus 5`, one container at a time)
See "Testing strategy" L1-L6. The scripts and outputs are kept in the session scratchpad during the runs; the
selected records are committed in task 5 (owner decision, see Notes on records).

### 5. COMMIT the Linux evidence, then UPDATE `.claude/context/architecture.md` (two commits)
- **Evidence commit** (artifact class `docs/rca/**`, `branching.md:13`): copy the record set listed in Notes on
  records to `docs/rca/AIUE-8-data/linux/aiue64/` and commit it on its own. Only after M3 has run (task 3 ordering).
- **Code-facts commit**: in §Build pipeline,
  - correct step 3: `make -f Makefile.Forthon` produces the `uedge/<pkg>py` extensions only, not `uedgeC`
    (`Makefile.Forthon` only removes `uedgeC.so`; review L1-m5). Add: "In the OpenMP build on Linux, `setup.py` runs
    that make with `-fopenmp` appended to `LDFLAGS`, because Forthon passes no OpenMP flag to the extension link
    (`setup.py:<new line>`). macOS relies on `uedgeC` loading libomp."
  - add (as a new step between the current 3 and 4, renumbering 4 → 5): "`build.run` then builds the C extension
    `uedgeC` (`setup.py:<build.run line>,<Extension lines>`), linked with `-fopenmp`." Keep the existing import
    step's text; it is still true.
  - **Line numbers (review L2-m1)**: take every new `setup.py` line number from the *edited* file (`grep -n`), not
    from this plan: task 1 adds about 16 lines above `build.run(self)` and the `uedgeC` `Extension` (pre-edit
    `:772`, `:781-803`). `--update` locks whatever text is on the cited line without checking it, so check every
    new citation by eye before `--update`.
- **Drift check (review L1-m5)**: the new `setup.py:<line>` citations will be reported as **NEW** (exit 1) by
  `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`, so `--update` is certain to be needed.
  Check that NEW (for the citations just added and verified by hand) is the only problem reported; only then run
  `--update` (it re-locks every reference), and commit `refs.lock.json` with `architecture.md`. If
  `origin/v9-develop` lags the local base, run `--changed v9-develop` too.
- **GOTCHA**: the code-facts commit is separate, with trailer `AI-layer: code-facts`. The hook (`change_kind.py`)
  checks it. Both commits make the task-3 venvs stale for `serial_check.py` (see task 3 ordering).
- **VALIDATE**: the drift check is clean after `--update`.

### 6. Validate gate and review
- `validate` skill, run **after the last commit** (it rebuilds into the active worktree venv, so its builds come
  from the final HEAD): serial build + smoke + `D_only` (setup.py change) and `--omp` (build change to the OpenMP
  path). The macOS `--omp` CheckPandf1/CheckJac output must match the same check on `venvs/base-omp`. The base code
  is pre-AIUE-56, so a known Jacobian difference may show up in both; this change must not make anything new show
  up.
- Adversarial implementation review (`end-to-end-feature` §Adversarial review loop, `stage: implementation`).

## Testing strategy (pre-registered; expected outcomes fixed before running)

**macOS (arm64, Homebrew LLVM clang + gfortran, Forthon 0.10.10, Python 3.13).**
- **M1 link unchanged**: for both the OpenMP and the serial build, before (task 0) vs after: (a) the normalised
  `-bundle` link command lines of all 11 extensions are identical (`diff` empty); (b) `otool -L` identical per
  extension; libomp appears **only** in `uedgeC` (as in `venvs/base-omp`, `venvs/base-serial`); no `libgomp`
  anywhere; (c) `nm -u | grep -E '^_(GOMP_|omp_)'` symbol sets identical before and after. Expected values,
  checked on `venvs/base-omp`/`base-serial` while revising this plan: OpenMP build apipy 4, bbbpy 4, ppppy 13,
  others 0; serial build ppppy 2 (`_omp_get_thread_num_`, `_omp_get_wtime_`, from `ppp/parallel.F90:213,286,340`),
  others 0 (review L1-m1; the unanchored pattern also matched UEDGE's own `_jac_calc_omp_` in serial `ppppy`);
  (d) the build log does **not** contain the new `Linux OpenMP build:` line.
- **M2 import**: `cd /tmp && HOME=$(mktemp -d) OMP_NUM_THREADS=1 $V/AIUE-64-omp/bin/python -I -c "import uedge;
  from uedge import bbb, ppp; print(bbb.uedge_ver, ppp.OMPParallelJac)"` succeeds; same for serial (without
  `ppp` attribute checks beyond import).
- **M3 AIUE-53 serial check — the gate**: tool from `uedge-wt/AIUE-53` (`15ae327`),
  `--base-python $V/base-serial/bin/python --new-python $V/AIUE-64-serial/bin/python
  --base-omp-python $V/base-omp/bin/python --new-omp-python $V/AIUE-64-omp/bin/python --jobs 4 --cases all
  --pytests-dir /Users/holma/Documents/uedge/src/uedge-pytests --out $SCR/serial_check`. Expected: `RESULT: AGREE (bitwise identical; complete
  gate)` for both pairs (`serial`, `omp0`). Quote the build lines and RESULT line verbatim. (On macOS the change
  is inactive by construction, so this checks that nothing changed by accident.) Runs on builds installed from the
  committed FIX with a clean tree, before any later commit (task 3 ordering); an `INCOMPLETE` caused by staleness
  means "rebuild and re-run", not a pass.
- **M4 validate**: serial build, smoke, `D_only` passes; `--omp` check result is the same as on `base-omp`.

**Linux (Docker Desktop, `--platform linux/amd64` under Rosetta, `--cpus 5 --memory 7g`, one container at a time,
repo mounted read-only at `/mnt/repo`; builds clone the commit, so the tree is clean).** Build with the AIUE-62
`build_uedge.sh NAME COMMIT` (CI pip deps `forthon>=0.10.7 numpy==1.26.4 h5py pytest`, `python -m pip install -v .`,
log in `/out/build_NAME.log`), always under `env -u LDFLAGS` unless stated. A serial variant runs the same with
`-C "--build-option=--serial"` (a one-line copy of the script, `build_uedge_serial.sh`).
Commits: `BASE=4faed39`, `FIX=<task 2 commit>`.
- **L1 Ubuntu 24.04 red → green** (`aiue62-ubuntu:amd64`, gcc 13.3, Python 3.12): build `base` (BASE, no LDFLAGS)
  and `fix` (FIX, no LDFLAGS). Expected: `base` import → exit 127 with `undefined symbol: GOMP_parallel` (the bug
  reproduces in the same container); `fix` import exits 0. Saved verbatim to `/out/import.txt`.
  **Unresolved OpenMP symbols (replaces the round-1 `LD_BIND_NOW=1` import, review L1-M1):** for every extension of
  both builds, `ldd -r <ext>.so 2>&1 | grep -E 'undefined symbol: (GOMP_|omp_)'`. Expected on `base`: non-empty
  for `apipy`, `bbbpy` and `ppppy`, empty for the other 8. Expected on `fix`: empty for all 11. Saved to
  `/out/ldd_r_omp.txt`. The filter is needed because `ldd -r` also lists the Python C-API symbols and the
  cross-package Forthon symbols as undefined; those are resolved at import through `RTLD_GLOBAL` and lazy binding
  and are not part of this check. (`LD_BIND_NOW=1` is not used anywhere in this plan: the extensions have forward
  references across packages, e.g. `uedgeC` → `exmain_f_` in `bbbpy`, `bbbpy` → `svrpy`/`apipy`/`aphpy`/`ppppy`,
  which only lazy binding, Forthon's `-Wl,-z,lazy`, resolves. Under `LD_BIND_NOW=1` the import fails on base and
  fix alike.)
- **L2 Ubuntu NEEDED / ldd**: for every extension of `fix`, `readelf -d` NEEDED and `ldd`. Expected: `apipy`, `bbbpy`,
  `ppppy` NEED `libgomp.so.1`. Invariant check: every extension with undefined OpenMP runtime symbols
  (`nm -D --undefined-only <ext>.so | awk '{print $NF}' | grep -E '^(GOMP_|omp_)'`, anchored as in M1(c)) has
  `libgomp.so.1` in NEEDED. `ldd` shows no `not found`. Exactly one OpenMP runtime:
  no `libomp`/`libiomp5` anywhere. `uedgeC` NEEDED unchanged from `base` (`libreadline.so.8 libc.so.6`). The build
  log contains `Linux OpenMP build: linking the Forthon extensions with LDFLAGS='-fopenmp'` and each Forthon
  extension's `-shared` link line contains `-fopenmp`; the `uedgeC` link line is identical to `base`'s.
- **L3 equivalence with the workaround**: build `wkld` = BASE with `LDFLAGS=-fopenmp` (the AIUE-62 recipe).
  Expected: NEEDED lists of all 11 extensions are identical between `fix` and `wkld`. The Forthon-extension link
  lines are identical after normalising the clone path. The only expected difference is that `wkld`'s `uedgeC`
  link also carries a second `-fopenmp`.
- **L4 serial unchanged on Linux**: build `base-ser` (BASE) and `fix-ser` (FIX) with `--serial`. Expected: all 11
  normalised link lines identical, NEEDED identical, no `libgomp` in any extension, and the new line absent from the
  log. Both import. The anchored `nm -D --undefined-only` OpenMP set and the L1 `ldd -r` filter give the same
  output for both: `ppppy` lists `omp_get_thread_num_` and `omp_get_wtime_` (the serial `ppppy` calls them, see
  the side finding; unresolved on this `--as-needed` toolchain), every other extension is empty. That is the
  pre-existing quirk for the follow-up ticket AIUE-67, recorded, not fixed here.
- **L5 AIUE-57 replay + short Te-box flow** (Ubuntu, on the `fix` build): clone the AIUE-57 harness
  (`clone_harness.sh 8ee189d76b0232cedfe17088574935b10b857df5`). The `fix` build already replayed the workflow's
  "Install pip dependencies" and "Build UEDGE (default OpenMP build)" steps (L1: same pip commands,
  `gfortran --version | head -1`, `python -m pip install -v .`, no LDFLAGS). Then run its "Unit tests, smoke test
  and OpenMP test flow" step:
  `OMP_CI_OUT=/out/ci OMP_CI_CORES=4 OMP_CI_MAX_JOBS=1 OMP_CI_GATE=none OMP_CI_FLOWS="tebox1|tebox|2,4|2|jac|none"
  PYTHON=/work/venv-fix/bin/python bash /work/harness/tests/deterministic_omp/ci/run_omp_ci.sh pr`.
  Expected: harness unit tests pass, the smoke test prints `uedge_ver ... OMPParallelJac ...` (the step that
  failed with exit 2 before the fix), and the Te-box flow (serial reference + Jacobian arm at 2 and 4 threads, K=2,
  one evaluation) completes. Exit 0 under `--gate none`, meaning no harness error. Also record whether the Jacobian
  arm agrees with serial. It is **report-only**: BASE is pre-AIUE-56, so a mismatch is expected and is not this
  ticket's to fix. A separate probe (a script file, run once, `OPENBLAS_NUM_THREADS=1` so numpy starts no pool of
  its own) shows that OpenMP threads actually ran (review L1-m7; the `libgomp` mapping alone proves only what L2
  proves, since `bbbpy` NEEDs it): import, record `n0 = len(os.listdir('/proc/self/task'))`, set
  `ppp.OMPParallelJac=1; ppp.Nthreads=2`, run one Te-box Jacobian evaluation (the harness worker or a single
  `bbb.exmain()` on the tebox preset), then record `n1` the same way and `grep -c libgomp /proc/self/maps`.
  Expected: `n1 - n0 ≥ 1` (libgomp keeps its worker thread in the pool after the parallel region) and the
  `libgomp` count ≥ 1. Saved to `/out/thread_probe.txt`.
  **Amendment to a pre-registered check (main-session decision, written before the re-run).** The probe above ran
  on `1e8eb78` and gave `RESULT FAIL n1-n0 = 0` (n0 = n1 = 2). This was a probe-design error, not a fix failure:
  the libgomp workers already exist right after `import uedge`. A diagnostic (not a gate) showed 2 threads after
  import at `OMP_NUM_THREADS=2`, 4 at 4 and 1 at 1, most likely from the parallel regions in Forthon's `--omp`
  wrappers. So n1−n0 cannot rise. The failed run and the diagnostic stay in the evidence. **Amended probe**
  (`thread_probe2.py`, run once on a fresh `fix` build of `1e8eb78` in the Ubuntu container, as the formal L5
  result):
  - Baseline after `import uedge` and the deck. The measure is each thread's CPU time during the Te-box `exmain`
    (one evaluation, `ftol=1e20`), from `/proc/self/task/<tid>/schedstat` (ns). If `schedstat` is missing, the
    probe uses utime+stime from `stat` (clock ticks) and prints the resolution it used.
  - Four processes, each a fresh interpreter with `OPENBLAS_NUM_THREADS=1`:
    - jac arm at `OMP_NUM_THREADS=Nthreads=2`;
    - jac arm at `OMP_NUM_THREADS=Nthreads=4`;
    - serial-arm control (`OMPParallelJac=0`) at `OMP_NUM_THREADS=2`;
    - serial-arm control at `OMP_NUM_THREADS=4`.
  - **Expected**, for each N in {2, 4}: every worker thread's (non-main) CPU-time increase during the jac-arm
    `exmain` is ≥ max(5 × the largest worker increase in the serial-arm control at the same N, 1 ms). Also, the
    `libgomp` mappings are ≥ 1 and `ppp.OMPParallelJac` is 1 after `exmain`.
  - The 1 ms floor stops a control of 0 from passing noise. A tick fallback makes the floor one tick.
  - Worker CPU time in a parallel region includes libgomp's spin-wait. That still shows the worker took part in
    OpenMP regions during the Jacobian; the serial-arm control, which has no region during `exmain`, separates
    it from idle pool threads.
  - Saved to `/out/thread_probe2.txt`.
  - *Post-run note (implementation review I1-m2; the pre-registered text above is left as written):*
    - "has no region during `exmain`" was inaccurate. The control's workers gained 5.3 ms (N=2) and 6.0–10.3 ms
      (N=4) of CPU during `exmain`, so either the serial arm has OpenMP regions there or spin from earlier regions
      carries on. The 5× margin covers both cases.
    - The 5× factor was chosen after the diagnostic had shown rough magnitudes (a jac worker gained 7 ticks; control
      workers on another preset gained 1–2 ticks). So the threshold was fixed before the run, but not blind.
    - Result: 10.1× the control at N=2 and at least 8.0× at N=4.
  Deviations from CI, stated up front: Python 3.12 (Ubuntu system) instead of setup-python 3.11; emulated amd64;
  `OMP_CI_FLOWS`/`OMP_CI_GATE` override the `pr` set (the full `pr` set under emulation is too slow, and its gate
  is red on pre-AIUE-56 code by design, see the workflow's DO-NOT-MERGE note).
- **L6 Debian 12** (`aiue62:amd64`, gcc 12.2, Python 3.11 = CI's Python): build `fix` (no LDFLAGS). Expected: import
  exit 0; the L1 `ldd -r` OpenMP filter empty for all 11 extensions. NEEDED as in L2 (matches AIUE-62
  `build_info.txt` "fixld" build with the `LDFLAGS=-fopenmp` workaround: `apipy`, `bbbpy`, `ppppy` NEED
  `libgomp.so.1`; `uedgeC` NEEDS only `libreadline.so.8 libc.so.6`). Record only (no expected value, not a gate): `gcc -dumpspecs | grep -c as-needed`, to put the
  Debian mechanism on record (review L1-m3). The base failure on Debian is already on record (AIUE-62
  `build_info.txt`) and is not rebuilt.
- **Not claimed**: arm64 Linux, non-`--as-needed` distributions (RHEL/Fedora/manylinux), `CC=clang` on Linux,
  cibuildwheel Linux wheels. These are untested. The wheel check is deferred (owner decision): auditwheel already
  vendors `libgomp.so.1` today, because manylinux gcc does not default to `--as-needed` and `uedgeC` NEEDs it there;
  after the fix `apipy`/`bbbpy`/`ppppy` NEED the same soname, and auditwheel grafts one copy per soname, so the
  wheel still carries one runtime (review open question 3, reasoned, not run).

**Pass/fail.** The ticket's acceptance (Jira AIUE-64) maps to: L1 + L6 (imports without LDFLAGS on Ubuntu 24.04 and
Debian 12, no unresolved OpenMP symbol under `ldd -r`), M1 + M2 (macOS OpenMP unchanged), M3 (AIUE-53 AGREE, both pairs), L5 (AIUE-57 smoke passes on the CI
distribution). L2-L4 are the supporting link evidence. Any deviation from an expected value above is reported
verbatim and stops the ticket. It is not explained away.

## AI-layer facts affected
Checked `CLAUDE.md` and `.claude/context/*.md` for `setup.py`, link, `LDFLAGS`, `-fopenmp`, `uedgeC`, `OMPargs`:
- `.claude/context/architecture.md` §Build pipeline step 3: incomplete after the change (it does not say how the
  extensions get the OpenMP runtime), and already wrong in saying the make produces `uedgeC` (`build.run` does,
  review L1-m5). Correct it, add the sentence and a `uedgeC` step (task 5).
- `CLAUDE.md:29` ("OpenMP by default; needs gfortran with -fopenmp; on macOS set CC to a libomp-capable clang"):
  still true, no edit.
- `.claude/context/openmp-jacobian.md:23` (`OMPargs`): still true.
- `.claude/context/testing.md:48` ("OpenMP paths are not tested in CI"): still true on `v9-develop` (AIUE-57 is not
  merged).
- `refs.lock.json` `setup.py:*` entries are all ≤ 697; the edit is at ~769, so existing references do not drift.
  The new `setup.py` citations in `architecture.md` are reported as NEW and need `--update` (task 5).

## Validation commands
- `validate` skill with suites `D_only`, `--omp` (macOS).
- AIUE-53: `python uedge-wt/AIUE-53/tests/deterministic_omp/harness/serial_check.py ...` (M3).
- Docker L1-L6 as above. Driver logs and outputs go to `<scratchpad>/AIUE-64/linux/{ubuntu,debian}/`.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` (NEW expected for the new citations,
  then `--update`, then clean).

## Acceptance criteria
- [ ] `import uedge` (OpenMP build, no `LDFLAGS`) succeeds on Ubuntu 24.04 and Debian 12, and `ldd -r` reports no
      undefined `GOMP_*`/`omp_*` symbol in any of the 11 extensions (on Ubuntu `base` it reports them for `apipy`,
      `bbbpy`, `ppppy`). (The Jira AIUE-64 acceptance text does not mention `LD_BIND_NOW`; checked, no change needed.)
- [ ] `apipy`/`bbbpy`/`ppppy` NEED `libgomp.so.1` on Linux; one OpenMP runtime; `uedgeC` link unchanged
- [ ] macOS OpenMP and serial links unchanged (link lines, `otool -L`, `nm -u`), both import
- [ ] Linux serial build link unchanged
- [ ] AIUE-53 serial check `RESULT: AGREE (bitwise identical; complete gate)`, both pairs, on builds that are not
      stale against HEAD
- [ ] AIUE-57 workflow's build + smoke replayed green on Ubuntu 24.04; short Te-box flow completes; the amended
      thread probe (L5 amendment) shows the workers working during the Jacobian
- [ ] Linux evidence committed under `docs/rca/AIUE-8-data/linux/aiue64/`
- [ ] `architecture.md` updated (step 3 corrected, `uedgeC` step added; code-facts commit); drift check clean after
      `--update`
- [ ] Adversarial implementation review APPROVE

## Notes
- **Records (owner decision: commit on the branch).** Commit a small set under
  `docs/rca/AIUE-8-data/linux/aiue64/` (artifact class): the driver scripts, `import.txt`, `ldd_r_omp.txt`,
  `needed.txt`, the link-line diffs (L2-L4), `thread_probe.txt` (the failed original), the diagnostic,
  `thread_probe2.txt` (the amended probe), the macOS M1/M2 records (`mac_before`/`mac_after`), the M3
  `serial_check` output, the Debian `gcc -dumpspecs` count, and the CI replay `ci.log`/`summary.md`. Not the build trees or full build logs. The commit comes in task 5, after M3 (task 3
  ordering, review L1-m4).
- **PR precondition (review L1-m8).** The branch starts from local `v9-develop` `4faed39`, which is 7 AI-layer-only
  commits (`.claude/`, `CLAUDE.md`, `docs/`) ahead of `origin/v9-develop` `3865c79`. Open the PR only once those
  commits are on the remote base (or after rebasing onto it), so the PR diff does not carry AI-layer process
  changes. No push in this ticket's steps.
- **Upstream.** Forthon should add the compiler's OpenMP link flag when `--omp` is given (`Forthon_builder.py`
  `extra_link_args`). Worth a Forthon issue; this setup.py change can stay as a belt-and-braces fix after that,
  since the `-fopenmp` dedupe keeps it harmless.
- **Risk.** If `CC` is set on Linux to a driver that rejects `-fopenmp` at link time, the build now fails at the
  extension link instead of at import. `uedgeC` is already linked with `-fopenmp` by the same `CC` (`setup.py:799`;
  it is not compiled with it), so the build would fail there anyway. No new requirement.
- **Confidence** for one-pass execution: 8/10 (the mechanism is the validated workaround; the remaining risk is
  emulation time and harness wiring in L5).

## Open questions — resolved by the owner (round 1)
1. *Linux evidence*: committed on this branch under `docs/rca/AIUE-8-data/linux/aiue64/` (task 5), after M3.
2. *Serial `uedgeC` linked with `-fopenmp`*: left as is here; the follow-up ticket **AIUE-67** (filed by the main
   session) carries review finding L1-m2 (the serial `ppppy` depends on it).
3. *Wheel/auditwheel check*: deferred. The wheel already vendors `libgomp` today; see "Not claimed".
4. *L5 flow set*: the reduced set is enough. The unmodified `pr` set is AIUE-57's own validation.
