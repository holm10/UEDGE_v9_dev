# Review: ai-adversarial-ticket-review — implementation, round 1

Branch `feature/v9-ai-adversarial-ticket-review` @ `3b99e75` (one commit on `origin/v9-develop` = `3865c79`).
Files: `.claude/skills/end-to-end-feature/SKILL.md`, `.claude/agents/uedge-reviewer.md`, `CLAUDE.md` (workflow row).
Reference: the user's request ("Use adversarial checks on every ticket to finish up ... update [the ticket-execution
skill] with the adversarial check for the ai-layer"), for unattended, iterative work on AIUE-8 tickets, plus the repo's
AI-layer rules (`CLAUDE.md`, `.claude/context/branching.md`, `create-prd` Step 5).

## Verdict

**REVISE**

## Summary

The change goes on the right kind of branch, passes both hook checks, and mirrors the `create-prd` loop: a fresh
reviewer for each round, a self-contained prompt, 3 rounds at most, reports in `docs/reviews/`. The new `plan` stage in
`uedge-reviewer` is sound. The skill has gaps an agent working alone would hit:
- The rule "nothing is committed until APPROVE" contradicts `execute` and `commit`. The AIUE-8 run did not follow it 12
  minutes after it was written.
- The loop has no fallback when the running agent can't spawn a fresh reviewer.
- It doesn't say what the reviewer may run, or what to do with acceptance criteria that can't be reproduced locally
  (Linux/macOS, CI).
- Code edited after APPROVE goes to commit without another review or validation.
- `implement-fix`, and Jira bug tickets that `plan-feature` routes to it, get no gate at all, although the user asked
  for every ticket.

There are no blockers. Each of the 5 MAJOR findings has a small fix.

## Findings

### BLOCKER

None.

### MAJOR

**I1-M1 — Commit semantics contradict the other skills and the run's own practice.**
*Location:* `end-to-end-feature/SKILL.md` Step 3b, first line ("Nothing is committed until a fresh `uedge-reviewer` has
returned **APPROVE**"); Escalation paragraph (`WIP:` subject); `uedge-reviewer.md` description ("before they are
committed"); Final Summary / Next Steps.
*Problem and evidence:*
- `execute` Step 3b (`.claude/skills/execute/SKILL.md`, "3b. Update the AI-layer facts", item 4) tells the agent to
  commit the code-facts edits before validation, so before Step 3b of `end-to-end-feature` can run. The two skills
  chained by this one disagree.
- The run that wrote this gate did not follow it. The gate was committed at 00:11:30. AIUE-46 was committed at
  00:23:31/00:23:58 (`a61a145`, `483d57a`) as ordinary commits, then reviewed (`docs/reviews/AIUE-46-implementation-round1.md`),
  then the fixes were committed (`f5fee63`, 00:40). Committing first and reviewing `base...HEAD` is the sensible flow,
  and the loop's own prompt already includes "`git diff <base>...HEAD` plus uncommitted changes". The rule as written
  is not what agents do or should do.
- The `commit` skill says "Subject: imperative, capitalised, **no tag prefix**". The Escalation rule requires `WIP:`.
  An agent that follows `commit` drops the marker, and unapproved work then looks like any other commit.
- The Final Summary always prints "4. ✅ Commit" and "Next Steps: Push to remote: `git push` / Create pull request".
  It has no escalated/WIP variant, so an unattended agent is told to push unapproved work.

*Resolution:*
- Define the gate by **status**, not by whether a commit exists. Commits on the ticket branch are allowed at any time.
  The ticket counts as done (Jira "In Review", PR, "Feature Implementation Complete") only after APPROVE on the final
  diff.
- Or keep "no commit" and change `execute` 3b to defer its commit. Either way, the two skills must agree.
- Make the `WIP:` marker work with `commit`: add an explicit exception in `commit`, or use a body line or trailer
  instead of a subject prefix.
- Give the Final Summary an escalated variant with no push/PR next step.

**I1-M2 — No defined behaviour when the running agent cannot spawn a fresh reviewer.**
*Location:* "Adversarial review loop", item 1 ("Spawn a **fresh** `uedge-reviewer` ... Never use a fork").
*Problem and evidence:*
- Nesting is often possible. The current Claude Code docs (code.claude.com/docs/en/sub-agents) say a subagent may
  spawn subagents up to three layers deep. But the `Agent` tool is withheld at the depth limit, "except a fork", which
  this skill forbids. It is also missing when the agent's `tools` list omits it (`uedge-implementer` has only
  `Read, Grep, Glob, Edit, Write, Bash`) or when `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`.
- `branching.md` says parallel tickets are run by subagents. The AIUE-8 run does exactly that: AIUE-47/50/52/53 are run
  by subagents, and per `docs/specs/AIUE-8-progress.md` "the main session runs the adversarial reviews".
