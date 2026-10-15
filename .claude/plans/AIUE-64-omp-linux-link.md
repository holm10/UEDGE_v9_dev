# Feature: AIUE-64 — link the Forthon extensions with -fopenmp in the Linux OpenMP build

Validate the patterns and file references below before implementing.

## Summary
**Type**: Python/Build (bug fix in `setup.py`)
**Complexity**: Low (one guarded block in `uedgeBuild.run`); the validation is the larger part
**Default results**: Unchanged. No Fortran, `.v` or compile flag changes. Only the link of the Forthon extensions in
the **Linux OpenMP** build changes. The serial build (every platform) and the macOS OpenMP build are not touched.
**Packages / files**: `setup.py` (product), `.claude/context/architecture.md` (code-facts, one sentence)
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
2. *`uedgeC`* is the only extension `setup.py` links itself (`setup.py:781-803`). Its
   `extra_link_args=FLAGS['CARGS']+[...]` (`setup.py:799`) carries `-fopenmp`. Its C sources contain no OpenMP
   code, so on Debian/Ubuntu, whose gcc links with `--as-needed` by default (`gcc -dumpspecs`: 3 occurrences,
   `ubuntu/build_summary.txt`), the linker drops `libgomp` from `uedgeC` too (AIUE-62 `fma_fixld.txt`:
   `uedgeC` NEEDS only `libreadline.so.8 libc.so.6`).

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
change the serial build, which this ticket must not do. It is recorded as an open question.

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
- *User `LDFLAGS` kept*: `-fopenmp` is appended to any `LDFLAGS` already set (CI's wheel job sets
  `LDFLAGS: "-L${LIBOMPPATH}/lib"`, `build-test-wheel.yml`). It is not added twice if the user already passes it,
  so a build that uses the AIUE-62 workaround gets an identical link.

**Alternatives considered (rejected).**
- *`--libs gomp` in `OMPargs` (Forthon `-l`)*: hard-codes the GNU runtime name into the link even when `CC` is
  clang (`clang -fopenmp` would pull libomp into `uedgeC`, giving two runtimes on non-`--as-needed` systems), and it
  bypasses the driver's own OpenMP link logic. `-fopenmp` lets the C driver that already compiled `uedgeC`
  with `-fopenmp` pick its own runtime. That is the same rule `setup.py` already uses for `uedgeC`.
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
  Record for every `*.so`: `otool -L`, `otool -hv`, `nm -u | grep -E 'GOMP_|omp_'`, and the link command lines
  (`grep -E ' -bundle ' log`) with the venv and build-temp paths normalised (`sed` the tree and venv prefixes).
