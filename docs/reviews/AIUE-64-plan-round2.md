# AIUE-64 plan review, round 2

Stage: plan. Ticket AIUE-64 (epic AIUE-8). Revised plan `.claude/plans/AIUE-64-omp-linux-link.md` at `8122cfb` on
`bugfix/v9-AIUE-64-omp-linux-link` (round 1 reviewed `75108da`). Response:
`docs/reviews/AIUE-64-plan-round1-response.md`. Reviewer: uedge-reviewer (read-only, plus `nm` on existing builds;
no Docker, no rebuilds).

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 2 MINOR (both new and optional).

## Summary

All nine round-1 findings are resolved. I re-checked each one against the code, the existing `base-*` builds and
the AIUE-53 tool, not against the response. The `LD_BIND_NOW=1` import is gone. In its place is a filtered `ldd -r`
check, which tells base from fix because `ldd -r` forces every relocation regardless of `-z lazy`. The anchored
symbol counts match the `base-omp` and `base-serial` builds exactly. The build → M3 → commit ordering now satisfies
`serial_check.py`'s dirty, stale and base-ref gate rules on both the base and the new side. The `LDFLAGS` snippet
appends to the user's string and leaves macOS and `--serial` on the old `env=None` call. Two small new points: one
on line numbers in the task-5 code-facts text, one on naming the follow-up ticket. Neither blocks execution.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**L2-m1. Task 5 dictates `setup.py` line numbers from before the edit.**
- *Location.* Plan §Step 5, code-facts commit: "`build.run` then builds the C extension `uedgeC`
  (`setup.py:772,781-803`)". The same numbers appear in §Context references.
- *What is wrong.* Task 1 replaces the 3-line make call at `setup.py:769-771` with a block of about 19 lines, so after
  the edit `build.run(self)` and the `uedgeC` `Extension` sit about 16 lines lower. `check_context_refs.py` reports a
  new citation as NEW and `--update` then locks whatever text is on the cited line. It does not check that the line
  is the one meant. If the plan's numbers are copied as written, `--update` locks wrong references without
  complaint, and `architecture.md` cites the wrong lines from then on.
- *Resolution.* In task 5, take the `uedgeC` step's numbers from the edited `setup.py` (`grep -n`), as is already
  planned for `setup.py:<new line>`, and check every new citation by eye before `--update`. A one-line note in
  task 5 is enough.

