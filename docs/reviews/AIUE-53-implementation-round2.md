# AIUE-53 Serial old-vs-new bitwise check: implementation review, round 2

Reviewer: uedge-reviewer (independent referee)
Branch: `feature/v9-AIUE-53-serial-bitwise-check` @ 0f5190e, rebased on the harness core 71b0e3b (diff `71b0e3b..HEAD`)
Round 1: `docs/reviews/AIUE-53-implementation-round1.md`. Response: `docs/reviews/AIUE-53-implementation-round1-response.md`

## Verdict

**REVISE**: 0 BLOCKER, 1 MAJOR, 2 MINOR.

## Summary

The round-1 blocker is fixed. Ten `-itN` Newton-iteration cases now run `psetnk`, the preconditioner, Krylov and the
line search. Three of them are in `quick`. I reproduced that they agree across independent builds, that they fail on
the new ulp-level control (one sum reassociated in `pandf_plasma_energy.m`), and that with the hook in both builds
they compare the raw `sfsetnk` and `psetnk` Jacobians (`jacobians 2+post`). The RESULT line and exit code now tell a
partial run or a self-comparison apart from the gate. I reproduced exit 2 for an unflagged self-comparison, INCOMPLETE
for `--allow-same-build`, and `AGREE, PARTIAL` for `--partial-ok`. All seven minors are resolved. One gap remains, and
it is of the same kind as I1-M1. The tool prints `RESULT: AGREE (bitwise identical; complete gate)` and exits 0 even
when its own source guard could not run or found the wrong base: an unknown source on both sides, which means the
same-commit check never ran, or a base that is not on `origin/v9-develop`. Those cases are only WARNINGs. I accept
the rebuttal on not recording the final `yl` separately.

## Findings

### BLOCKER

None.

### MAJOR

