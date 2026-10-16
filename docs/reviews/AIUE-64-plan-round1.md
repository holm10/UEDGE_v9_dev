# AIUE-64 plan review, round 1

Stage: plan. Ticket AIUE-64 (epic AIUE-8). Plan `.claude/plans/AIUE-64-omp-linux-link.md` at `75108da` on
`bugfix/v9-AIUE-64-omp-linux-link` (base local `v9-develop` `4faed39`). Reviewer: uedge-reviewer (read-only;
no Docker, no rebuilds).

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 8 MINOR.

## Summary

The root cause is right and I reproduced it from the sources. Forthon 0.10.10 never puts an OpenMP flag on the
extension link. setuptools appends `LDFLAGS` from the environment to `LDSHARED`. gcc's `-fopenmp` at link time
places `-lgomp` after the objects, so it survives `--as-needed`. The proposed fix (append `-fopenmp` to `LDFLAGS`
only in the environment of the Forthon `make`, only for Linux OpenMP builds) is minimal and well scoped. It leaves
the `uedgeC` link, macOS and `--serial` untouched by construction. It brings in no second OpenMP runtime, and deferring
the wheel question is safe.

The one MAJOR finding is in the validation. The pre-registered `LD_BIND_NOW=1` import (L1, L6, and the first
acceptance criterion) cannot succeed on any UEDGE build, because the extensions have forward cross-references
between them by design. Under the plan's own stop rule, that would halt the ticket for a reason that has nothing
to do with the fix. Several smaller expected values and orderings also need correcting before execution.

## Findings

### MAJOR

**L1-M1. The `LD_BIND_NOW=1` import check cannot pass, with or without the fix.**
Location: plan §Testing strategy L1 ("The import is also run with `LD_BIND_NOW=1` ... expected exit 0") and L6.
The first box of §Acceptance criteria.
- *What is wrong.* `src/uedge/__init__.py:21-33` loads `uedgeC` first, then `compy`, `grdpy`, `flxpy`, `bbbpy`,
  `svrpy`, `wdfpy`, `apipy`, `aphpy`, `ppppy` and `nclpy`, one after another. Several of them reference symbols that
  are only defined in extensions loaded *later*. That works only because of lazy binding. This is why Forthon adds
  `-Wl,-z,lazy` on Linux, and its comment at `Forthon_builder.py:463-470` says so ("breaks Warp (which has cross
  references across its shared objects)"). glibc's `LD_BIND_NOW` turns lazy binding off for `dlopen` too, even when
  the call passes `RTLD_LAZY`. It overrides `-z lazy`.
- *Evidence.* I compared `nm -u` against `nm -gU` across the extensions of `venvs/base-omp`, in import order:
  - `uedgeC` needs `_exmain_f_` from `bbbpy`. The call is at `bbb/exmain.c:91,135`, from the same source on Linux.
  - `bbbpy` needs 30 symbols from `svrpy`, 20 from `apipy`, 9 from `aphpy` and 4 from `ppppy` (`_initparallel_`,
    `_jac_calc_parallel_`, ...).

  So under `LD_BIND_NOW=1` the first `from . import uedgeC` should already fail with `undefined symbol: exmain_f_`,
  on both `base` and `fix`. This is reasoning from the symbol tables and glibc semantics; I did not run it on Linux
  (no Docker in my budget). On macOS `DYLD_BIND_AT_LAUNCH=1` did not fail the import, but dyld4 is not a model for
  glibc. Because of the plan's rule ("Any deviation ... stops the ticket"), the ticket would stop on L1.
- *Resolution.*
  - Remove `LD_BIND_NOW=1` from L1, L6 and the acceptance criterion. If the Jira AIUE-64 acceptance text contains
    it, change that text too and record the change.
  - Replace it with a check that targets the bug and can tell base from fix. For example, run
    `ldd -r <ext>.so 2>&1 | grep -E 'undefined symbol: (GOMP_|omp_)'` for every extension.
    - Expected on `base`: non-empty for `apipy`, `bbbpy` and `ppppy`.
    - Expected on `fix`: empty for all 11.
  - `ldd -r` will also list Python-API and cross-package symbols as undefined, which is why the output is
    filtered.
  - Alternatively, keep `LD_BIND_NOW` but pre-register its expected failure at `exmain_f_` for both builds, as an
    informational check only.