- **VALIDATE**: both import (the build script's own smoke line prints `uedge_ver`).

### 1. UPDATE `setup.py` — `uedgeBuild.run`, replace the make call at `setup.py:769-771`
- **IMPLEMENT** (exact intent; keep the wording close to this):
  ```python
        # Linux OpenMP build: link every Forthon extension with -fopenmp (AIUE-64). Forthon's --omp,
        # --fargs and --cargs reach only the compile lines, so bbbpy, ppppy and apipy were linked without
        # the OpenMP runtime; with the --as-needed default of Debian/Ubuntu gcc, uedgeC drops it as well,
        # and import failed with "undefined symbol: GOMP_parallel". setuptools appends LDFLAGS to every
        # extension link. Set it for the Forthon make only, so the uedgeC link below is unchanged.
        # macOS is left alone: there, uedgeC loads libomp and the flat-namespace extensions bind to it.
        makeenv = None
        if not arglist['serial'] and platform.startswith('linux'):
            makeenv = dict(os.environ)
            ldflags = makeenv.get('LDFLAGS', '').split()
            if '-fopenmp' not in ldflags:
                ldflags.append('-fopenmp')
            makeenv['LDFLAGS'] = ' '.join(ldflags)
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
  move.
- **VALIDATE**: `python -c "import ast,sys; ast.parse(open('setup.py').read())"`; on macOS rebuild both venvs
  (task 3) and run the `--debug`-free macOS checks.

### 2. COMMIT the code
- `git -C $WT commit setup.py` with a repo-style message ("Links the Forthon extensions with -fopenmp in the Linux
  OpenMP build"), body naming AIUE-64, ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Linux
  validation clones this commit from the read-only repo mount.

### 3. VALIDATE on macOS (after the change)
See "Testing strategy" M1-M4.

### 4. VALIDATE on Linux (Docker, linux/amd64 emulated, `--cpus 5`, one container at a time)
See "Testing strategy" L1-L6. Scripts go in `tests/deterministic_omp/linux/aiue64/` on this branch only if they are
committed as the record (see Notes on records). Otherwise they go in the session scratchpad, and the plan's results
section quotes them.

### 5. UPDATE `.claude/context/architecture.md` §Build pipeline (code-facts commit)
- **IMPLEMENT**: add to step 3: "In the OpenMP build on Linux, `setup.py` runs that make with `-fopenmp` appended
  to `LDFLAGS`, because Forthon passes no OpenMP flag to the extension link (`setup.py:<new line>`). macOS relies on
  `uedgeC` loading libomp (step 4)." Then run `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`
  (and, if `origin/v9-develop` lags the local base, `--changed v9-develop` too) and update `refs.lock.json` only if
  the tool says so.
- **GOTCHA**: separate commit, trailer `AI-layer: code-facts`. The hook (`change_kind.py`) checks it.
- **VALIDATE**: the drift check is clean.

### 6. Validate gate and review
- `validate` skill: serial build + smoke + `D_only` (setup.py change) and `--omp` (build change to the OpenMP
  path). The macOS `--omp` CheckPandf1/CheckJac output must match the same check on `venvs/base-omp`. The base code
  is pre-AIUE-56, so a known Jacobian difference may show up in both; this change must not make anything new show
  up.
- Adversarial implementation review (`end-to-end-feature` §Adversarial review loop, `stage: implementation`).

## Testing strategy (pre-registered; expected outcomes fixed before running)

**macOS (arm64, Homebrew LLVM clang + gfortran, Forthon 0.10.10, Python 3.13).**
- **M1 link unchanged**: for both the OpenMP and the serial build, before (task 0) vs after: (a) the normalised
  `-bundle` link command lines of all 11 extensions are identical (`diff` empty); (b) `otool -L` identical per
  extension; libomp appears **only** in `uedgeC` (as in `venvs/base-omp`, `venvs/base-serial`); no `libgomp`
  anywhere; (c) `nm -u` OpenMP symbol sets identical (apipy 4, bbbpy 4, ppppy 13, others 0, OpenMP build;
  0 everywhere in serial); (d) the build log does **not** contain the new `Linux OpenMP build:` line.
- **M2 import**: `cd /tmp && HOME=$(mktemp -d) OMP_NUM_THREADS=1 $V/AIUE-64-omp/bin/python -I -c "import uedge;
  from uedge import bbb, ppp; print(bbb.uedge_ver, ppp.OMPParallelJac)"` succeeds; same for serial (without
  `ppp` attribute checks beyond import).
- **M3 AIUE-53 serial check — the gate**: tool from `uedge-wt/AIUE-53` (`15ae327`),
  `--base-python $V/base-serial/bin/python --new-python $V/AIUE-64-serial/bin/python
  --base-omp-python $V/base-omp/bin/python --new-omp-python $V/AIUE-64-omp/bin/python --jobs 4 --cases all
  --pytests-dir /Users/holma/Documents/uedge/src/uedge-pytests --out $SCR/serial_check`. Expected: `RESULT: AGREE (bitwise identical; complete
  gate)` for both pairs (`serial`, `omp0`). Quote the build lines and RESULT line verbatim. (On macOS the change
  is inactive by construction, so this checks that nothing changed by accident.)
- **M4 validate**: serial build, smoke, `D_only` passes; `--omp` check result is the same as on `base-omp`.

