# AIUE-53 Serial old-vs-new bitwise check: implementation review, round 1

Reviewer: uedge-reviewer (independent referee)
Branch: `feature/v9-AIUE-53-serial-bitwise-check` @ 99b2479 (diff `fbe0adf..HEAD`)
Reference: ticket AIUE-53 acceptance criteria, `.claude/plans/AIUE-53-serial-bitwise-check.md`

## Verdict

**REVISE**: 1 BLOCKER, 2 MAJOR, 7 MINOR.

## Summary

The tool works and is well built. The comparison is bitwise, harness errors turn into exit 2, a case that fails in both builds gives ERROR (not AGREE), the pairs and roles are kept apart, and the omp0 pair really runs with `OMPParallelJac=OMPParallelPandf1=0`, `ParallelJac=ParallelPandf1=0`, `Nthreads=1` and `OMP_NUM_THREADS=1` (checked in the provenance of every record). The pytests worker repeats `test_reference` faithfully. I reproduced the negative control: exit 1, with the case and first entry named. The serious gap is that every case runs at `ftol=1e20`. `nksol` returns at its initial stop test (`svr/nksol.m:1014`, `nkstp0`) before `pset` is ever called, so the "fnrm sequence" has one element and the whole Newton/preconditioner/Krylov path is never run. A Fortran change on that path gets exit 0 even though converged results change. That breaks the "nothing may change" proof the epic depends on. The fix is cheap: I showed that an iterating `tebox` case (itermx=5) agrees bitwise across two builds of the same code and fails on the negative control. Two smaller weaknesses would let a misused run look like a pass: the RESULT line says AGREE when a pair was skipped or a build was compared with itself, and nothing records which source each build came from.

## Findings

### BLOCKER

**I1-B1: The solver path is never run, and the "fnrm sequence" is always one element long.**
- Location: `serial_check.py:205` (`RunSpec(..., itermx=None)`, so `ftol=1e20` in `worker.py:81-82`), `pytests_worker.py:67`; the docs in README, `testing.md` and `openmp-jacobian.md` ("exit 0 = identical").
- What is wrong: `nksol` runs `nkstp0` on the initial residual (`svr/nksol.m:1014`, `iterm=1` when `fmax <= p01*ftol`) and returns before `pset`/`psetnk`, the ILU preconditioner, the Krylov solve or the line search (`svr/nksol.m:1501`). The only things exercised are `rhsnk`, the `sfsetnk` Jacobian and `rnrms`. The ticket asks for a comparison of the "fnrm sequence". Here it is `[(0, ...)]` in every record: I checked all 20 records of my quick run, and each has `iterations` of length 1 and `ijactot = 1`. As a result, any change to `psetnk` (row normalisation, `nufak`/dt diagonal, RCM reordering), `svr/` (nksol, ILUT, GMRES), `bbb/odesolve.m` after `sfsetnk`, or `ppp/` preconditioner code reached in serial passes with exit 0, even though converged results change. By the epic's rule ("a tool that can pass when results differ"), that is a blocker.
- Evidence: a script (`scratchpad/rev53/iter.py`) runs `RunSpec(preset="tebox", arm="serial", itermx=5)` through the existing `runner.run_spec`:
  - base-serial and AIUE-47-serial (same physics, different build) give the same 4-iterate sequence `0.3221264477609989, 0.1295818223118249E-01, 0.3022148351236412E-04, 0.3833757148333837E-09` and full AGREE;
  - base-serial against AIUE-53-neg gives MISMATCH in every section, including the whole sequence.
  So iterating cases are deterministic in serial, discriminating, and cost a few seconds.
- What would resolve it: add iterating cases to `quick` and `all` in both pairs. Examples: `repro-tebox` and `repro-te` with `itermx` of about 5, and at least one pytests case run a few Newton iterations at the deck's `ftol` from the perturbed `solution.h5`. Compare the full fnrm sequence plus the final `yldot`/`fnrm_final` (and ideally the final `yl`). Then either the docs say what is and is not covered, or they claim the solver path only once these cases exist.

### MAJOR

**I1-M1: The RESULT line and exit code 0 don't show that the gate was incomplete.**
- Location: `serial_check.py:272-278, 300-302, 352-390`; README ("paste its `RESULT` line"), `testing.md` ("Paste the `RESULT` line into the PR").
- What is wrong: if only `--base-python/--new-python` are given, the tool exits 0 and prints `RESULT: AGREE (bitwise identical)`. A WARNING line further up is the only sign the omp0 pair was skipped. The same happens with `--allow-same-build`: a build compared with itself prints the same RESULT line. The documented PR evidence is the RESULT line, so a partial or self-comparison run is indistinguishable from the real gate, both to whoever reads the PR and to any script that checks the exit code.
- Evidence: my run `rev53/onepair` (serial pair only, `pytests-D_only`) printed `WARNING: pair omp0 not checked; the PR gate needs both pairs` and then `RESULT: AGREE (bitwise identical)`, with exit 0.
- What would resolve it: any one of the following.
  - Make both pairs required, with an explicit `--partial` override that cannot exit 0 silently.
  - Put the checked pairs, the case set and the same-build flag into the RESULT line (for example `RESULT: AGREE serial+omp0, cases all`), and say in the docs that only a RESULT naming both pairs, a non-self comparison and `all` meets the gate.