**I2-M1: "complete gate" and exit 0 when the source guard could not run, or found a base that is not v9-develop.**
- Location: `serial_check.py:252-261` (`check_pair`: these conditions go to `warnings` only) and `:501-507`
  (`incomplete` covers only skipped pairs, `--allow-same-build` and skipped cases). The docs say the same in README
  "Build and source guard" ("Warnings: ...") and in `testing.md`, `openmp-jacobian.md` ("Exit 0 only for the complete
  gate").
- What is wrong: the docs make `RESULT: AGREE (bitwise identical; complete gate)` the PR evidence, with base =
  `v9-develop` and "two different builds". The tool gives that line in two situations where it knows the gate's
  premise does not hold or cannot be checked:
  - **The source is unknown on both sides.** This happens with a wheel install (`direct_url.json` names a `.whl`
    file, not a directory), a PyPI install (no `direct_url.json`), or a tree that is no longer a git checkout. The
    same-tree and same-commit guards are then skipped. Only the extension hash is left, and round 1 showed that it
    differs for every rebuild of the same source. So two wheel builds of the PR commit compare the change with itself,
    the only thing I1-M2 asked the tool to prevent, and it reports a complete-gate AGREE.
  - **Base HEAD is not `origin/v9-develop` or an ancestor of it**, or the check could not run (`on_base_ref` False or
    None). An example is a base built from an earlier commit of the PR branch. The run then proves only "the last
    commit changed nothing" and still reports a complete gate.

  In both cases a WARNING line is the only sign, exactly the pattern I1-M1 rejected.
- Evidence: a fake-run test, `scratchpad/rev53r2/fakes/test_guards.py`. It uses the real `serial_check.main`, with
  `probe_build`, `source_info` and `run_case` replaced as in `test_serial_check.py`'s `fake` fixture. Every variant
  printed `RESULT: AGREE (bitwise identical; complete gate)  [pairs serial+omp0, cases all (42)]` with exit 0 and
  `gate_complete: true`:
  - both sources unknown (`file:///x/uedge.whl`);
  - base `on_base_ref=False`;
  - base `on_base_ref=None`;
  - same HEAD with new dirty;
  - same HEAD with both dirty.
- What would resolve it: an unknown source on either side, and a base that is not on (or not checkably on)
  `BASE_REF`, each add an item to `result["incomplete"]`. They then give `INCOMPLETE`/exit 2, or `AGREE, PARTIAL` with
  `--partial-ok`. Stacked-branch comparisons keep working through `--partial-ok`. Decide the dirty-tree cases the same
  way, or justify keeping them as warnings: a dirty tree contradicts "build from clean committed trees" and makes the
  provenance unreproducible. Add unit tests for these states and update the README's "Warnings" list.

### MINOR

**I2-m1: The HEAD read at check time can name the wrong commit for a build, and nothing flags it.**
- Location: `serial_check.source_info`.
- Live example from this machine: `venvs/AIUE-47-omp/.../bbbpy*.so` dates from 2026-10-15 01:30. Its source tree
  `uedge-wt/AIUE-47` now has HEAD f7f6e8b, committed at 02:41. My q47 run therefore reports the build as f7f6e8b. It
  also warns `new: the serial and OpenMP builds come from different commits (460aa5fc0834, f7f6e8b6f140)`, although
  both builds contain the same Fortran: the last `bbb/svr/com/ppp` commit in both trees is 3625b48. The README states
  this limit, which meets the I1-M2 acceptance condition.
- Suggestion: a cheap staleness check would catch the common case of "committed after building, forgot to reinstall".
  Warn, or mark the run incomplete, when the source HEAD's commit time, or the mtime of any tracked file changed
  since, is later than the mtime of the installed extension.

**I2-m2: Nothing asserts that an `-itN` case actually iterated.**
- Location: `serial_check.compare_pair` and `run_case`.
- The solver-path coverage behind the I1-B1 fix rests on today's runs: `iters 4`/`6` and `post(psetnk)` in every
  `-it` case. Suppose a deck or preset change, or a different pytests checkout, left the start state below the deck's
  `ftol`. The case would then be evaluation-only again, with no error, and RESULT would still say complete.
- Suggestion: for cases with `itermx`, require `len(iterations) >= 2` and `post_exmain_from == "psetnk"`, and make
  any other result a harness ERROR.

## Status of previous findings

| ID | Status | Evidence |
|---|---|---|
| I1-B1 (solver path never run) | **Resolved** | The `CASES` table now has 3 repro and 5 pytests `-itN` cases. `quick` holds `repro-tebox-it5` and `pytests-{D_only,D+C}-it5`. My runs: (1) base vs AIUE-47 `quick --partial-ok`, both pairs: 16/16 AGREE, `-it` cases `iters 4`/`6`, `post(psetnk)`. (2) base-serial vs AIUE-53-ulp `quick`: 8/8 MISMATCH, exit 1. `pytests-D_only-it5` shows a different whole `fnrm` sequence from iteration 1 (`0.9719416114299252E-01` vs `0.9719416171284716E-01`), 405 `yldot` entries differ and `fnrm_final` differs. (3) AIUE-47 vs itself, both hooks: `jacobians 2+post(psetnk)`, with captures `['sfsetnk','psetnk']` and source `jac_calc`. `pytests_worker.py` sets `ftol` back to the deck value and `itermx` before the final `exmain`, as described. The round-2 validation record (§R2-1, R2-3) shows the full `all` set at `iters 4`/`6` and the negative control failing on the `-it` cases. |
| I1-M1 (RESULT AGREE on partial or self runs) | **Resolved** (for the cases raised in round 1; see I2-M1 for the source-guard states) | Self-comparison without flags: `HARNESS ERROR ... same build ... same source tree`, exit 2. With `--allow-same-build`: `NOT THE GATE` lines and `RESULT: INCOMPLETE ... [pairs serial, cases partial (2)]`, exit 2. `quick --partial-ok`: `RESULT: AGREE, PARTIAL (--partial-ok; not the gate)`, exit 0. The RESULT line names the pairs and the case set. Unit tests `test_main_incomplete_is_not_the_gate` and `test_main_complete_gate_agrees` pass. |
| I1-M2 (no source provenance) | **Resolved** against its acceptance conditions | `direct_url.json` dir, HEAD, dirty state and `on_base_ref` are printed per build and stored in the JSON. Same tree and same clean commit are errors: reproduced, my self run names the same source tree. A base off `v9-develop` is flagged: h47 shows `(not on origin/v9-develop)`, base-serial 0fac655 shows no flag. Every record's `extensions_sha256` is checked against the probe. The docs say the tree is read at check time. The remaining weakness, that these facts don't affect RESULT, is filed as I2-M1. |
| I1-m1 (scaled vs raw Jacobian; capture path dead) | Resolved | The capture path runs (h47: `jacobian:captured[0..1]` sections). The README "Limit" paragraph states the `1/suscal` masking. With the hook in one build only, capture is 0 and a warning is printed (q47 output). |
| I1-m2 (runtime provenance not checked) | Resolved | `compare_records` runs `compare.check_arm` on both records. `pytests_worker.py` records `spec.arm/threads/preset` and the diagnostic switches. `test_compare_pair_checks_serial_path` passes. |
| I1-m3 (unexpected exceptions exit 1) | Resolved | `serial_check.py:459` and `:616` catch `Exception`. `test_main_unexpected_exception_is_exit_2` passes. |
| I1-m4 (thin pytests coverage) | Resolved | 20 `pytests-unit-*` variants are in `all`, and the validation R2-1 run shows all of them AGREE. |
| I1-m5 (double-null wording) | Resolved | The README now says "no runnable double-null case". |
| I1-m6 (uninformative ERROR line) | Resolved | `error_cause` adds the last traceback line and the last UEDGE error line. `test_error_cause` passes. |
| I1-m7 (stronger acceptance runs) | Resolved | Validation R2-1 runs independent builds over all of `all` (complete gate). I reproduced the ulp control on `quick` (above). |

**Rebuttal: the final `yl` is not recorded separately.** Accepted. In an iterating case the tool compares, bit for
bit, `yldot_probe = ffun(yl_final)` over all `neq`, `get_fnrm` at the final state and the whole printed sequence. A
`yl` difference that leaves every residual entry bitwise equal would need entries that do not enter any residual, and
the solver leaves those unchanged anyway. What stays uncovered is code that runs only after convergence (for example
the copy to `nis`/`tes`). That is outside the serial pandf/Jacobian/solver path the epic changes. Recording `yl`
would be a natural addition when the core `worker.py` is next touched.

**Core commits not in the branch (f46f7a4..de57d59).** None changes this tool's verdicts.
- The `csr_entries` consistency check turns an inconsistent CSR into a harness error rather than a possible silent
  misread. serial_check gains it on rebase.
- `exit_code([]) == 2` is not reachable from serial_check, which always passes a single report.
- `_text(premeth)` affects only `worker.py` provenance.

Rebase before merge as usual.

## What was checked and how

- Read `git diff 71b0e3b..HEAD` in full, all of `serial_check.py`, `pytests_worker.py`, `build_probe.py` and
  `test_serial_check.py`, and the core `compare.py` (`check_arm`, `compare_records`), `worker.py` (`run`, capture)
  and `runner.parse_iterations`. Also read `git diff 71b0e3b..de57d59 -- tests/deterministic_omp/harness/`.
- Unit tests: `venvs/base-serial/bin/python -m pytest -q tests/deterministic_omp/harness` gave 45 passed.
- Runs (`--jobs 2`, outputs under
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev53r2/`):
  - `self`: base-serial vs base-serial, `quick`, no flags. HARNESS ERROR, exit 2.
  - `selfallow`: same, `--allow-same-build`, two `-it` cases. INCOMPLETE, exit 2.
  - `ulp`: base-serial vs AIUE-53-ulp, `quick`. 8/8 MISMATCH, exit 1. The ulp tree differs from 3865c79 only by the
    reassociation at `bbb/pandf_plasma_energy.m:436-437` (checked with `git diff`). It shows as DIRTY with a warning.
  - `q47`: base-{serial,omp} vs AIUE-47-{serial,omp}, `quick --partial-ok`. 16/16 AGREE, `AGREE, PARTIAL`, exit 0.
  - `h47`: AIUE-47-serial vs itself, both hooks, `-it` cases. `jacobians 2+post(psetnk)`, AGREE.
- Fake-run guard probes (`fakes/test_guards.py`, real `main` with fakes): five source states give a complete-gate
  AGREE (I2-M1).
- Build and source timing: installed `bbbpy*.so` mtimes against the source trees' HEAD commit times, and the last
  Fortran commit per tree (I2-m1).
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` from the worktree: `OK`, exit 0
  (informational re-read notes only).
- Commit trailers: e06fb93 and da3c05b, which touch `.claude/context/`, carry `AI-layer: code-facts`. The
  `.claude/plans/` file is an artifact (`branching.md`, `change_kind.py`). No skills, agents, hooks or settings change
  on the branch.
- `physics-models.md`: not applicable, because no model or switch is added.
