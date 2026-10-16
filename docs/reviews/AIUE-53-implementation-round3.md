# AIUE-53 Serial old-vs-new bitwise check: implementation review, round 3

Reviewer: uedge-reviewer (independent referee)
Branch: `feature/v9-AIUE-53-serial-bitwise-check` @ 1a4a34a, rebased onto the harness core
`feature/v9-AIUE-49-omp-harness-core` de57d59 (ancestor of HEAD, checked). New commits: `351ae5a..HEAD`
(0a6ea6f, 914d5e4, 1a4a34a).
Round 2: `docs/reviews/AIUE-53-implementation-round2.md`. Response: `docs/reviews/AIUE-53-implementation-round2-response.md`.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 1 MINOR.

## Summary

All three round-2 findings are fixed, and I checked each one myself. I re-ran my round-2 fake-run probes against the
new `main`, with three extra states and a clean control. Each source-guard state now gives `RESULT: INCOMPLETE ...
(not the gate: <reason>)` and exit 2. The clean control is the only one that still gives the complete-gate AGREE. On
real builds, the negative control still fails (8/8 MISMATCH, exit 1), self-comparison is still a HARNESS ERROR, and
base vs AIUE-47 is `INCOMPLETE ... build older than HEAD` because of a real stale build. That stale flag is a true
positive: commit 63370bd changed `bbb/bbb.v` after `venvs/AIUE-47-omp` was installed. The dirty-tree and stale rules
are strict but usable: commit, build, run the check, then record. One weakness is left, a MINOR. The stale test looks
only at the HEAD commit time. So it misses a tree moved to an *older* commit (or reverted) after the build, and it
flags docs-only commits after the build.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I3-m1: The stale-build test compares commit time, not the build inputs, so it works in one direction only.**
- Location: `serial_check.py` `is_stale` and `source_info` (`head_time` = `git log -1 --format=%ct`), and
  `build_probe.py` `extensions_mtime`.
