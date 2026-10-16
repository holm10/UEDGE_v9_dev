# AIUE-60 implementation review, round 2 (covers plan amendment 1)

Ticket AIUE-60 (epic AIUE-8): "Fix remaining OpenMP races in the pandf tree and the clip-index inconsistency".
Branch `bugfix/v9-AIUE-60-omp-races`, tip `e157a0a` (round 1 reviewed `a2e1550`), stacked on AIUE-56 `1553e75`.
Reference: the approved plan `.claude/plans/AIUE-60-omp-races.md` plus its Amendment 1 as revised in `88ff722`.
Previous reviews: `AIUE-60-implementation-round1.md` (REVISE 1/0/2) and `AIUE-60-plan-amendment1-review.md`
(REVISE 0/4/6), with their responses.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 2 MINOR.

## Summary

Amendment 1 removes the I1-B1 overflow at its root. `com.v` is back to its `1553e75` text and `aph.v` differs from it
only by `workh`. The 10 timers are updated through a new `acctim` helper whose `c$omp atomic` compiles to a CAS loop
in the OpenMP build and to a plain add in serial. `iflag_aph` is replaced by `iflagl` locals, and B2VAhL sets IFLAG
before it reads it, so the change can't affect results. I re-ran G-common on three venvs:
- the amended venv: PASS, `bbb` first at 728 B, `com`/`aph` define nothing;
- the preserved pre-amendment venv: FAIL;
- AIUE-56: PASS.

One run of the `iotable` probe changed exactly words 11 and 12 (0 to 1), the same as AIUE-56. I also re-derived:
- Probe S (146/147/145);
- the flow gates, from the records, with an independent script;
- the clip patterns, from the records, with an independent script;
- the D_only outcomes;
- the timing ratio.

I spot-checked the TSan classification as well. Every amendment-review finding is resolved. The two remaining minors
are wording in the new rule 5 and a fail-open path in the G-common script on Linux.

## Findings

### BLOCKER

None.

### MAJOR

None.

### MINOR

**I2-m1: The rule-5 heading and checklist 4 say "threadprivate scalars only in `bbb`", but `api` already has 12, and
the body allows them.**
- *Location:* `.claude/context/openmp-jacobian.md` rule 5 heading; `.claude/context/variables-forthon.md` checklist 4
  ("A threadprivate **scalar** belongs in `bbb` only").
- *Evidence:* `api/api.v` has 25 `+threadprivate` lines. G-common shows `apipy` defining a 12-variable, 96 B block on
  every build (AIUE-56, pre-amendment, amended). The rule-5 body states the actual invariant correctly: nothing
  before `bbb`, and nothing after `bbb` larger than `bbb`'s block. Read on its own, the heading is false as a
  statement of the code. As a prescription for new scalars it is fine.
- *Resolution (optional):* say "New threadprivate scalars go in `bbb`" (or note `api`'s 12 as an allowed later,
  smaller block), so the headline matches the code and the body.

**I2-m2: `AIUE-60-common-check.py` fails open when `nm` finds no symbols, for example on a stripped Linux wheel.**
- *Location:* `docs/reviews/AIUE-60-common-check.py`, `defines_block` (Linux branch `nm -S`) and the
  "no package defines the block" path in `main`.
- *What is wrong:* `nm`'s return code is ignored. On Linux, `nm -S` reads `.symtab`. On a stripped `.so` it prints
  "no symbols", so every package reads as "not a definer" and the script reports `RESULT: PASS (no package defines
  the block)`. `nm -D` would still see the exported dynamic symbol. An OpenMP build always has `bbb` as a definer, so
  "no definer" is itself an anomaly. This doesn't affect this ticket: on macOS, `nm -m` shows exported symbols, and
  the recorded and re-run outputs list `bbbpy`/`apipy` as definers. It matters if the script becomes the AIUE-57
  Linux CI check, as `openmp-jacobian.md` rule 5 and the plan propose.
- *Resolution (optional, or when the script is adopted for CI):* use `nm -D -S` on Linux, treat a nonzero `nm` exit
  as ERROR, and treat "no definer at all" as ERROR (or require `--serial`).

## Status of previous findings

### Implementation review round 1

