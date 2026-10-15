---
name: end-to-end-feature
description: Autonomously develops a complete feature or Jira ticket from priming through planning, execution, an adversarial uedge-reviewer gate, and commit by chaining the core PIV-loop skills. Use when you want a full hands-off feature build from a single description or ticket key.
argument-hint: [ticket-key or feature-description]
---

# End-to-End Feature Development

**Feature Description**: $ARGUMENTS

This skill chains the core PIV-loop skills for autonomous feature development, with an independent adversarial
review (`uedge-reviewer`) that a ticket must pass before it counts as done. Never run it on
`v9-develop`/`v9-main`, and never on an AI-layer branch (`feature/v9-ai-*`, `v9-agentic`). It runs on the
ticket's own branch and worktree, which `plan-feature` creates in its Phase 0b (`.claude/context/branching.md`).
After Step 1, `cd` into that worktree and stay there for every later step.

**Ticket input.** For a Jira key, take the scope and acceptance criteria from the Jira issue, or from the epic's
`docs/specs/<epic-slug>.md` (it lives on the epic's planning branch: `git show feature/v9-<EPIC>-planning:docs/specs/<file>`).
The acceptance criteria are what the reviewer checks against, so quote them verbatim.

**Stacking.** A ticket may start on a parent ticket's branch while the parent is still in review. When the parent
changes (review fixes, rebase), rebase the child onto it and re-run the child's validation before its review.

---

## Step 0: Route

If the request is **new physics** (new transport term, atomic/molecular process, BC, source, closure, neutral or
impurity model) and there is no approved spec in `docs/physics_specs/`, **stop**: tell the user it must go
through `uedge-physics` → `uedge-reviewer` → `uedge-implementer` (`.claude/context/physics-workflow.md`).
This skill handles refactors, numerics/parallel work, Python/build changes, and implementing approved specs.
Bug fixes from an RCA follow `implement-fix`, which uses the same review loop.

---

## Step 1: Prime - Load Codebase Context

Execute the priming workflow to understand the codebase.

Run the `prime` skill (`.claude/skills/prime/SKILL.md`).

---

## Step 2: Planning - Create Implementation Plan

Create a detailed implementation plan for the feature.

Run the `plan-feature` skill (`.claude/skills/plan-feature/SKILL.md`) with the feature description: **$ARGUMENTS**.

**IMPORTANT**: Note the feature name (and plan file path) that the planning step creates. You'll need it for the next step.

---

## Step 2b: Adversarial plan review (required for high-risk plans)

**Required** when the plan touches the `pandf` tree (`bbb/pandf*.m` and what they call), `ppp/`, Jacobian or
preconditioner code, a `.v` file, or the build (`setup.py`, `Makefile.Forthon`). Optional otherwise. A wrong design
costs more to fix after execution than before.

Run the **Adversarial review loop** below with `stage: plan`. The reviewer checks the plan against the ticket's
acceptance criteria and the code it cites. Revise the plan, not the code, until it is approved. Nothing is built
or run at this stage, so there is no re-validation between rounds.

---

## Step 3: Execute - Implement the Feature

Implement the feature from the plan document.

Run the `execute` skill (`.claude/skills/execute/SKILL.md`) with the plan file path: `.claude/plans/[feature-name].md`.

Do not continue unless the `validate` gate is green (or the only moved cases are the ones the plan documents for an
intended physics/numerics change).

(Use the feature name from Step 2.)

---

## Step 3b: Adversarial implementation review (always required)

Run the **Adversarial review loop** below with `stage: implementation`, on the ticket's whole diff against its base
(committed and uncommitted). The reference is the approved physics spec if there is one, otherwise the ticket's
acceptance criteria and the plan.

**Committing and "done".** You may commit as you go (the code, then the code-facts commit, as `execute` and `commit`
describe), and the reviewer reviews `<base>...HEAD`. What makes a ticket **done** is a fresh reviewer's APPROVE on
the final diff, not the existence of a commit. Until then, don't report the ticket as complete, don't move its Jira
issue past In Progress, and don't open a PR for it.

---

## Adversarial review loop

Used by Step 2b and Step 3b here, and by `plan-feature`, `execute` and `implement-fix`. Inside this skill, Steps 2b
and 3b **are** those skills' review gates: run each loop once, not again from `plan-feature` or `execute`, so the
3-round cap counts one loop.

**Who reviews.** Never review your own plan or code, and never use a fork or an agent that saw the drafting. Spawn a
**fresh** `uedge-reviewer` agent for every round (Agent tool, `subagent_type: "uedge-reviewer"`). If you can't spawn
one (no Agent tool, nesting limit reached, running as a subagent without it), **stop after validation** and return
to your caller: the work state, the validation output, and the ready-to-use reviewer prompt below. The caller then
runs the loop. Whoever runs the loop also decides who applies the fixes: itself, or the implementing agent (resumed
with the findings). The one applying fixes re-validates before the next round. After a hand-off, the caller also
owns the rest of this skill for that ticket: Step 4 (commit the reports), Step 5 (Learn) and the Final Summary.

1. **Prompt.** The reviewer can't see this conversation, so its prompt must be self-contained:
   - `stage` (`plan` or `implementation`), round number, ticket key (or feature name), branch and worktree path;
   - the reference: the spec path, or the ticket's acceptance criteria quoted verbatim, plus the plan path;
   - for `implementation`: the diff range (`git diff <base>...HEAD` plus uncommitted changes) and the validation
     output you got;
   - the **run budget**: which builds/venvs it may use (never to be reinstalled), what it may build in a scratch
     worktree, and a time limit; and which acceptance criteria can't be reproduced in its environment (another OS,
     CI, many-run statistics), so it records those as *not independently verified* instead of failing or trusting
     them;
   - the binding decisions and constraints (`CLAUDE.md` hard rules, epic decisions), so the reviewer checks against
     them instead of re-opening them;
   - the **absolute** report path: `<worktree>/docs/reviews/<KEY>-<stage>-round<N>.md` (a relative path can land in
     another checkout);
   - on rounds 2+: the previous report path and the response file (step 4).