- The skill describes neither that hand-off nor what a ticket agent without `Agent` must do. The cheapest failure is
  an agent that reviews its own work and reports "APPROVE".
- "Who fixes" is also undefined in the hand-off case. The implementing subagent has already returned when the REVISE
  arrives.

*Resolution:*
- State that a session that cannot spawn a non-fork `uedge-reviewer` must never review its own work. It stops before
  the gate, commits as in I1-M1, and hands back a ready-to-use review prompt (stage, round, reference, diff range,
  venv, validation output) to its caller.
- State who runs the loop and who applies the fixes when the orchestrator owns the review: the orchestrator itself,
  or a new implementer given the report path.

**I1-M3 — The loop doesn't say what the reviewer may run, or how to handle criteria it can't reproduce.**
*Location:* loop item 1; `uedge-reviewer.md:98,101,106` ("Verify this yourself by building and running the reference
cases", "Rebuild and rerun the test suite", "Tell the main session before any long or resource-heavy run").
*Problem and evidence:*
- A reviewer subagent returns exactly once. It cannot "tell the main session" and wait for an answer, so in unattended
  mode line 106 can't be met. The reviewer will either skip runs, which makes a weak review, or run anything, with
  unbounded time and possibly a different build flavour left in the author's venv (`validate` step 4 switches to an
  OpenMP build).
- Some AIUE-8 acceptance criteria can't be reproduced on the reviewer's machine:
  - T7/AIUE-54: characterisation "on Linux and macOS";
  - T11/AIUE-57: CI "red ... in 20/20 runs", with nothing pushed.
- With no rule, the reviewer either raises them as BLOCKER ("missing essential test"), and the loop burns 3 rounds and
  escalates for environment reasons, or approves on the author's word, which the reviewer is told never to do.

*Resolution:*
- The prompt states the run budget and environment: which venv(s) and build flavours the reviewer may use, whether it
  may rebuild, a wall-time cap, and the OpenMP toolchain.
- The reviewer marks criteria it cannot reproduce as "not independently verified (environment)", citing the author's
  evidence, as a separate category that is neither APPROVE-blocking by default nor accepted silently.
- The orchestrator records these on the ticket as items for the owner to check. Add the matching sentence to
  `uedge-reviewer.md` next to line 106.

**I1-M4 — Edits after APPROVE reach the commit without validation or review.**
*Location:* loop item 3 ("**APPROVE** → continue. Fix MINOR findings when cheap").
*Problem and evidence:*
- After an APPROVE the agent may change code, possibly in `ppp/` or the `pandf` tree, and commit it with no
  re-validation (the "Re-validate" in item 4 applies only to REVISE) and no review of the new diff. The reviewed and
  validated state then isn't the committed state, which is what the gate is meant to prevent.
- `create-prd` already closes this hole: Step 6 precondition, "If you edited the PRD after the approving round (beyond
  typo-level fixes), run one more round first."

*Resolution:*
- After APPROVE, apply only comment/doc-level MINOR fixes.
- Any code or test change triggers re-validation and one more review round, or is deferred and listed in the
  execution report.

**I1-M5 — "Every ticket" is not covered: `implement-fix` and Jira bug tickets bypass the gate.**
*Location:* `implement-fix/SKILL.md` (unchanged, no review step); `plan-feature/SKILL.md` Phase 0 row "Bug fix ... Prefer
`rca` → `implement-fix`"; `CLAUDE.md` row "Bug from a GitHub issue | `rca` → `implement-fix` → `commit`" (unchanged).
*Problem and evidence:*
- The user asked for adversarial checks "on every ticket". `end-to-end-feature` calls `plan-feature`, whose Phase 0
  tells an agent to prefer `rca` → `implement-fix` for bug fixes, and that path has no review gate.
- AIUE-8 has exactly such tickets: T10 `bugfix/v9-AIUE-56-omp-jacobian-fix` and T13 `bugfix/v9-AIUE-59-omp-rhs-fix`
  (`docs/specs/AIUE-8-investigate-non-deterministic-openmp-jacobian.md:236,280`). They touch `ppp/` and the `pandf`
  tree, the highest-risk code in the epic.
- The new `CLAUDE.md` row also adds reviewer gates to the manual `plan-feature → execute → … → commit` path, but none
  of those skills mentions them. Only `end-to-end-feature` enforces the gate.

*Resolution:*
- Add the same implementation gate (a reference to the loop in `end-to-end-feature`) to `implement-fix` before its
  commit, or state in `end-to-end-feature` Step 0 / `plan-feature` Phase 0 that Jira tickets, including `bugfix/`
  ones, stay in `end-to-end-feature`.
- Either make the manual path's gate visible in `commit` (a pre-commit check line: "ticket work: APPROVE report
  present, or WIP"), or reword the `CLAUDE.md` row so it doesn't claim a gate that no skill on that path enforces.