**I1-B1: `com` threadprivate scalars caused the `/ompcommonscalarcopy/` overflow into `/iotable/`. Resolved.**
- `git diff 1553e75 e157a0a -- com/com.v` is empty.
- `aph/aph.v` differs only in `workh`. It is an array, which goes through the per-routine `pcopy__`, not the scalar
  common.
- The generated `build/temp.*/{com,aph}_p.F90` (16:51:37, after `728f9d9`) contain 0 `ompcommonscalarcopy`
  statements.
- `nm -m` over all 11 extensions of `venvs/AIUE-60-omp`: definers are only `bbbpy` (0x3d7230, next symbol at 0x3d7508:
  0x2d8 = 728 B) and `apipy`. `compy` has `_iotable_` and no block.
- The venv's `compy*.so` SHA-1 equals the worktree build's.
- G-common re-run:
  - `AIUE-60-omp` + its generated sources: `RESULT: PASS (first definer bbbpy 728 B; others apipy 96 B)`, exit 0;
  - `AIUE-60-omp-pre` + `pre_amend_gen`: `RESULT: FAIL: first definer is compy (80 B) …`, exit 1;
  - `AIUE-56-omp`: PASS, 712 B / 96 B.
- G-iotable re-run (one repeat each, tebox, `jac`, 4 threads, `itermx=1`):
  - base: `2 words changed: [(11, 0, 1), (12, 0, 1)]`;
  - new: `com block absent; 2 words changed: [(11, 0, 1), (12, 0, 1)]`;
  - `new equals base: True`, `RESULT: PASS`;
  - run records `ijactot 2, OMPParallelJac 1, Nthreads 4` for both builds.
- Acceptance (a), (b) and (c) of I1-B1 are met. For (b), see the checks below. For (c), see `openmp-jacobian.md`
  rule 5 and `variables-forthon.md` checklist 4.

**I1-m1: B2 and B4 were never run threaded. Resolved.**
- Stated as "Untested at run time" in the validation record's deviation section, with the reasons.
- Listed for the PR.

**I1-m2: two deviations were not labelled. Resolved.**
- Both appear under "Deviations from the plan" in `AIUE-60-validation.txt`: the `0fac655` base substitution with its
  reasoning, and the `workh` bound text.

### Plan amendment 1 review

**LA1-M1: G-iotable "0 changed words" would fail on correct code. Resolved.**
- The criterion is now differential against AIUE-56, over all 128 words before and after, with a repeatability
  check (`AIUE-60-iotable-probe.py` `check`).
- The positive control (AIUE-56, 2/2 `{11,12: 0→1}`) and the negative control (pre-amendment, 62 words, 2/2) are in
  `AIUE-60-amendment1-controls.txt`.
- My re-run matches.

**LA1-M2: the negative controls would be lost on rebuild. Resolved.**
- Timestamps:
  - `venvs/AIUE-60-omp-pre` copied 16:47:51;
  - `pre_amend_gen/*_p.F90` 16:47;
  - controls `gcommon_aiue56.txt` 16:48:44, `gcommon_pre.txt` 16:48:45, `iotable_ctrl.txt` 16:49:00;
  - committed in `88ff722` at 16:50:41.
- Then the code commit `728f9d9` (16:51:03), the regenerated `build/temp` (16:51:37) and the amended venv (16:53:12).
  So the controls were recorded and committed before the amended build existed.
- The pre venv is really pre-amendment: `compy` defines the 80 B block, and the probe changes 62 words.
- The script takes `--gen` and returns ERROR (exit 2) for a definer without a size or a missing `.so`.
- The scripts are unchanged between `88ff722` and the tip (`diff` empty).

**LA1-M3: scripts were not committed. Resolved.**
- `AIUE-60-common-check.py`, `AIUE-60-iotable-probe.py` and the controls file are in `88ff722`, before the code
  commit.

**LA1-M4: the plan body and AI layer were stale. Resolved.**
- Row A4 is marked "Superseded by Amendment 1".
- Task 1 has an "Amendment 1 (supersedes …)" paragraph.
- Default-results point 4, Task 5 (rule-1 rewrite plus the invariant) and the acceptance checklist (`:498-500`:
  146/147/145, G-common/G-iotable/G-atomic) are updated.
- The committed rule 1 in `openmp-jacobian.md` now says the timers are shared, atomic through `acctim`, and sum
  thread-seconds. The false "master thread only" sentence is gone.