2. Wait for the completion notification, then read the report.
3. **APPROVE** → done with this stage. MINOR findings may be fixed: typo-level and documentation-only fixes need
   only the validation they touch; any other change after APPROVE (code, tests, data, behaviour) needs a new round
   with a fresh reviewer on the changed diff. List deferred MINORs in the execution report.
4. **REVISE** → fix every BLOCKER and MAJOR, or rebut it with evidence. Write the response to
   `docs/reviews/<KEY>-<stage>-round<N>-response.md` (finding → fixed where / rebutted why). Re-validate (implementation
   stage). Start round N+1 with a fresh reviewer.
   An implementation finding that shows the **plan** is wrong: revise the plan first, and for a high-risk plan
   (Step 2b list) re-run a plan round before changing the code.
5. **REJECT** → stop and escalate (below).
6. **Round 3 without APPROVE** → stop and escalate.
7. Commit the review reports and responses with the ticket (`docs/reviews/` is an artifact path on the ticket
   branch). Criteria the reviewer marked *not independently verified* go into the PR description and the ticket, for
   the owner.

**Escalation.** When a person is available, show them the open BLOCKER/MAJOR findings and ask how to proceed. When
running **unattended** (the user said they can't give feedback): leave the commits on the ticket branch as they are,
record the open findings in the execution report and on the ticket (Jira comment, if a key is known), keep the ticket
In Progress, and move on only to tickets that don't depend on it. Do the same for any decision the PRD or ticket
reserves for the owner: prepare the evidence and the options, and stop at the decision.

---

## Step 4: Commit - Save Changes

Commit what is not yet committed (the review reports and responses, any last fixes) with the `commit` skill
(`.claude/skills/commit/SKILL.md`).

---

## Step 5: Learn - Feed process lessons back

Run the `execution-report` skill and then the `system-review` skill on the plan and the report. `system-review`
files each recommendation as an `ai-layer` issue. Nothing in `.claude/skills`, `.claude/agents` or
`.claude/hooks` changes on this branch.

---

## Final Summary

After completing all steps, provide:

### Feature Implementation Complete | Ticket Escalated

**Original Request**: $ARGUMENTS

**Feature Name**: [feature-name from planning step]

**Steps Executed:**
1. ✅ Prime - Codebase context loaded
2. ✅ Planning - Plan created at `.claude/plans/[feature-name].md`
3. ✅ Execute - Feature implemented and validated
   ✅/❌ Adversarial review - plan: [verdict, rounds or "not required"]; implementation: [verdict, rounds]
4. ✅ Commit - Changes committed to git
5. ✅ Learn - Execution report + system review; ai-layer issues filed: [keys]

**Outputs:**
- Plan document: `.claude/plans/[feature-name].md`
- Files created/modified: [list]
- Validate result: [report block]
- Review reports: `docs/reviews/<KEY>-<stage>-round<N>.md`, findings fixed / rebutted / deferred
- Not independently verified (for the owner): [criteria, or "none"]
- Default results: [unchanged / changed as documented]
- Commit hash: [hash]

**Next Steps:**
- Approved: push and open a PR when the user asks for it (`commit`/branching rules apply).
- Escalated: the open BLOCKER/MAJOR findings or the owner decision needed, and which tickets are blocked by it.
- Continue with the next independent ticket.