### MINOR

- **I1-m1 — Report location is relative.** Loop item 2 says the reviewer writes `docs/reviews/<KEY>-...`, and
  `uedge-reviewer.md:135` uses a relative path. A reviewer spawned from the orchestrator's cwd (in this run the main
  checkout, on `v9-develop`, which already shows a stray `?? tests/`) writes the report into the wrong tree. Item 7
  ("commit the review reports with the ticket") then misses it, and the hook blocks it on `v9-develop`. Require an
  absolute path inside the ticket worktree in the prompt, as this review's prompt did.
- **I1-m2 — Responses and rebuttals aren't saved.** Rounds 2+ pass "your response to each finding" only in the prompt.
  `create-prd` practice (`docs/reviews/AIUE-8-prd-round1-response.md`) and `uedge-implementer.md:91` save it as
  `...-round<N>-response.md`. Unattended, this is the owner's only record of why a MAJOR was rebutted rather than
  fixed. Ask for the response file and commit it with the reports.
- **I1-m3 — Finding-ID prefix collision.** `uedge-reviewer.md:116` defines `P1-M3` as "PRD round 1". The new `plan`
  stage also starts with P. Give it a distinct prefix (e.g. `L` or `PL`) and name the implementation prefix (`I`).
- **I1-m4 — Trigger and loop wording.**
  - `CLAUDE.md`'s trigger "`pandf*`/`ppp/`/`.v`/build" doesn't match Step 2b's "`pandf` tree, `ppp/`, Jacobian or
    preconditioner code, a `.v` file, or `setup.py`/`Makefile.Forthon`". Use one list.
  - Loop item 4's "Re-validate" means nothing at the plan stage.
  - The loop doesn't say what happens when an implementation review finds a plan-level design flaw (revise the plan
    and re-run the plan stage, or not).
- **I1-m5 — Stacking on parents still in review is unspecified.** The Escalation rule covers escalated parents only.
  The AIUE-8 run stacks AIUE-49/52/53 on AIUE-46 while AIUE-46 is in review. Say whether that's allowed, and that
  dependents must be rebased and re-validated if the parent changes during its review.
- **I1-m6 — `argument-hint` is still `[feature-description]`** although the description now accepts a ticket key, and
  the skill doesn't say how to load the acceptance criteria for a key. `docs/specs/` lives on the epic planning
  branch, not on ticket branches based on `v9-develop`.
- **I1-m7 — Housekeeping (not a defect of the change).** `docs/reviews/**` counts as an *artifact*, so `change_kind.py`
  blocks it on this AI-layer branch (checked: `violations('feature/v9-ai-x', ['docs/reviews/...'])` gives a
  violation). This report must stay uncommitted here, as instructed, or go on a ticket/planning branch.

### Scope

The change matches the request. The plan-stage gate goes beyond the literal "to finish up". It is justified (a wrong
design in `ppp/` costs more after execution) and conditional, so I don't raise it as a finding, but the owner should
know it adds time to each high-risk ticket.

## Status of previous findings

Round 1: none.

## What was checked and how

- Diff: `git diff origin/v9-develop...HEAD` (3 files, +90/−8). Confirmed that the branch base is `origin/v9-develop`
  (`3865c79`).
- Hooks, from the worktree:
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` → `OK`, exit 0 (only the
    "docs that cite files changed" advisory list, all citing `CLAUDE.md`).
  - `uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD` → 3 process files on an `ai` branch, `OK`,
    exit 0.
- Hook behaviour probed in Python with `change_kind.violations`:
  - `docs/reviews/*` and `.claude/plans/*` are artifacts: allowed on a ticket branch, blocked on an AI branch.
  - A `WIP:` subject trips nothing. `pre_tool_use.py` checks paths and the trailer only, not the subject.
- Consistency read in full: `create-prd`, `plan-feature`, `execute`, `validate`, `code-review`, `commit`,
  `implement-fix`, `spec`, `branching.md`, `physics-workflow.md`, `uedge-reviewer.md`, `uedge-implementer.md`, agent
  `tools` lists.
- Practice vs rule:
  - `git log` timestamps: `3b99e75` at 00:11:30; AIUE-46 `a61a145`/`483d57a` at 00:23, then review, then `f5fee63` at
    00:40.
  - `docs/specs/AIUE-8-progress.md` (delegation model: reviews run in the main session).
  - AIUE-8 ticket list (`docs/specs/AIUE-8-…md`): bugfix branches; Linux/macOS and CI criteria.
- Claude Code subagent nesting: fetched https://code.claude.com/docs/en/sub-agents. Nesting is allowed up to three
  layers by default. At the limit only a fork keeps `Agent`; nesting can be disabled with
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` or by omitting `Agent` from `tools`.
- No builds or test suites were run (not needed for a process-file review).