**Linux (Docker Desktop, `--platform linux/amd64` under Rosetta, `--cpus 5 --memory 7g`, one container at a time,
repo mounted read-only at `/mnt/repo`; builds clone the commit, so the tree is clean).** Build with the AIUE-62
`build_uedge.sh NAME COMMIT` (CI pip deps `forthon>=0.10.7 numpy==1.26.4 h5py pytest`, `python -m pip install -v .`,
log in `/out/build_NAME.log`), always under `env -u LDFLAGS` unless stated. A serial variant runs the same with
`-C "--build-option=--serial"` (a one-line copy of the script, `build_uedge_serial.sh`).
Commits: `BASE=4faed39`, `FIX=<task 2 commit>`.
- **L1 Ubuntu 24.04 red → green** (`aiue62-ubuntu:amd64`, gcc 13.3, Python 3.12): build `base` (BASE, no LDFLAGS)
  and `fix` (FIX, no LDFLAGS). Expected: `base` import → exit 127 with `undefined symbol: GOMP_parallel` (the bug
  reproduces in the same container); `fix` import exits 0. The import is also run with `LD_BIND_NOW=1`, so that
  every lazily bound symbol of all extensions must resolve at load; expected exit 0. Saved verbatim to
  `/out/import.txt`.
- **L2 Ubuntu NEEDED / ldd**: for every extension of `fix`, `readelf -d` NEEDED and `ldd`. Expected: `apipy`, `bbbpy`,
  `ppppy` NEED `libgomp.so.1`. Invariant check: every extension with undefined `GOMP_*`/`omp_*` symbols
  (`nm -D --undefined-only`) has `libgomp.so.1` in NEEDED. `ldd` shows no `not found`. Exactly one OpenMP runtime:
  no `libomp`/`libiomp5` anywhere. `uedgeC` NEEDED unchanged from `base` (`libreadline.so.8 libc.so.6`). The build
  log contains `Linux OpenMP build: linking the Forthon extensions with LDFLAGS='-fopenmp'` and each Forthon
  extension's `-shared` link line contains `-fopenmp`; the `uedgeC` link line is identical to `base`'s.
- **L3 equivalence with the workaround**: build `wkld` = BASE with `LDFLAGS=-fopenmp` (the AIUE-62 recipe).
  Expected: NEEDED lists of all 11 extensions are identical between `fix` and `wkld`. The Forthon-extension link
  lines are identical after normalising the clone path. The only expected difference is that `wkld`'s `uedgeC`
  link also carries a second `-fopenmp`.
