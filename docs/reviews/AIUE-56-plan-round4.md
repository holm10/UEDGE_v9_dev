# AIUE-56 plan review, round 4

Plan: `.claude/plans/AIUE-56-omp-jacobian-fix.md` (committed in `4fae2f9`, unchanged since). Previous reports:
`AIUE-56-plan-round{1,2,3}.md` (round 3: REVISE 0/1/1). Responses: `AIUE-56-plan-responses.md`.
Reviewer: uedge-reviewer (plan stage, finding prefix L). This round goes past the 3-round cap with the owner's
permission. Read-only: no builds and no runs, except the context-reference checker.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 0 MINOR (no new findings).

- L3-M1 is resolved.
- L3-m1 is resolved. One stale sentence is left over from it; see the editorial note, which is optional.

## Summary

The plan now applies the magnitude and deviation gates (3–4) only to the one-evaluation runs. In those runs the
compared Jacobian is the first one of the process, from `sfsetnk`. It is column-scaled only: not row-normalised
and not permuted. I checked this in the solver source and in the harness. The `--itermx 3` runs are explicitly
report-only.

The negative and positive controls are named, with their expected outcomes, on fresh `base-omp` runs made with
the reviewed core. The validation record shows the gates were applied as the plan describes:
- every post-fix one-evaluation run passes, with a worst deviation of 7.2e-9 of the serial row max, against a
  bound of 1e-6;
- the four C1-sensitive base controls fail by about 1e38;
- the four presets without Te rows pass, both pre-fix and post-fix.

The code change, the default-safety argument and the AI-layer facts are unchanged since round 3 and are still
correct.

## Findings

### BLOCKER
None.

### MAJOR
None.

### MINOR
None new. Under the round-2+ rule I raise no new minors about unchanged material.

## Status of previous findings

| Finding | Status | Evidence |
|---|---|---|
| L3-M1 gates 3–4 invalid on `--itermx 3` runs | **Resolved** | See below. |
| L3-m1 negative control ill-defined | **Resolved** (one stale sentence left; see the editorial note) | See below. |

**L3-M1.**

- **Plan text.**
  - Plan lines 119-122: "Gates 3 and 4 apply to the **one-evaluation runs** only (`ftol=1e20`: the compared
    Jacobian is the first, `sfsetnk` one — unpermuted, not row-normalised …). The `--itermx 3` runs … are
    **report-only** (round-3 L3-M1); their `sfscal`/final-`fnrm` agreement is reported too."
  - Gates 3 and 4 now say "in every one-evaluation OpenMP run of step 3" (plan lines 124, 126).
  - Gate 5 (`check_arm`) still covers every run, which is correct.
- **The premise holds.**
  - The harness sets `bbb.ftol = 1e20` when `itermx` is None (`AIUE-49/.../worker.py:174-175`).
  - `nksol` then calls `nkstp0` and leaves before the iteration block (`svr/nksol.m:1014-1015`). `nkstp0` sets
    `iterm=1` when `fmax ≤ 0.01·ftol` (`svr/nksol.m:1398-1399`). So `psetnk`, `jac_norm_rows` and `jac_reorder`
    never run.
  - `sfsetnk` applies only `amudia` with `1/su`, i.e. column scaling, and then `rnrms`, which computes the row
    norms into `sf` and doesn't modify `jac` (`bbb/oderhs.m:2333-2346`).
  - The harness labels these records `sfsetnk` and unpermuted (`worker.py:196-214`). The gate script then uses
    the `eq`-based Te rows (`AIUE-56-c1-gate.py:69-72`).
- **Applied as written.**
  - The gate-script table in `AIUE-56-validation.txt:9-28` lists only one-evaluation (`it0`) directories.
  - The two `it3` directories appear only in the report-only block (`:89-101`): fnrm sequence, sfscal mismatches
    = 0, final fnrm.
- **`check_arm` on the itermx and jacrhs runs.**
  - Their `check_arm` is covered by `cli.py check`. Any `check_arm` problem is a comparison error and gives exit
    2 (`compare.py:221-223`, `cli.py:44-49`).
  - Every recorded exit code is 0 or 1 (`validation.txt:32-55`).

**L3-m1.**

- **Plan text.** Plan lines 134-136: "Controls (round-3 L3-m1), fresh `base-omp` runs with the reviewed core, one
  evaluation, 4 threads, K=3: `tebox`, `full`, `te`, `te_phi` must FAIL both bounds (negative controls); `ti`,
  `ni`, `up`, `ng` have no Te rows and must PASS (positive controls …)". This is the set and the expectations that
  round 3 asked for.
- **The script handles presets without Te rows.**
  - `max(initial=0.0)` gives 0/0, which the script maps to ratio 0 (`c1-gate.py:71-75`). Gate 3 is therefore
    vacuous there, not undefined.
  - Gate 4 is evaluated on all rows.
