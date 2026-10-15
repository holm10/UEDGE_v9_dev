# AIUE-58 RHS RCA: implementation review, round 2

Ticket AIUE-58 "RHS RCA (bonus)" (epic AIUE-8). Branch `feature/v9-AIUE-58-omp-rhs-rca`, tip `fc26922` (round 1
reviewed `ee291a4`). Reference: the ticket's acceptance criteria (an RCA RHS section with root causes or a
known-limitation statement with evidence; an owner decision prepared), the round-1 report and the authors' response
`docs/reviews/AIUE-58-implementation-round1-response.md`.

## Verdict

**APPROVE**

## Summary

All round-1 findings are resolved, and I checked each one myself. R3 now describes the real mechanism. `gallot` calls
`setarraypointer` before the fill, and the generated `apisetarraypointer<var>` gives every worker a `copyin`'d copy
of the unfilled block. The fix direction is now a full worker refresh after `ueinit`. The jac-arm "use-after-free"
paragraph has been replaced by a correct note. AIUE-50 F15, the AIUE-60 A6 row and the AIUE-61 plan now agree with
the RCA. The new `reexmain` control reproduces: in my run the block moved (2194 Te rows, up to 3.7e34) and the second
`exmain` with `icntnunk=0` still gave a bitwise-equal RHS, also after a 1e-3 perturbation. The authors' rebuttal on
Q6 is correct. The status line and the Decision section say plainly that only R1's fix was tested. Three new MINORs
remain: the leftover's bound and how much the control isolates, option B's internal consistency, and untracked scratch
folders. None of them blocks approval.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I2-m1: The "≤ 5.5e-9 component" is presented as a fixed bound and as one component, and the `reexmain` control
does not separate the copy from the column loop.**
- *Location:* R3 row, evidence and fix-direction cells; evidence-by-configuration row "`te` probe, `ueinit`, then a
  second `exmain`".
- *The bound:* it is a value observed at the first `exmain`'s `yl0`. My run of the committed probe ended with a
  `ueinit` after the `reexmain`, at a different state, and the block was reused (`emcoef` address unchanged). That
  gave 791 Te rows up to **8.1e-9**. The author's `stepless` record also has different counts in two consecutive P
  evaluations at the same `yl` (988, then 760), so the leftover depends on the state and the schedule.
- *"The same component as the reviewer's reassign":* this is inferred from the matching `max_rel`.
- *The control:* the `reexmain` Jacobian runs the copy (`OmpCopy*`) **and** the column loop, whose local `pandf`
  calls also rewrite worker state. For R3 proper this does not matter, because nothing on a worker writes the
  `Imslwrk` tables except the copy. For the unlocalised leftover, though, the control shows only that "a Jacobian
  after `ueinit`" removes it, not that "master `pandf` + `OmpCopy*`" alone does.
- *Acceptance:* the leftover is described by the values observed at each state, not as a fixed bound. The text says
  the control includes the column loop. AIUE-59's acceptance check (already named) then shows that the refresh alone
  removes the leftover.

**I2-m2: Option B is no longer self-consistent after the R3 correction.**
- *Location:* §Decision, options table, row B.
- *The problem:* R3's fix direction is now the same full worker refresh after `ueinit` that fixes R2 (refresh point
  1). So "R3 + R4, R2 remains for indexed/Fortran-side input changes" cannot both hold, unless B's R3 fix means
  refreshing only the `Imslwrk` arrays. That variant leaves the ≤ 5.5e-9 / 8.1e-9 component.
- *Why it is minor:* the owner chose A, so B is moot.
- *Acceptance:* either mark B as superseded by the owner decision, or say that B's R3 fix is the `Imslwrk`-only
  refresh.

**I2-m3: Untracked scratch folders in the worktree.**
- *Location:* `git status` shows `docs/rca/AIUE-8-data/rhs/probe/tebox_t4_try/` and
  `docs/rca/AIUE-8-data/rhs/seq/try_ti_serial/` as untracked.
- *The problem:* no record cites them (`grep -rn` over `docs`).
- *Acceptance:* delete them, or keep them out of the merge commit (`git add -A` would pick them up).