- **L4 serial unchanged on Linux**: build `base-ser` (BASE) and `fix-ser` (FIX) with `--serial`. Expected: all 11
  normalised link lines identical, NEEDED identical, no `libgomp` in any extension, and the new line absent from the
  log. Both import.
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
  ticket's to fix. A run that shows `/proc/<pid>/maps` without `libgomp.so.1` during the threaded run counts as
  failed; the check runs once in a separate probe: import, `ppp.OMPParallelJac=1; ppp.Nthreads=2`, Te-box
  evaluation via the harness worker or a single `bbb.exmain()` on the tebox preset, then `grep -c libgomp
  /proc/self/maps` ≥ 1.
  Deviations from CI, stated up front: Python 3.12 (Ubuntu system) instead of setup-python 3.11; emulated amd64;
  `OMP_CI_FLOWS`/`OMP_CI_GATE` override the `pr` set (the full `pr` set under emulation is too slow, and its gate
  is red on pre-AIUE-56 code by design, see the workflow's DO-NOT-MERGE note).
- **L6 Debian 12** (`aiue62:amd64`, gcc 12.2, Python 3.11 = CI's Python): build `fix` (no LDFLAGS). Expected: import
  exit 0, also with `LD_BIND_NOW=1`. NEEDED as in L2 (matches AIUE-62 `fma_fixld.txt`: `apipy`, `bbbpy`, `ppppy`
  NEED `libgomp.so.1`; `uedgeC` NEEDS only `libreadline.so.8 libc.so.6`). The base failure on Debian is already on
  record (AIUE-62 `build_info.txt`) and is not rebuilt.
- **Not claimed**: arm64 Linux, non-`--as-needed` distributions (RHEL/Fedora/manylinux), `CC=clang` on Linux,
  cibuildwheel Linux wheels (auditwheel would now vendor libgomp into the wheel). These are untested and listed as
  open questions.

**Pass/fail.** The ticket's acceptance (Jira AIUE-64) maps to: L1 + L6 (imports without LDFLAGS on Ubuntu 24.04 and
Debian 12), M1 + M2 (macOS OpenMP unchanged), M3 (AIUE-53 AGREE, both pairs), L5 (AIUE-57 smoke passes on the CI
distribution). L2-L4 are the supporting link evidence. Any deviation from an expected value above is reported
verbatim and stops the ticket. It is not explained away.

## AI-layer facts affected
Checked `CLAUDE.md` and `.claude/context/*.md` for `setup.py`, link, `LDFLAGS`, `-fopenmp`, `uedgeC`, `OMPargs`:
- `.claude/context/architecture.md` §Build pipeline step 3: incomplete after the change (it does not say how the
  extensions get the OpenMP runtime). Add one sentence (task 5).
- `CLAUDE.md:29` ("OpenMP by default; needs gfortran with -fopenmp; on macOS set CC to a libomp-capable clang"):
  still true, no edit.
- `.claude/context/openmp-jacobian.md:23` (`OMPargs`): still true.
- `.claude/context/testing.md:48` ("OpenMP paths are not tested in CI"): still true on `v9-develop` (AIUE-57 is not
  merged).
- `refs.lock.json` `setup.py:*` entries are all ≤ 697; the edit is at ~769. Expect no drift (verified by the tool).

## Validation commands
- `validate` skill with suites `D_only`, `--omp` (macOS).
- AIUE-53: `python uedge-wt/AIUE-53/tests/deterministic_omp/harness/serial_check.py ...` (M3).
- Docker L1-L6 as above. Driver logs and outputs go to `<scratchpad>/AIUE-64/linux/{ubuntu,debian}/`.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`.

## Acceptance criteria
- [ ] `import uedge` (OpenMP build, no `LDFLAGS`) succeeds on Ubuntu 24.04 and Debian 12, also with `LD_BIND_NOW=1`
- [ ] `apipy`/`bbbpy`/`ppppy` NEED `libgomp.so.1` on Linux; one OpenMP runtime; `uedgeC` link unchanged
- [ ] macOS OpenMP and serial links unchanged (link lines, `otool -L`, `nm -u`), both import
- [ ] Linux serial build link unchanged
- [ ] AIUE-53 serial check `RESULT: AGREE (bitwise identical; complete gate)`, both pairs
- [ ] AIUE-57 workflow's build + smoke replayed green on Ubuntu 24.04; short Te-box flow completes
- [ ] `architecture.md` updated (code-facts commit); drift check clean
- [ ] Adversarial implementation review APPROVE

## Notes
- **Records.** The Linux scripts and outputs are evidence for the PR. Commit a small set on this branch (artifact
  class, e.g. `docs/rca/AIUE-8-data/linux/aiue64/` with `import.txt`, `needed.txt`, link-line diffs, and the CI
  replay `ci.log`/`summary.md`), not the build trees. The alternative is to keep them in the scratchpad and quote
  them in the PR. Main session to decide (open question 1).
- **Upstream.** Forthon should add the compiler's OpenMP link flag when `--omp` is given (`Forthon_builder.py`
  `extra_link_args`). Worth a Forthon issue; this setup.py change can stay as a belt-and-braces fix after that,
  since the `-fopenmp` dedupe keeps it harmless.
- **Risk.** If `CC` is set on Linux to a driver that rejects `-fopenmp` at link time, the build now fails at the
  extension link instead of at import. `uedgeC` is already compiled and linked with `-fopenmp` by the same `CC`
  (`setup.py:799`), so the build would fail there anyway. No new requirement.
- **Confidence** for one-pass execution: 8/10 (the mechanism is the validated workaround; the remaining risk is
  emulation time and harness wiring in L5).

## Open questions
1. Commit the Linux evidence on this branch (under `docs/rca/AIUE-8-data/linux/aiue64/`) or only quote it in the PR?
2. The serial build links `uedgeC` with `-fopenmp` (`setup.py:799` is evaluated before `--serial` strips `CARGS`),
   so serial macOS `uedgeC` loads libomp. Leave as is (this ticket keeps serial unchanged), or file a separate
   ticket?
3. The Linux wheel job (`build-test-wheel.yml` `build_wheels`, cibuildwheel/manylinux) is affected by the same code
   path; it will now link libgomp and auditwheel will vendor it. Is a cibuildwheel check in scope, or a follow-up?
4. Should L5 also run with `OMP_CI_SET=pr` unmodified once AIUE-56 is merged (on the AIUE-57 branch), or is that
   AIUE-57's own validation?