**L2-m2. Name the follow-up ticket.**
- *Location.* §Problem "Side finding" and §Open questions 2 ("a separate follow-up ticket, filed by the main
  session").
- *What is wrong.* The ticket has been filed as AIUE-67. With the key in the plan, the L1-m2 hand-off can be traced
  from the branch without Jira.
- *Resolution.* Say "AIUE-67" in both places. Optional.

## Status of previous findings

| Finding | Status | Evidence (checked myself) |
|---|---|---|
| L1-M1 `LD_BIND_NOW=1` check cannot pass | **Resolved** | `LD_BIND_NOW` is gone from L1, L6 and the acceptance list; it now appears only in the explanation of why it is not used. The replacement, `ldd -r <ext>.so 2>&1 \| grep -E 'undefined symbol: (GOMP_\|omp_)'`, tells base from fix. glibc's `ldd -r` runs the loader in trace mode with all function relocations forced (the ldd script sets bind-now), so `-Wl,-z,lazy` (`Forthon_builder.py:469-470`, confirmed) does not hide an unresolved PLT symbol. On `base`, `apipy`/`bbbpy`/`ppppy` have no `libgomp` in their NEEDED closure (AIUE-62 link line), so `GOMP_parallel` etc. are reported. On `fix` they NEED `libgomp.so.1` (AIUE-62 `fma_fixld.txt` for the same `LDFLAGS=-fopenmp` link), which exports both the `GOMP_*` and the C/Fortran `omp_*` entry points, so the filter comes back empty. The pattern is anchored after "undefined symbol: ", so it cannot match `jac_calc_omp_`. The `2>&1` catches the loader's warnings. The expected base set (exactly those 3 of 11) matches the macOS anchored counts below, because the Fortran objects are the same. `uedgeC` has 0 OpenMP references even though it carries `extra_objects`. |
| L1-m1 Serial expectations; unanchored regex | **Resolved** | `nm -u ... \| grep -E '^_(GOMP_\|omp_)'` on `venvs/base-omp` gives apipy 4, bbbpy 4, ppppy 13, others 0. On `venvs/base-serial` it gives ppppy 2 (`_omp_get_thread_num_`, `_omp_get_wtime_`), others 0. Both match the plan's M1(c) values exactly. The serial calls come from `ppp/parallel.F90:213,286,340`, where `USE omp_lib` (`:182`) is not guarded by `_OPENMP`. The L2 and L4 Linux patterns are anchored the same way (`nm -D --undefined-only \| awk '{print $NF}' \| grep -E '^(GOMP_\|omp_)'`; versioned names such as `GOMP_parallel@GOMP_4.0` still match). |
| L1-m2 Serial `uedgeC` quirk is load-bearing | **Resolved** | The side finding records that the serial `ppppy` depends on the serial `uedgeC`'s libomp on macOS and is already unresolved on Linux `--as-needed` builds. L4 now expects those two symbols on both `base-ser` and `fix-ser`, so they are recorded, not fixed. See L2-m2 for the ticket key. |
| L1-m3 Factual slips | **Resolved** | "Linked, not compiled" now appears in Root cause item 2, Alternatives and Notes/Risk. `setup.py:799` (`extra_link_args=FLAGS['CARGS']+...`) and `:801` (`extra_compile_args=fcompiler.extra_compile_args`) are confirmed. The dumpspecs figure is now cited from `ubuntu/import_default_ldflags.txt`, whose line 5 reads "as-needed occurrences: 3". The Debian mechanism is now "observed", with a record-only `gcc -dumpspecs` check in L6. The Debian NEEDED citation is the "fixld" row of AIUE-62 `build_info.txt` (Debian 12.2.0, `LDFLAGS=-fopenmp`, lines 4-12). |
| L1-m4 M3 provenance ordering | **Resolved** | I read `serial_check.py` at `15ae327`. `source_info` reads `git status --porcelain --untracked-files=no` (`:226`), so untracked review files do not make a tree dirty. The plan's stricter `--porcelain`-empty rule is harmless. `is_stale` compares the HEAD commit time with the extension mtime (`:233-237`). The base side has to be on or below `origin/v9-develop`. I checked both base venvs: their `direct_url` points to `uedge-wt/base-omp` and `uedge-wt/base-serial`, both at `0fac655`, clean, ancestors of `origin/v9-develop` (`3865c79`), commit time 1792010326 < `bbbpy` mtime 1792048311, so the base side passes all three gates. On the new side, task 2 commits, task 3 builds from a clean tree, M3 runs, and only then come the task-5 commits. The order is right, and the rebuild-before-re-run rule is stated. Task 0 saves the "before" records to `$SCR/mac_before/` before task 3 overwrites the venvs. Task 6 `validate` runs after the last commit. |
| L1-m5 Drift check; `architecture.md` step 3 | **Resolved** (see new L2-m1) | Task 5 expects NEW for the new citations, runs `--update` only once NEW is the only status reported, and commits `refs.lock.json` with `architecture.md`. Step 3's "and the `uedgeC` module" is to be corrected, and a `build.run`/`uedgeC` step is to be added. That is right: `architecture.md:49` currently has the false claim, and `uedgeC` is linked by `build.run` at `setup.py:772`. Every locked `setup.py` reference is at or above line 697, and the edit is at 769, so no locked reference moves. The drift check on the branch today gives `OK` (exit 0). |
| L1-m6 `LDFLAGS` round trip; `--noclean` | **Resolved** | The snippet appends `' -fopenmp'` to the original string and skips it when `-fopenmp` is already a token. `.strip()` only changes leading or trailing whitespace, which is harmless. `makeenv` is built at call time, so it carries `OMP=TRUE` (`setup.py:740`, written to `os.environ`) and `NOCLEAN` (`:698-701`, class-level `environ`, the same object). `env=None` keeps macOS and `--serial` on the old call. `Makefile.Forthon` has no `LDFLAGS` (grep empty), so make passes the inherited variable through to `Forthon3`, which calls `setuptools.setup` in-process (`Forthon_builder.py:495-508`, confirmed), and setuptools appends it to `LDSHARED`. The `--noclean` note is present. |
| L1-m7 L5 probe proves only L2 | **Resolved** | The probe now records the `/proc/self/task` count before and after one Te-box Jacobian evaluation, with `OPENBLAS_NUM_THREADS=1`. The expectation `n1 - n0 >= 1` is sound. `InitOMPJac` (`ppp/omp_parallel.F90:296-310`) opens a `!$omp parallel` team of `OMP_GET_MAX_THREADS()` threads, and libgomp keeps its pool threads alive after the region. The probe is a separate script, and AIUE-57's `run_omp_ci.sh` sets `OMP_NUM_THREADS=1` only inside the smoke subshell (`:89`), so the probe does not inherit it. |
| L1-m8 PR precondition | **Resolved** | Stated in Notes. `git rev-list --count origin/v9-develop..4faed39` gives 7, and those commits touch no product files (the product-path diff is empty). |

## Not independently verified (environment)

- Every Linux expectation (L1-L6): the `ldd -r` output on base vs fix, NEEDED lists, link lines, the L5 replay and
  the thread probe. I reasoned these from the macOS symbol tables, glibc `ldd -r` semantics and the AIUE-62 records.
  They need the Docker runs the plan describes.
- The Linux serial `ppppy` symbol set in L4 (`omp_get_thread_num_`, `omp_get_wtime_`) is inferred from the macOS
  serial build. gcc 13.3 should produce the same calls from `parallel.F90`, but I did not run it. If it differs, the
  plan's stop rule applies. That is correct behaviour, not a plan defect.
- The Jira AIUE-64 acceptance text. The response says it does not mention `LD_BIND_NOW`, and I have no Jira access
  or snapshot to check that.
- Whether AIUE-67 exists with the L1-m2 content (reported by the main session).

## What was checked and how

- `git diff 75108da..8122cfb --stat`: only the plan and the two review files changed. No product files are on the
  branch, and `git status --porcelain` in the worktree is empty.
- Plan read in full at `8122cfb`. Response read and mapped finding by finding to plan sections.
- `nm -u <ext> | grep -E '^_(GOMP_|omp_)'` over all 11 extensions of `venvs/base-omp` and `venvs/base-serial`
  (results in the table above).
- `setup.py`: `grep -n` for lines 46, 698-701, 732-740, 769-772, 784, 799 and 801. The class-level `from os import
  environ` and the `call`/`platform` imports at `:13-14`.
- `Makefile.Forthon`: no `LDFLAGS`.
- Forthon 0.10.10 in `venvs/base-omp`: `Forthon_builder.py:297-302` (`cargs` reach compile only; the OpenMP flag is
  commented out), `:466-470` (`-z lazy` on Linux) and `:495-508` (in-process `setuptools.setup`, no OpenMP link
  argument).
- `ppp/parallel.F90:182,213,286,340` and `ppp/omp_parallel.F90:281-333` (the `InitOMPJac` team size, for the probe).
- AIUE-53 `serial_check.py` (`15ae327`) `:205-290` (dirty, stale and base-ref gates). The base venvs'
  `direct_url.json`, plus the HEAD, cleanliness, ancestry and commit time of their source trees, compared with the
  extension mtimes.
- AIUE-62 `docs/rca/AIUE-8-data/linux/build_info.txt` (Debian image, fixld row) and
  `ubuntu/import_default_ldflags.txt:5`.
- AIUE-57 `run_omp_ci.sh` for `OMP_NUM_THREADS`.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` gives OK. `.claude/context/refs.lock.json`
  `setup.py` entries are all ≤ 697. `architecture.md:45-50` read.