## Status of previous findings

| ID | Status | Evidence (checked by the reviewer) |
|---|---|---|
| I1-B1 R3 mechanism, fix direction, jac-arm paragraph | **Resolved** | `Forthon.h:1241-1270` (AIUE-56-omp venv): `Forthon_freearray`, then `PyArrayFromFarray`, then `setarraypointer`, then the init fill. `api_p.F90:1222-1252` (AIUE-56 build tree): the threadprivate `SAVE pcopy__`, `copyin(pcopy__)`, `tid>0 → emcoef => pcopy__`. The R3 row cites both and names all 12 `Imslwrk` arrays (`api/api.v:148-172`). The fix direction is "full worker refresh after `ueinit`", with dropping `copyin` "hygiene only". The jac-arm bullet is replaced by a correction note. The note agrees with the generated `OmpCopyPointeremcoef` (`api_p.F90:366-380`, which writes through the worker's current association) and with the `copyin` at `ppp/omp_parallel.F90:721`. The fix-tickets row (`:553`), F15 (`:837`), AIUE-60 plan A6 (`AIUE-60/.claude/plans/AIUE-60-omp-races.md:32`) and the AIUE-61 plan (`:251-252`, which keeps the `copyin` list) are consistent. No "dangling" or "use-after-free" claim is left (grep). Only `bbb` and `api` carry `+threadprivate` (`aph`, `com` and the rest have none), so "OmpCopy* of all packages, as `OMPJacBuilder` does" (bbb/com/api) covers every threadprivate variable. The archived discriminating run (`review_round1/r3`: `r3.json`, `b1vahl_error_count.txt` = 78876, the script and `run.sh`) matches my round-1 output. |
| I1-M1 Which fixes were tested | **Resolved** | The status line says "**Only R1's fix was built and tested** … The R2, R3 and R4 fixes were neither built nor run, so whether the combined fix restores a correct RHS is not shown; it is AIUE-59's acceptance". §Scratch test says "the only fix that was built and tested". §Decision opens with "What is tested". Option A says "Expected, **not shown**". "Explain every" now reads "account for every RHS-arm failure traced here". The R4 trace scope is labelled. |
| I1-M2 Refresh points, Q6, AIUE-61, `emcoef` owner | **Resolved** | The owner decision is recorded (A + Q6; AIUE-59 after AIUE-60/61). The AIUE-61 plan's Q6 row (`AIUE-61-omp-static-partition.md:53`) independently states the referral and the ordering. Four refresh points are defined: after `ueinit` and before the first parallel RHS, with the reason it must not come before `ueinit`; after each OpenMP Jacobian; every worker, including workers that drew no chunk under AIUE-61; Python whole-array assignments. I checked the order in code: `exmain` sets `ijactot=0` for `icntnunk=0` (`bbb/odesetup.m:6799`) before `uedriv` → `ueinit` (`bbb/odesolve.m:118`), and `OMPPandf1Rhs` runs serially while `ijactot=0` (`ppp/omp_parallel.F90:955,997-999`). So "with `icntnunk=0` the Jacobian already copies; the point must hold for `icntnunk=1`" is right. AIUE-59 is named as the single owner of removing `emcoef` from the `copyin`. **The authors' rebuttal is accepted.** My round-1 wording ("Q6 … needed for correctness … for `Nxchunks>1`, where R1-class reads remain"; and for R2/R3) was wrong. After a Q6 refresh a worker holds the Jacobian state's value at `xe+1`, and the next RHS at a trial state reads that stale value, so Q6 alone does not correct an R1-class read. R2 and R3 happen before the first Jacobian of an `icntnunk=1` `exmain`, so only point 1 helps there. |
| I1-m1 Scratch patch widens `hcxi`/`hcyi` | **Resolved** | Note in §Scratch test, with the recommended minimal form for AIUE-59. |
| I1-m2 R4 attribution inferred | **Resolved** | The R4 row, the pre/post table and the status line label the untraced crashes "inferred". |
| I1-m3 R2 and Forthon assignment semantics | **Resolved** | The R2 row and the static list are correct: `Forthon.h:810-825` (`setaction`, then `setarraypointer` on a dimension-matched whole-array set); `fnuizx`/`fnucxx` are scalars (`bbb/bbb.v:2215-2216`); `cftgtipltl/r` are fixed-size (`:857-858`); `kye_use` is dynamic (`:2190`). |
| I1-m4 Scratch patch not recorded | **Resolved** | `r1_scratch_hcyn.patch` is byte-identical to `git -C uedge-wt/AIUE-58-hcyn diff` (HEAD `1553e75`). |

## Not independently verified (environment)

- The owner decision's Jira sources (the AIUE-59 description, comments 10022/10024/10025): I have no Atlassian access.
  The AIUE-61 plan's Q6 row is consistent with them.
- Linux, double null, `isimpon=2`, TSan: not run by the authors (stated), and not run here.
- R1 at 1, 2 and 8 threads, `Nxchunks=4`, and the Newton-level sequence counts: checked against the records in round
  1 and not rerun.

## What was checked and how

- `git diff ee291a4..fc26922`: the RCA section, records, the response, the round-1 report, and a `reexmain` step in
  `tests/deterministic_omp/rhs/rhs_probe.py` (test script only). There is no `.m`, `.v`, `.F90`, build or
  `.claude/` change.
- `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: **OK**. It prints its standing
  advisory list of AI-layer docs that cite `CLAUDE.md` or `testing.md`; none of those files changed on this
  branch.
- `uv run .claude/hooks/change_kind.py --range 8277210..HEAD`: **OK**. Ticket branch, artifacts plus `tests/` scripts.
- **Forthon and generated code:** `Forthon.h:1236-1275` and `:810-830` in `venvs/AIUE-56-omp`. In
  `AIUE-56/build/temp.macosx-26.3-arm64-cpython-313/api_p.F90`, lines `:1222-1252` (setarraypointer) and `:366-380`
  (OmpCopyPointeremcoef). The `threadprivate` counts per `.v` file.
- **Code path:** `api/apip93.m:91-111`: `gallot` is at `:108`. The RCA's `:101-107`, carried from round 1, is off
  by one line, which is immaterial. Also `bbb/odesetup.m:1130,1150`, `bbb/odesolve.m:118`,
  `bbb/odesetup.m:6793-6803` and `ppp/omp_parallel.F90:645-720,940-1001`.
- **Records:** `probe/te_t4_ueinit_reexmain` (`reexmain_ijactot = [1]`, so a Jacobian ran; the `emcoef` address was
  reused; 889/889 → 0 → 0) and `probe/te_t4_ueinit_stepless` (exit 2 at the then-unknown step, as labelled; 988/760
  rows). `review_round1/hcyn_ti`: every step `ndiff = 0`; the provenance is the `AIUE-58-hcyn` build, dirty as
  recorded.
- **Run 1 of 1** (AIUE-56 OpenMP venv, `te` preset, 4 threads, committed `run_probe.sh`/`rhs_probe.py`): steps `same,
  ueinit, reexmain, pert:1e-3, ueinit`. Output `/tmp/aiue58-r2/te_reexmain/probe.json`, exit 0, 4 s.
  - `same`: 0.
  - First `ueinit`, block **moved**: 2194 Te rows, max_rel 3.74e34.
  - `reexmain`, `ijactot` 1: **0/0**.
  - `pert:1e-3`: **0/0/0**.
  - Final `ueinit`, address reused: 791 rows, max_rel 8.1e-9 (I2-m1).

  This reproduces the authors' control and makes it stronger: a full Jacobian copy after `ueinit` restores a
  bitwise RHS also in the moved-block (garbage-table) case, which their record did not cover. It also shows the
  defect returns at the next `ueinit`, which supports refresh point 1 for every `exmain`. This run printed no
  `B1VAhL` messages although the max_rel was the same as in round 1. So the error count is not a reliable
  indicator, and P ≠ S with the old tables alive and equal stays the discriminating evidence, as the RCA uses it.