**I1-M2: The build guard cannot tell which source each build came from.**
- Location: `build_probe.py` (hashes the extensions; `_build_info.json` is never written by any build), `serial_check.py:145-157`.
- What is wrong: builds on this machine are not byte-reproducible. Every one of the 11 extensions differs between `base-serial` and `AIUE-53-neg`, including `aphpy`, `compy`, `svrpy` and others whose source is identical (per-file SHA-256 listed below). So the hash guard catches only "the same installed files twice". It cannot catch "base is not v9-develop", "base and new were built from the same tree" (for example the PR branch built into two venvs, which compares the change with itself and gives AGREE), or "base-serial and base-omp come from different commits". The summary records interpreter paths and hashes but no source commit, so the PR evidence cannot show what was compared. The validation record had to state the commits by hand.
- Evidence: `shasum` of `*.so` in the six venvs. Every venv has `uedge-8.1.2b0.dist-info/direct_url.json` naming its source tree, for example `file:///Users/holma/Documents/uedge/src/uedge-wt/base-serial`.
- What would resolve it: have the probe record the source directory from `direct_url.json` together with `git rev-parse HEAD` and `git status --porcelain` of that tree. Print them in the summary and JSON. Make it a harness error (overridable) when base and new have the same clean source commit. Show whether the base commit is `origin/v9-develop` or one of its ancestors. Note in the docs that the tree is read at check time, not build time.

### MINOR

**I1-m1: The scaled Jacobian is not equivalent to the raw capture point.** The docs say the post-exmain Jacobian is "the AIUE-47 capture point scaled by `1/suscal`". That equality holds, but the map is not one-to-one. `amudia` computes `b(k) = a(k)*diag(ja(k))` (`svr/svrut4.m:1152`) with `diag = 1/suscal`, and `suscal` is a per-variable value under `iscolnorm=3` (`bbb/bbb.v:1284`), not a power of two. In my numpy test (`rev53/mask.py`, one million random entries), 9.6 % of isolated 1-ulp raw differences vanish after scaling. `sfscal` is computed from the scaled matrix, so it cannot recover them. Once I1-B1 is fixed, iterating cases make this a small residual risk. Still, say so in the docs, and record the raw captures once AIUE-47 is merged. Today `worker.capture_description` always returns `{"hook": False}`, so the "raw captures when both builds have the hook" path, including the mixed-hook note, is dead code. Only unit tests exercise it, and no run does. The README should state that.

**I1-m2: Runtime provenance is recorded but not checked.** Records hold `OMPParallelJac`, `OMPParallelPandf1`, `ParallelJac`, `ParallelPandf1`, `Nthreads` and `OMP_NUM_THREADS`. They are all correct today, but nothing asserts them. If a later change ignored or reset the ppp switches, the "serial path" claim would go unchecked. Assert them per record and make a violation a harness error.

**I1-m3: Unexpected exceptions exit with 1, not 2.** `serial_check.py:321` and `:423` catch only `HarnessError`, `OSError`, `ValueError`, `KeyError` and `SubprocessError`. Anything else, for example `zipfile.BadZipFile` from a truncated `record.npz`, propagates and the interpreter exits 1, which reads as MISMATCH. I demonstrated this with `rev53/exc.py`. The error fails closed, but it violates "exit codes as AIUE-49". Catch `Exception` in both places.

**I1-m4: The pytests coverage is thin compared with what is available.** Only the `default` variant of each family is used. The suite has about 180 unit cases that toggle boundary-condition and transport switches (`istewc*`, `isnwcon*`, `isupw*`, `istg*`, `recycm*`, drifts, and so on), and each takes about 1 s. A change confined to one of those branches of `pandf_boundary.m` or the energy and momentum files would pass. The ticket's minimum of three cases is met. Consider an optional `pytests-unit` group, and have the docs state that exit 0 means "identical on these cases".

**I1-m5: The double-null wording is imprecise.** `builder/test/rensink/dnull/` holds BASIS double-null mesh-generation decks (`makemesh_dRsep_{p1,m1}`, `rdmesh.dnull.{top,bot}`), so "no double-null case in `builder/test`" is true only of runnable plasma cases. Note also that a bitwise RHS and Jacobian comparison needs no converged solution, only a grid and a state. Reword the claim to "no runnable double-null case" and leave the gap to AIUE-9.

**I1-m6: The ERROR summary line carries no information.** For a failed run it prints only the first line of the error, `run in <dir> failed:`. The actual cause (for example `Jacobian row = 0 for eqn iv = 1092`) is only in the JSON or run log. Print the last line of the traceback.

**I1-m7: The acceptance runs could be stronger.**
- The base-vs-base acceptance used the same venv twice (`--allow-same-build`). Add one run with two independent builds of the same source. I did this partly with AIUE-47-{serial,omp}, hook off, on `quick`: both pairs AGREE.
- The negative control is a 1e-7 relative change. Bit-level sensitivity rests only on the comparator unit tests (the ±0 case). A ulp-level control, such as a reassociated sum in one `pandf` term, would show the tool catches reduction-order changes, which is what the epic's fixes produce.