- Two residual stale passages remain. Neither matters, because the Amendment section and the record carry the
  binding numbers:
  - Task 4 (`:312-314`) still lists the pre-amendment Probe S numbers ("137 → 135");
  - the G-common description still says "× 8 B" next to the corrected "sizes come from the declared kinds".

**LA1-m1: pin `acctim` and check it statically. Resolved.**
- The exact helper text is in the plan, and `com/misc.m:108-118` matches it (no `Use`; the directive is directly
  above the assignment).
- In the generated `com/misc.F` (OpenMP and serial worktrees, identical), `c$omp atomic` is on line 115, directly
  above `acc = acc + dt`.
- `otool -tV` `_acctim_`:
  - OpenMP: `ldr` / `fadd` / `cas x2, x3, [x0]` / `cmp` / `b.ne` to `mov x1,x2; b 0x2aba8` (a full CAS retry loop);
  - serial: `ldr` / `ldr` / `fadd` / `str` / `ret`.

**LA1-m2: G-common robustness. Resolved,** apart from the Linux fail-open path (new minor I2-m2).
- The import order is parsed (`uedgeC` … `nclpy`), and sizes come from `kind=`.
- There is a Linux branch.

**LA1-m3: Probe S reachable units. Resolved.**
- 146 was pre-registered.
- Re-run on `git archive e157a0a`: `146 reachable units; 147 variables`, and passed-args 145 entries.
- Both outputs are byte-identical to `logs/AIUE-60/sw_a1.txt`/`pa_a1.txt`.
- The diff against `sw_post2`/`pa_post2` is exactly the unit-count line plus 10 `->acctim` entries.

**LA1-m4: timer semantics and the timing flag. Resolved.**
- "Thread-seconds summed over threads" is stated in rule 1, the plan and the record's PR notes.
- A flag goes to the owner as a decision.
- Timing medians are 11.18 s (AIUE-56) and 11.04 s (AIUE-60), ratio 0.987 (recomputed from `protocol.log`), so there
  is no flag.

**LA1-m5: `aph.iflag_aph` is no longer updated by the rate calls. Resolved.**
- Stated in the plan and in the record's "Behaviour notes for the PR".

**LA1-m6: Forthon text (2). Resolved.**
- Reworded to the `split('(')[1].split(')')[0]` behaviour, with a reference to AIUE-71.

## Not independently verified (environment)

- **Linux/ELF binding and the invariant on CI wheels.** Reasoned only, as in round 1. To verify: G-common with
  `nm -D -S` (see I2-m2) and the `iotable` probe on the Linux OpenMP CI build.
- **AIUE-71 exists in Jira with the proposed text.** I have no Jira access. The plan says "Filed as AIUE-71".
- **8 threads; `istabon=5/6`; limiter sputtering at run time.** These are unchanged from round 1. The `nwfits` data is
  missing, no preset enables them, and the machine rule forbids 8 threads.
- **The full TSan re-run.** I did not re-run TSan, because it was outside the budget. I checked the recorded post
  logs (`logs/AIUE-60/tsan3`), listed under "What was checked".

## What was checked and how

- **Code diff.**
  - `git diff a2e1550 728f9d9` and `git diff 1553e75 e157a0a` over the product files.
  - Line counts are unchanged for `aphrates.m` (1490), `fmombal.m` (1249), `pandf.m` (766),
    `pandf_gas_continuity.m` (1961) and `comutil.m` (10373). `misc.m` grows from 106 to 118 lines, at the end only.
  - `fmombal.m:247-248` is a logical IF with a `call` on its continuation line, which is valid.
- **Timer writes.** `git grep -n -i -w` of all 10 timers across the tree, outside `docs/` and `.claude/`:
  - every in-`pandf`-tree update is `call acctim(...)` (13 sites);
  - the remaining assignments are master-side resets (`odesolve.m:89-90`, `comutil.m:44-45`, `apifcn.m:221`);
  - the rest are prints, `USE` lines, `debug_parallel.F90` writes and `bas2py_rules.py` names.
- **`iflagl` is result-neutral.**
  - `git grep -w iflag_aph`: only the master-side `aphread.m:920-951` setup remains.
  - `B2VAhL` sets `IFLAG = 0` as its first executable statement (`com/comutil.m:3607-3608`), and the return value
    does not depend on IFLAG.
  - `iflagl` and IFLAG are default `integer` in sources compiled with the same flags.
  - The defaults gate (below) is bitwise AGREE.
