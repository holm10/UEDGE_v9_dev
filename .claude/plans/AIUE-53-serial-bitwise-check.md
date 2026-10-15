# Feature: AIUE-53 — Serial old-vs-new bitwise check

## Summary
**Type**: Python (test tooling; no Fortran, `.v` or `src/uedge` change)
**Complexity**: Medium
**Default results**: Unchanged (no product code touched)
**Packages / files**: `tests/deterministic_omp/harness/{serial_check.py,pytests_worker.py,build_probe.py,test_serial_check.py}`,
`tests/deterministic_omp/README.md`, `.claude/context/{openmp-jacobian.md,testing.md}`
**Branch / worktree**: `feature/v9-AIUE-53-serial-bitwise-check` @ `../uedge-wt/AIUE-53`
(stacked on `feature/v9-AIUE-49-omp-harness-core`)

## Problem and solution
Epic AIUE-8 requires every fix to leave serial results bitwise unchanged, in the `--serial` build and in the OpenMP
build with `OMPParallelJac=OMPParallelPandf1=0`. The pytests suite (`rtol=1e-5`) cannot show that. Add one command
that runs a case set serially, each case in a fresh process, with a base and a new build, and compares the records with
the AIUE-49 comparator (`compare.compare_records`).

## Decisions
- **Takes venvs, does not build them.** Build both with `pip install` (or `build_uedge.sh`) and pass the interpreters.
  Building inside the tool would double its run time and hide build failures in a long log.
- **Two pairs:** `--base-python/--new-python` (the `--serial` builds) and `--base-omp-python/--new-omp-python` (the
  OpenMP builds, run on the `serial` arm: both switches 0, `Nthreads=1`, `OMP_NUM_THREADS=1`). Both builds have the
  `ppp` package, so the same worker serves both. The OpenMP pair is optional on the command line, but the summary
  says when it was skipped, and the PR gate requires both.
- **Build guard:** a probe process per interpreter records `sys.executable`, `sys.prefix`, `uedge.__file__`,
  `uedge_ver`, the SHA-256 of every compiled extension in the package and one combined hash, and whether `bbbpy` is
  an OpenMP build (contains `GOMP_`/`__kmpc_` symbols). Exit 2 if base and new have the same combined hash (unless
  `--allow-same-build`, used for the base-vs-base acceptance), or if a serial pair contains an OpenMP build or the
  OpenMP pair a serial build.
- **Case set:** reproducer presets on the serial arm (`full, tebox, te, ti, ni, up, ng, full_note`, from
  `config.PRESETS`; AIUE-52's driver is not merged yet) and pytests coverage cases. `quick`: `repro-tebox` and the
  pytests cases. `all`: every preset and every pytests case. No double-null case exists in the pytests suite or in
  `builder/test/Forthon_cases` (all `snull` or slab): documented gap; the AIUE-9 families are added when they exist.
- **pytests worker** (`pytests_worker.py`) mirrors `test_reference` exactly: exec `input.py`, `issfon=1`,
  `ftol=1e20`, `exmain()`, then set the equation switches from `solution.h5:pytests/default`, restore
  `nis..phis` from `solution.h5:bbb`, `exmain()` again, and record. `perturb_solution` is not called: the test does not
  call it either (only `write_data` does, when the reference is made), so the stored file is used as it is. `com.iprint`
  stays 1 (the test sets 0) so the `fnrm` lines are printed; it changes no numbers. Serial arm set before the first
  `exmain`. D_mols decks need `rates/aph/crumpet_{n,E}rates.dat` copied into the run directory.
- **What is compared:** the full `compare_records` report: the post-`exmain` Jacobian (with `ftol=1e20` this is the
  `sfsetnk` Jacobian, i.e. the AIUE-47 capture point times `1/suscal`, bitwise per AIUE-47), any raw captured
  Jacobians both records hold, `sfscal`, `suscal`, `yldot`, the `ffun` probe, final `fnrm` (`float.hex`) and the printed
  `fnrm` sequence. If only one build has the AIUE-47 hook (captured Jacobian counts differ), the captured ones are not
  compared and the report says so; the post-`exmain` Jacobian is still compared. The pytests worker records no raw
  captures (it does not touch `worker.capture_description`, which another session is changing).
- **Exit codes:** 0 all agree, 1 at least one mismatch, 2 harness error (bad build pair, missing case, failed run).
  A harness error wins over a mismatch, because the result is incomplete.
- **Disk:** a full-problem record is ~50 MB. `record.npz` of agreeing cases is deleted unless `--keep-records`.

## Tasks
1. CREATE `harness/build_probe.py`. VALIDATE: run on base-serial and base-omp, OpenMP flag differs.
2. CREATE `harness/pytests_worker.py`. VALIDATE: run D_only, D+C, D_mols, fulltest 16x8 with base-serial.
3. CREATE `harness/serial_check.py` (CLI, parallel jobs, JSON + summary). VALIDATE: unit tests, base vs base.
4. CREATE `harness/test_serial_check.py` (no build needed): case table, build guard, capture-count equalising.
5. Negative control: detached scratch trees `../uedge-wt/AIUE-53-neg{,-omp}` with
   `feexy = 1.0000001*exp(...)` in `bbb/pandf_plasma_energy.m:444`, built into `venvs/AIUE-53-neg{,-omp}`; never
   committed. VALIDATE: exit 1, summary names case and first entry.
6. UPDATE `README.md`; `.claude/context/{openmp-jacobian,testing}.md` (separate commit, `AI-layer: code-facts`);
   `docs/reviews/AIUE-53-validation.txt`.

## Acceptance criteria (ticket)
- [ ] v9-develop against itself passes in both builds — task 3
- [ ] Negative control fails and names case and first entry — task 5
- [ ] Documented as required for every PR touching Fortran, `.v` or `ppp/` — task 6
- [ ] Documented in `openmp-jacobian.md` and `testing.md` (`AI-layer: code-facts`) — task 6

## Revision after review round 1 (`docs/reviews/AIUE-53-implementation-round1.md`)
- Rebased onto the harness-core tip with the AIUE-47 capture integration and the stricter `compare_records`
  (`check_arm`, record checks, `cli.exit_code`); `full_note` became `te_phi`.
- I1-B1: Newton-iteration cases (`-itN`) in `quick` and `all`; raw captures of every `sfsetnk`/`psetnk` Jacobian in both
  workers when both builds have the hook (else capture 0 on both sides, as `compare_records` requires).
- I1-M1: the gate is complete only with both pairs, two different builds and every case of `all`; otherwise
  `RESULT: INCOMPLETE`, exit 2, unless `--partial-ok`. `--cases all` is the default.
- I1-M2: the probe records `direct_url.json`; the source tree's HEAD/dirty/ancestry are read; same tree or same clean
  commit is a harness error; each record's build identity must equal the probed one.
- Minors: serial-path checks via `compare.check_arm`; unexpected exceptions exit 2; informative ERROR lines; 20 pytests
  unit variants; double-null wording; independent-build acceptance (base vs AIUE-47 builds) and a ulp-level
  (reassociation) negative control in `../uedge-wt/AIUE-53-ulp`.