- **Missed case.** The tree is moved to an older commit after the build, or dirty edits that were built are reverted.
  I showed this with the real `source_info` and `is_stale` on a throwaway repo
  (`scratchpad/rev53r3/stale/probe_stale.py`):
  - Build B at time T. Then `git checkout A`, where A is older and is `origin/v9-develop`.
  - The result is `head A, dirty False, on_base True, stale False`.
  - So a base venv that holds B's code is recorded as a clean v9-develop base. If the new tree is B, the other guards
    don't catch it: the extension hashes differ, the trees differ, and the HEADs read now differ. The run is then a
    complete-gate AGREE of B against itself.
  - A pull of commits whose committer time is earlier than the build misses in the same way. One example is a GitHub
    merge made before a local build of the older tip.
  - All of these break the documented rule ("build from a clean committed tree and don't touch it until the check is
    done"). The README states that the tree is read at check time, and round 2 accepted that limit (I1-M2). So this
    stays MINOR, the same severity as I2-m1.
- **False positive.** A docs-only commit after the build flags the build stale (same probe:
  `docs-only commit after the build ... stale True`). That costs a reinstall but can never give a false AGREE. I accept
  it as conservative.
- **Suggestion (optional).** Use the latest mtime of the tracked build inputs in the source tree (`git ls-files` over
  `*.m`, `*.v`, `*.F90`, hand-written `*.f`, `*.c`, `setup.py`, `Makefile.Forthon`, `*/Package*`), alone or alongside
  `head_time`, and compare it with `extensions_mtime`. Git writes every file it changes with the current mtime.
  - This catches a checkout, reset or revert after the build. In the probe, `bbb/a.m` mtime 1792066046 is later than
    the build at about 1792066044.
  - It also catches real code commits. In the AIUE-47 case, `bbb/bbb.v` was rewritten by the 63370bd work.
  - It no longer fires for docs-only commits.

## Status of previous findings

| ID | Status | Evidence |
|---|---|---|
| I2-M1 (complete gate when the source guard could not run, or the base is off v9-develop) | **Resolved** | `check_pair` returns a `gate` list, and it is added to `result["incomplete"]`. I re-ran `scratchpad/rev53r2/fakes/test_guards.py` against the new code (copy in `rev53r3/fakes/`, with the fake `-it` records given two iterations so that I2-m2 does not turn them into ERRORs). Results: both sources unknown (`.whl`) gives `INCOMPLETE ... source unknown`, exit 2. `on_base_ref=False` and `None` give `base not on origin/v9-develop`, exit 2. Same HEAD with new dirty, and with both dirty, give `dirty tree`, exit 2. My extra states: new dirty state unknown gives `dirty tree`, exit 2, and a stale base gives `build older than HEAD`, exit 2. The clean control is the only `AGREE (bitwise identical; complete gate)`, exit 0. The unit test `test_source_guard_states_are_not_the_gate` asserts the same states, plus the `--partial-ok` path giving `AGREE, PARTIAL` with the reason named. A real run (R3-3 in the validation record) with a `.whl` URL substituted gives `INCOMPLETE ... source unknown`. The README "Not the gate" list, `testing.md` and `openmp-jacobian.md` match the code. The decision on dirty trees (INCOMPLETE, not a warning) is what I asked for. A mismatch is still never hidden: the ulp run on a dirty tree gives `RESULT: MISMATCH`, exit 1. |
| I2-m1 (the HEAD read at check time can name the wrong commit) | **Partially resolved** (MINOR, does not block) | The forward case, a commit after the build, is caught and makes the run INCOMPLETE. My real run base vs AIUE-47 gives `NOT THE GATE: omp0 new: HEAD e71fafca87d7 ... committed after the build was installed` and the adjusted different-commits warning. I confirmed it is a true positive: the `.so` files are dated 01:30, and the later commit 63370bd (04:52) changes `bbb/bbb.v`. The reverse case, a checkout or revert to an older state after the build, is not caught. See I3-m1. |
| I2-m2 (no check that an `-itN` case iterated) | **Resolved** | `iteration_problems` turns an AGREE or MISMATCH into an ERROR when a record of an `itermx` case shows fewer than 2 printed iterations or a post-exmain Jacobian not from `psetnk`. My first fake re-run, whose `-it` records had no iterations, showed that this works: every variant gave `HARNESS ERROR`. The unit tests `test_iteration_problems` and `test_main_case_that_did_not_iterate_is_error` pass. The real records pass the check: in my base vs AIUE-47 run and in the ulp run, the `-it` cases show `iters 4`/`6` and `post(psetnk)`, with no ERROR. |

## Workflow questions raised by the main session

- **Is "dirty → INCOMPLETE" usable for a PR?** Yes. `git status --porcelain --untracked-files=no` ignores untracked
  files: review drafts, scratch outputs, the main repo's untracked `tests/`. The build does not dirty the tree: the
  real base and AIUE-47 trees read clean after their installs. Only modified tracked files count. The workable order
  is: commit, build both venvs, run the check, then write the validation record. Source state is read once, at the
  probe stage, so editing the record after the probes have run does not affect that run. Scratch trees such as the
  ulp control still report MISMATCH, exit 1.
- **Does the stale rule fire for docs-only commits after a build?** Yes (I3-m1). Committing the validation record
  after the run is common here (1a4a34a, and f7f6e8b on AIUE-47). It does not invalidate the RESULT line pasted from
  that run. It does mean a later re-run needs a reinstall first. A rebase before merge rewrites committer times and
  usually changes the code too, so it also forces a reinstall, and it should. It never yields a false AGREE, so it is
  acceptable. The one real example on this machine shows the rule catching a real `.v` change.

## New code: regressions or problems

- `result_line` tags: every message `check_pair` produces maps to a tag in `INCOMPLETE_TAGS`. An unmatched message
  falls back to "see NOT THE GATE" and does not lose the INCOMPLETE status. The `is not origin/v9-develop` key is
  hard-coded and so tied to `BASE_REF`. That is cosmetic only.
- `dirty is not False` treats an unknown dirty state as not clean, which is correct. `head_time None` makes
  `is_stale` False, but in that state `git log` on a HEAD that `rev-parse` just resolved has failed, which is very
  unlikely.
- An ERROR from `iteration_problems` takes precedence over a MISMATCH (exit 2, not 1), which is consistent with "an
  error wins over a mismatch".
- No change to skills, agents, hooks or settings on the branch. 914d5e4 touches `.claude/context/` and carries
  `AI-layer: code-facts`. 0a6ea6f and 1a4a34a touch no AI-layer files. The `CLAUDE.md` difference from
  `origin/v9-develop` comes from the core base (483d57a), not from this ticket.

## What was checked and how

- `git diff 351ae5a..HEAD`: read `serial_check.py`, `build_probe.py`, `test_serial_check.py`, the README and the
  context docs in full. `git merge-base --is-ancestor feature/v9-AIUE-49-omp-harness-core HEAD`: true, core at
  de57d59.
- Unit tests: `venvs/base-serial/bin/python -m pytest -q tests/deterministic_omp/harness` gave **57 passed**.
- Fake-run probes, using the real `serial_check.main` with `probe_build`, `source_info` and `run_case` faked:
  `scratchpad/rev53r2/fakes/test_guards.py` (as written in round 2), then
  `scratchpad/rev53r3/fakes/test_guards.py` (iterating `-it` records, three extra states, a clean control). Results
  are in the table above.
- Stale-rule probe on a throwaway git repo with the real `source_info` and `is_stale`:
  `scratchpad/rev53r3/stale/probe_stale.py`. It gives a docs-only commit stale=True and a checkout to an older commit
  stale=False (I3-m1).
- Real runs, `--cases quick --jobs 2`, outputs under
  `/private/tmp/claude-501/-Users-holma-Documents-uedge-src-UEDGE-v9-dev/2129e705-3f07-427f-a973-d2dbc3c7ccdb/scratchpad/rev53r3/`:
  - `q47`: base-{serial,omp} vs AIUE-47-{serial,omp}, both pairs, no `--partial-ok`. 16/16 AGREE,
    `RESULT: INCOMPLETE (... not the gate: build older than HEAD, cases skipped)`, exit 2.
  - `ulp`: base-serial vs AIUE-53-ulp. 8/8 MISMATCH, including `repro-tebox-it5` and `pytests-{D_only,D+C}-it5` at
    `iters 4`/`6` with `post(psetnk)`. `RESULT: MISMATCH`, exit 1, with the dirty-tree NOT THE GATE line shown.
  - `self`: base-serial vs base-serial gives `HARNESS ERROR ... same build`, exit 2.
- Provenance of the stale flag: `git log` and `git show --stat` in `uedge-wt/AIUE-47`, where 63370bd touches
  `bbb/bbb.v` after the build. `stat` of the `venvs/AIUE-47-omp` `.so` files gives Oct 15 01:30:32.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` from the worktree: `OK`, exit 0 (re-read
  notes only).
- Commit trailers and AI-layer scope: `git show --stat` for the three new commits, and
  `git diff --name-only de57d59..HEAD`.
- `physics-models.md`: not applicable, because no model or switch is added.