- **Defaults.**
  - `serial_check.json` (val2, vs `0fac655`): `agree true`, `gate_complete true`, `warnings []`, 42 cases, both
    pairs.
  - The new sides are `AIUE-60` (extension mtime 16:53, the amended build) and `AIUE-60-serial` (clean at `ee76a15`,
    whose product sources equal `728f9d9`).
  - `0fac655` is an ancestor of `origin/v9-develop`, and there is no product diff `0fac655..origin/v9-develop`.
- **D_only.** I compared `val2/donly_{omp,serial}.json` with `val/donly56_*` per file, ignoring timings: 0
  differences. The pre-existing failures are ineudif0/1/3 and tg_atom_cftiexclg0p5, plus concap in serial.
- **Flow gates.**
  - Re-ran `AIUE-60-flow-gates.py` on `val2/flow56`/`flow60`: text and JSON identical to the record.
  - The round-1 independent script found, for both flows: 64 agreement reports, 0 class-X mismatches, 0 RHS-section
    mismatches, 0 Jacobian mismatches outside Te rows.
  - `flow60` and `flow56` used `venvs/AIUE-60-omp` and `AIUE-56-omp` respectively.
  - The cross-build compares are AGREE.
- **Clip.** I ran the independent script over `val2/clip_ni` and `clip_full`:
  - the predictions are 636 497 / 594 104 / 69 401 (`ni`) and 2 474 283 / 2 402 093 / 812 962 (`full`);
  - every new OpenMP run has the serial pattern (0+0 one-sided entries);
  - every base run has the column-rule set;
  - `sfscal` is bitwise equal;
  - the base and new serial patterns and values are equal.
- **TSan (records).** `logs/AIUE-60/tsan3`:
  - the run records have `OMPParallelJac 1`, `Nthreads 4`, `ijactot` 1/1/2/1;
  - `Location is global` occurs only for `ompcommonscalarcopy_`, at `bbbpy` (12 per run), never `compy`/`aphpy`;
  - no frame mentions `acctim`, a timer, `TimingPandfOn`, `nfsp` or `areapl`;
  - the `post_tebox` in-loop reports pair `convsr_aux2` worker reads with `dcopy_u_`/`s2copy_` (the documented
    false-positive class).
  - The TSan tree is `AIUE-60-tsan` at `ee76a15`, dirty only in `setup.py`.
- **AI layer.**
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`: `OK`, exit 0. The list of docs to
    re-read includes skills changed on `v9-develop` since the stack base, which the rebase will bring in.
  - `uv run .claude/hooks/change_kind.py --range 1553e75..HEAD`: `OK`, exit 0.
  - The process files changed only in `1442d23` and `ee76a15`, both with `AI-layer: code-facts`; neither touches
    product code.
  - The `bbb.v` threadprivate count is 526, as `variables-forthon.md` states. `com.v` 0, `aph.v` 1, `api.v` 25.
  - Rule 5 references AIUE-71 and `docs/reviews/AIUE-60-common-check.py`.
- **AIUE-61 readiness.** `bugfix/v9-AIUE-61-omp-static-partition` is at `604a667`, on `1553e75`.
  - `git merge-tree --write-tree e157a0a 604a667` conflicts only in `.claude/context/openmp-jacobian.md` and
    `refs.lock.json`.
  - `ppp/parallel.F90` auto-merges and keeps `sfscal(ii)` (merged `:292` debug, `:296` storage).
  - AIUE-61's `ppp.v` adds no `+threadprivate` line, so rule 5 holds after the rebase.
  - After the rebase, the `ppp/parallel.F90:292` reference in `openmp-jacobian.md`/`refs.lock.json` moves to `:296`.
    AIUE-61 must update it; `check_context_refs` will flag it.
  - Ready to rebase onto `e157a0a`.
- **Process note.**
  - The revised amendment (`88ff722`) was not re-reviewed before the code commit (`728f9d9`, 22 s later). This round
    covers both, as the main session stated.
  - The gate scripts and both controls were committed before the amended build, so pre-registration holds.
- **Runs used.** 2 short UEDGE runs (the `iotable` probe, one repeat on `AIUE-56-omp` and one on `AIUE-60-omp`,
  4 threads). No builds, no reinstalls.