## Judgement of the author's stated deviations

- **The tool takes venvs instead of building them.** Accepted: the ticket says "builds or takes". The provenance gap this opens is I1-M2.
- **The pytests worker skips `perturb_solution`.** Accepted, and verified: `test_reference` never calls it, only `write_data` does (upstream `test_nonog_default.py`). The worker's sequence (exec `input.py`; `issfon=1`; `ftol=1e20`; `exmain`; `seteqs(defref)`; `restore` from `bbb`; `exmain`) matches `matches()`. Leaving `iprint=1` changes no number: the author's D_mols fnrm equals the upstream test's to every digit. The `testing.md` correction is right.
- **Post-exmain Jacobian instead of raw AIUE-47 captures.** Acceptable as an interim step, but not equivalent (I1-m1). The mixed-hook logic is correct, but no run reaches it today.
- **No double-null case.** Accepted, with the wording fix in I1-m5.
- **`full_note` and `pytests-orthogonal` excluded.** Accepted, and consistent with AIUE-52 (`flow.PHI_PRESET = "full_note"`). I confirmed `repro-full_note` errors in both builds and that the tool reports this as exit 2, not AGREE. Phi stays covered: `te/phi` Jacobian entries appear in the mismatches of `repro-full`, `pytests-D_only` and `pytests-D_mols`. I did not rerun the orthogonal case.

## Status of previous findings

Round 1: none.

## What was checked and how

- I read the full diff `fbe0adf..HEAD`, and the library pieces this tool depends on (`compare.py`, `runner.py`, `worker.py`, `config.py`).
- Unit tests: `venvs/base-serial/bin/python -m pytest -q tests/deterministic_omp/harness` gave 30 passed.
- `serial_check.py --cases quick --jobs 4 --keep-records`, base-{serial,omp} against AIUE-47-{serial,omp}: exit 0, 10/10 AGREE. In every record: `OMPParallelJac=OMPParallelPandf1=ParallelJac=ParallelPandf1=0`, `Nthreads=1`, `OMP_NUM_THREADS=1`, iterations length 1, `ijactot=1`, capture count 0.
- Negative control `--cases quick`, base against AIUE-53-neg{,-omp}: exit 1, 10/10 MISMATCH, each naming the case and first entry (for example `repro-tebox ... row te(ix=3,iy=18) col te(ix=3,iy=18) (iv 1,1)`). The scratch trees differ from 3865c79 only at `bbb/pandf_plasma_energy.m:444` (`1.0000001*exp(`), checked with `git diff`. The extension hashes differ from base.
- `--cases repro-full_note,pytests-D_only`, serial pair only: `full_note` gave ERROR, `D_only` AGREE, RESULT HARNESS ERROR, exit 2. A case that errors in both builds is not counted as agree.
- Serial pair only, `pytests-D_only`: exit 0, RESULT AGREE, warning only (I1-M1).
- Unexpected exception via fakes (`rev53/exc.py`): `BadZipFile` is not caught, so the exit is 1 (I1-m3).
- Iterating case via `runner.run_spec(RunSpec(itermx=5))`, three builds: it agrees across two builds of the same code and fails on the negative control (I1-B1).
- Solver flow: `svr/nksol.m:1014` (`nkstp0` before the iteration loop) and `:1501` (`pset`); `bbb/odesolve.m:288-300` (`sfsetnk`); `bbb/oderhs.m:2292-2350` (`sfsetnk`, `amudia` column scaling); `svr/svrut4.m:1152`.
- Masking estimate: `rev53/mask.py` found 9.6 % of 1-ulp raw differences hidden by `*(1/su)`.
- Build reproducibility: per-extension SHA-256 across six venvs. All differ, even for unchanged sources. Each venv has a `direct_url.json` naming its source tree.
- Upstream pytests b535508: `test_reference`, `conftest.py` (only a `chdir`), and the input decks (no `exmain` or `iprint` in the decks, so exactly two nksol blocks).
- Double-null search: `grep geometry=` in the pytests checkout (161 × `snull`) and in `builder/test` (dnull and dnbot mesh decks only).
- AIUE-47 hook source (`bbb/bbb.v` `Jacobian_capture`, `bbb/oderhs.m` `jac_capture`) and AIUE-52 `flow.PHI_PRESET`.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` from the worktree: `OK`, exit 0. It lists informational re-read notes only, caused by the stack's CLAUDE.md, README and harness changes. Commit 99b2479 carries `AI-layer: code-facts`. No skills, agents, hooks or settings change on the branch.
- Doc claims checked:
  - `testing.md` on `perturb_solution`: correct.
  - The README case list, exclusions, crumpet copy, pytests-dir lookup and exit codes match the code.
  - "exit 0 = identical" and "Prove it" overclaim (I1-B1, I1-M1).

Scratch outputs: `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev53/` (`q47`, `qneg`, `fn`, `onepair`, `iter`, `mask.py`, `exc.py`, `iter.py`).