- **Applied as written.**
  - `run_protocol.sh:27` runs exactly these 8 presets on `base-omp` at 4 threads with K=3.
  - The results are FAIL for tebox, full, te and te_phi (worst 2.6e38 to 6.9e38) and PASS (bitwise 3/3) for ti, ni,
    up and ng (`validation.txt:21-28`).

**Editorial note (optional, no severity).** Two sentences still point at the earlier control design:
- Testing step 3, last line (plan line 102): "The same protocol on `base-omp` for the cases not covered by
  AIUE-54's K=20 data (negative control)";
- Dependencies (plan line 31): "re-run here as a negative control where a protocol differs".

Read literally, they ask for `base-omp` runs at 2 and 8 threads, and they treat the AIUE-54 data as a control.
Round 3 established that the AIUE-54 data can't be put through the gate script (no `record.npz` survives). The
execution followed the Acceptance section, which is the pre-registered and authoritative one. No gate depends on
these two sentences. Aligning them with plan lines 134-136, or recording the deviation in the validation file,
would remove the contradiction.

## Remaining-risk check (looking for any BLOCKER/MAJOR)

- **Code change matches the plan.**
  - `git diff origin/v9-develop -- ppp/` moves the `OmpCopyScalar*` block ahead of the `OmpCopyPointer*` block in
    `OMPJacBuilder`.
  - It adds the ordering comment, including the hazard of `OMPCopyScalar=0` with `OMPCopyArray=1`.
  - There are no other Fortran changes.
- **Defaults.**
  - The serial check reports AGREE (bitwise, complete gate, 42 cases, both builds) (`validation.txt:6`).
  - The D_only per-file outcomes are identical between base-omp and AIUE-56-omp (`:83-86`).
  - Both results are consistent with the plan's argument that the default path is unreachable.
- **The round-3 residual risk on gate 4 is retired by data.** Round 3 flagged gate 4 on the full problem as
  undemonstrated. The worst post-fix ratio there is 4.6e-9 of the serial row max (`validation.txt:10,14`), more
  than 200× inside the bound. The gate passed because the bound held, not because it was too loose: the residual
  entries are counted (903–2428 per run) and reported.
- **Tool lineage.** The validation used the harness at `cf23ddf` and `de57d59`. Both descend from `71b0e3b`
  (`git merge-base --is-ancestor`), and the commits in between change docs and minor `cli/compare/worker` code
  only (reviewed in AIUE-49 round 2). This satisfies "71b0e3b or later".
- **AI layer.** `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` prints OK (exit 0).
  - The plan said "Nothing else cites the moved lines", but `mppl-fortran.md` did. The plan's own hedge ("check
    with `check_context_refs.py`") caught it, and `47e02cc` (trailer `AI-layer: code-facts`) fixed it.
  - This is not a defect of the gate.
  - The plan file sits under `.claude/plans/`, which `branching.md:13` classes as a ticket artifact. That's fine.
- **Deviations from the plan, not plan defects.**
  - Timing used K=8 instead of 10. The validation file records this.
  - The epic's bitwise line is "not met". That is owner decision 9 and out of scope here.

## What was checked and how

- **Plan and earlier reviews.** Read the plan in full, the round-3 report and all responses. Ran `grep -n` for
  "every OpenMP run", "AIUE-54's K=20" and "negative control" in the plan.
- **Plan file history.**
  - `git log -- .claude/plans/AIUE-56-omp-jacobian-fix.md` shows one commit, `4fae2f9`.
  - `git status`: the working tree is clean.
- **Code.** `git diff origin/v9-develop --stat` and `git diff origin/v9-develop -- ppp/` for the code change.
  `git diff` of `mppl-fortran.md` and `refs.lock.json`, and the `47e02cc` trailer.
- **Solver path.**
  - `bbb/oderhs.m:2328-2360` (`sfsetnk`: `jac_calc_interface`, `amudia`, `rnrms`).
  - `svr/nksol.m:1005-1020` and `:1391-1402` (`nkstp0` early exit).
- **Harness (AIUE-49 worktree).**
  - `worker.py:174-214`: ftol, `jac_post` source, the `post_exmain_from`/`permuted` labels.
  - `cli.py:44-90`: `exit_code`, `cmd_check`.
  - `compare.py:204-235`: `check_arm` errors give exit 2.
  - The ancestry of `cf23ddf`/`de57d59` from `71b0e3b`, and `git log 71b0e3b..de57d59 --stat`.
- **Evidence the plan was applied.**
  - `docs/reviews/AIUE-56-c1-gate.py` in full: Te-row selection, all-row deviation bound, `check_arm`
    integration, the no-Te-rows path.
  - `docs/reviews/AIUE-56-run_protocol.sh`: which runs, which K, which control set.
  - `docs/reviews/AIUE-56-validation.txt` in full.
- **AI-layer check.** Ran `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: OK.
- **Not done.** No builds and no UEDGE runs (read-only round). I didn't recompute the gate on the run
  directories: they are in a session scratchpad, and this verdict is on the plan.