### MINOR

**L1-m1. M1(c): the expected serial values are wrong, and the symbol regex catches a UEDGE symbol.**
- *What is wrong.* The plan expects "0 everywhere in serial". On `venvs/base-serial`, `nm -u ppppy*.so | grep -E
  'GOMP_|omp_'` returns 3 symbols:
  - `_omp_get_thread_num_` and `_omp_get_wtime_`, which are real runtime references from `ppp/parallel.F90:213,286,340`;
  - `_jac_calc_omp_`, a UEDGE routine that the unanchored `omp_` matches.

  The OpenMP counts (apipy 4, bbbpy 4, ppppy 13) are correct.
- *Why it matters.* M1(c) is a before/after identity check, so the comparison is still valid. But the wrong
  side-expectation would trigger the plan's stop rule.
- *Resolution.* Correct the serial expectation. Anchor the pattern (macOS `'^_(GOMP_|omp_)'`, Linux
  `'^(GOMP_|omp_)'` on `nm -D --undefined-only` names), and use the same pattern in the L2 invariant.

**L1-m2. Input for open question 2 (the serial `uedgeC` quirk): the quirk is load-bearing.**
- *What I found.* Because of the finding above, the serial `ppppy` calls `omp_get_wtime`/`omp_get_thread_num`.
  - On macOS they resolve only because the serial `uedgeC` is still linked with `-fopenmp` (the `setup.py:799`
    quirk the plan describes, which I confirmed: `otool -L` of `base-serial` `uedgeC` lists `libomp.dylib`).
  - On Linux with `--as-needed` they are already unresolved in the serial build. This is a latent lazy-binding
    failure if `OMPTimingJacRow>0` or the debug print at `parallel.F90:286` is reached; I did not check whether a
    serial build can get there.
- *Scope.* Not this ticket. It is right to keep `--serial` unchanged here.
- *Resolution.* Record this in the follow-up for open question 2, so that the follow-up does not simply drop
  `-fopenmp` from the serial `uedgeC` link.

**L1-m3. Factual slips in the plan text.**
- §Alternatives ("the C driver that already compiled `uedgeC` with `-fopenmp`") and §Notes/Risk ("already compiled
  and linked with `-fopenmp`"): `uedgeC` is *linked* with `-fopenmp` but not compiled with it.
  `extra_compile_args=fcompiler.extra_compile_args` (`setup.py:801`), and the `uedgeC` compile lines in
  `uedge-wt/logs/build-base-omp.log:1851-1859` carry no `-fopenmp`. The Risk argument still holds, because the link
  driver is the same.
- The `gcc -dumpspecs` "3 occurrences" figure is in `ubuntu/import_default_ldflags.txt`, not
  `ubuntu/build_summary.txt`.
- That evidence covers Ubuntu only. For Debian 12, AIUE-62 shows the outcome (`uedgeC` NEEDs no libgomp) but not the
  mechanism. Say "observed on Debian 12", not "Debian gcc defaults to `--as-needed`", unless it is checked.
- Resolution: fix the wording.

**L1-m4. M3 provenance ordering.**
- *What is wrong.* `serial_check.py` makes a run non-gate (`INCOMPLETE`) in two cases:
  - the source tree is dirty;
  - the source HEAD was committed after the build was installed (`is_stale`, `serial_check.py:233-237,272-275`).

  Task 5 (the code-facts commit) and the owner-approved evidence commit both come after the task-3 builds. If M3
  or the task-6 `validate` is run, or re-run, after those commits, it will report `INCOMPLETE` instead of
  `AGREE ... complete gate`.
- *Resolution.* State that the "after" builds are installed from the committed FIX with a clean tree, and that M3
  runs before any later commit. Otherwise, rebuild after the last commit. Also note that the M1 "before" builds
  (task 0) reuse the venv names that the "after" builds overwrite, so save the M1 "before" records first.

**L1-m5. Drift check and `architecture.md` wording.**
- *Drift check.*
  - The new citation `setup.py:<new line>` will come out as **NEW** (exit 1), so `--update` is certain to be
    needed, not "only if the tool says so".
  - `--update` re-locks every reference, so run it only once NEW is the only problem reported.
  - The current drift check on the branch is clean (`--changed origin/v9-develop` → OK).
- *Wording.* Step 3 of §Build pipeline says the make produces "the `uedgeC` module". That is false: `uedgeC` is
  built by `build.run` (`setup.py:772,781-803`), and `Makefile.Forthon` only removes `uedgeC.so`. The plan edits
  this step and the new sentence relies on `uedgeC` (step 4), so correct it in the same code-facts commit.

**L1-m6. `LDFLAGS` round trip.**
- *What is wrong.* `' '.join(makeenv.get('LDFLAGS','').split())` normalises whitespace in the user's `LDFLAGS`. That
  is harmless for ordinary flags, but it changes a quoted argument that contains whitespace. setuptools splits
  `LDSHARED` with shell-style quoting.
- *Resolution.* Append `' -fopenmp'` to the original string when the token is absent. Optional.
- *Related note.* With `--noclean`, a Linux build tree left over from before the fix will not relink (the
  Makefile `*pydep` stamps). The default clean covers this; a one-line note is optional.

**L1-m7. L5's `/proc/self/maps` probe proves only what L2 already proves.**
- *What is wrong.* `bbbpy` NEEDs `libgomp.so.1` after the fix, so `libgomp` is mapped right after `import uedge`.
  The probe therefore passes whether or not a threaded region runs.
- *Resolution.* Also record evidence that more than one thread ran (for example the thread count `ppp` reports, or
  per-thread timing entries). Optional; the Te-box flow at 2 and 4 threads already runs `GOMP_parallel`.

**L1-m8. Merge precondition from the base choice.**
- *What is wrong.* The branch starts from local `v9-develop` `4faed39`, which is 7 commits ahead of
  `origin/v9-develop` `3865c79`. Those commits change only `.claude/`, `CLAUDE.md` and `docs/`.
- *Resolution.* Open the PR only after those commits are on the remote base, or rebase. Otherwise the PR diff
  carries AI-layer process changes. This is a process note, not a plan defect.

## Open questions (my view; the owner's defaults are binding)

1. **Evidence on the branch.** Fine. `docs/rca/**` is the artifact class (`branching.md:13`). Mind L1-m4 ordering.
2. **The serial `uedgeC` quirk.** Leaving it for a follow-up is correct. Carry L1-m2 into that ticket.
3. **Wheel/auditwheel.** Deferring is safe for this fix.
   - cibuildwheel does not forward the job's host `CC`/`LDFLAGS` into the manylinux container. On Linux,
     `CC: ${{ env.LLVMCLANG }}/bin/clang` is a macOS-only setting anyway.
   - manylinux2014 gcc does not default to `--as-needed`, so today `uedgeC` already NEEDs `libgomp.so.1` and
     auditwheel already grafts it.
   - After the fix, `apipy`, `bbbpy` and `ppppy` NEED the same soname. auditwheel grafts one copy per soname and
     rewrites every extension to point at it, so there is still one runtime.
   - The plan's phrase "will now link libgomp and auditwheel will vendor it" overstates the change: the wheel already
     vendors it today. Not run: see below.
4. **L5 reduced flow set.** Accepted as the owner's default. The unmodified `pr` set belongs to AIUE-57.

## Not independently verified (environment)

- Any Linux behaviour: L1–L6, `LD_BIND_NOW` semantics (L1-M1 is reasoned from symbol tables and glibc's
  `dl_open`/`dl_lazy` logic), Debian 12's `--as-needed` mechanism, `ldd -r` output. These need the Docker runs.
- The cibuildwheel/manylinux behaviour (open question 3) is reasoned, not run.
- `CC=clang` on Linux. My reasoning: clang `-fopenmp` links libomp into both `uedgeC` and the Fortran extensions, and
  libomp provides the `GOMP_*` and Fortran `omp_*_` entry points (as on macOS). That gives one runtime, and it is no
  worse than today. Untested, and the plan correctly does not claim it.
- The Jira AIUE-64 acceptance text. I checked the plan's own acceptance list only.

## What was checked and how

- Plan read in full at `75108da`. `git diff 0fac655 4faed39 -- . ':!.claude' ':!CLAUDE.md' ':!docs'` is empty, and
  `0fac655` is an ancestor of `origin/v9-develop`, so the `base-*` venvs are valid baselines.
- `setup.py`:
  - `platform` comes from `sys.platform` (`:14`) and is not shadowed.
  - `--serial` removes the flags at `:731-740`.
  - The make call is at `:770` and is followed by `build.run` (`:772`).
  - The `uedgeC` `Extension` builds its `extra_link_args` at module level (`:799`), so serial keeps `-fopenmp`
    (confirmed with `otool -L` on `base-serial`).
  - Every `refs.lock.json` `setup.py` entry is ≤ 697.
- `Makefile.Forthon`: it never uses `LDFLAGS`. It passes `$(OMPFLAGS)` through `INSTALLARGS`, and `uedgeC` is not
  built by make.
- Forthon 0.10.10:
  - `Forthon_builder.py:297-302` (`cargs` reach compile only), `:463-470` (`-z lazy`, Linux) and `:493-507`
    (`setuptools.Extension`, no OpenMP link flag, `setuptools.setup` called in-process by `Forthon3`).
  - `compilers.py:369-370,644-645` (`--omp` only extends `fopt`) and `:641` (`-flat_namespace`).
  - `Forthon_options.py`: there is no link-argument option.
  - The generated `Makefile.bbb` does not use `LDFLAGS`.
- setuptools 84.0.0 `_distutils/compilers/C/unix.py:51-54,233` (`LDFLAGS` appended to `LDSHARED`; a `CC` override
  replaces the `LDSHARED` prefix) and `:382` (`-l` libraries after the objects).
- macOS `venvs/base-omp` and `base-serial`:
  - `otool -L` per extension: libomp appears only in `uedgeC`, in both builds.
  - `nm -u` OpenMP counts: omp 4/4/13; serial `ppppy` 3, see L1-m1.
  - `nm -gU libomp.dylib | grep -c GOMP_` gives 134, and `T _GOMP_parallel` is present.
  - Cross-extension forward references: the script in the session's `/tmp`, see L1-M1.
- AIUE-62 evidence:
  - `build_info.txt`: Debian base/fix import failure, and the base `bbbpy` link line without `-fopenmp`.
  - `ubuntu/import_default_ldflags.txt`: Ubuntu exit 127 and `as-needed` 3.
  - `ubuntu/fma_fixld.txt`: with `LDFLAGS=-fopenmp`, `apipy`/`bbbpy`/`ppppy` NEED `libgomp.so.1` and `uedgeC` NEEDs
    only `libreadline.so.8 libc.so.6`.
- AIUE-53 `serial_check.py` (`15ae327`): its CLI flags and `RESULT` string match M3, and its gate/stale rules are the
  basis for L1-m4.
- AIUE-57 (`8ee189d`): `run_omp_ci.sh` environment variables, the `OMP_CI_FLOWS` format and the smoke step
  (`:86-94`), and `build-test-omp.yml` (no `LDFLAGS`, `pip install -v .`).
- `.github/workflows/build-test-wheel.yml`: the wheel job's environment.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` gives OK. The AI-layer claims in the plan
  (`CLAUDE.md:29`, `openmp-jacobian.md:23`, `testing.md:48`) stay true after the change.
