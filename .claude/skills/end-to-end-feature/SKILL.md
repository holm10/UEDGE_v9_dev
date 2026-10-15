---
name: end-to-end-feature
description: Autonomously develops a complete feature or Jira ticket from priming through planning, execution, an adversarial uedge-reviewer gate, and commit by chaining the core PIV-loop skills. Use when you want a full hands-off feature build from a single description or ticket key.
argument-hint: [feature-description]
---

# End-to-End Feature Development

**Feature Description**: $ARGUMENTS

This skill chains the core PIV-loop skills for autonomous feature development, with an independent adversarial
review (`uedge-reviewer`) before anything is committed. Never run it on
`v9-develop`/`v9-main`, and never on an AI-layer branch (`feature/v9-ai-*`, `v9-agentic`). It runs on the
ticket's own branch and worktree, which `plan-feature` creates in its Phase 0b (`.claude/context/branching.md`).
After Step 1, `cd` into that worktree and stay there for every later step.

---

## Step 0: Route

If the request is **new physics** (new transport term, atomic/molecular process, BC, source, closure, neutral or
impurity model) and there is no approved spec in `docs/physics_specs/`, **stop**: tell the user it must go
through `uedge-physics` → `uedge-reviewer` → `uedge-implementer` (`.claude/context/physics-workflow.md`).
This skill handles refactors, numerics/parallel work, Python/build changes, and implementing approved specs.

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

**Required** when the plan touches the `pandf` tree, `ppp/`, Jacobian or preconditioner code, a `.v` file, or
`setup.py`/`Makefile.Forthon`. Optional otherwise. Review the plan before writing code, because a wrong design costs
more to fix after execution than before.

Run the review loop in **Adversarial review loop** below with `stage: plan`. The reviewer checks the plan against the
ticket's acceptance criteria and the code it cites. Revise the plan, not the code, until it is approved.

---

## Step 3: Execute - Implement the Feature

Implement the feature from the plan document.

Run the `execute` skill (`.claude/skills/execute/SKILL.md`) with the plan file path: `.claude/plans/[feature-name].md`.

Do not continue to Step 4 unless the `validate` gate is green (or the only moved cases are the ones the plan
documents for an intended physics/numerics change).

(Use the feature name from Step 2.)

---

## Step 3b: Adversarial implementation review (always required)

Nothing is committed until a fresh `uedge-reviewer` has returned **APPROVE** on the implementation. Run the loop in
**Adversarial review loop** below with `stage: implementation`. The reference is the approved physics spec if there
is one, otherwise the ticket's acceptance criteria and the plan.

After each fix, re-run the `validate` gate (or the plan's validation commands) before the next round, so that the
reviewer sees validated work.

---

## Adversarial review loop

The session that wrote the plan or the code can't review it independently.

1. Spawn a **fresh** `uedge-reviewer` agent for every round (Agent tool, `subagent_type: "uedge-reviewer"`). Never
   use a fork or an agent that saw the drafting. The reviewer can't see this conversation, so its prompt must be
   self-contained:
   - `stage` (`plan` or `implementation`), round number, ticket key (or feature name), branch and worktree path;
   - the reference: the spec path, or the ticket's acceptance criteria quoted verbatim (from `docs/specs/` or
     Jira), plus the plan path;
   - for `implementation`: the diff range (`git diff <base>...HEAD` plus uncommitted changes), the venv to use, and
     the validation output you got;
   - the binding decisions and constraints (`CLAUDE.md` hard rules, epic decisions), so the reviewer checks against
     them instead of re-opening them;
   - on rounds 2+: the previous report path and your response to each finding (fixed where, or rebutted why).
2. The reviewer writes `docs/reviews/<KEY>-<stage>-round<N>.md`. Wait for its completion notification, then read
   the report.
3. **APPROVE** → continue. Fix MINOR findings when cheap; list the rest in the execution report.
4. **REVISE** → fix every BLOCKER and MAJOR, or rebut it with evidence. Re-validate. Start round N+1 with a fresh
   reviewer.
5. **REJECT** → stop and escalate (below).
6. **Round 3 without APPROVE** → stop and escalate.
7. Commit the review reports with the ticket (`docs/reviews/` is an artifact path on the ticket branch).

**Escalation.** When a person is available, show them the open BLOCKER/MAJOR findings and ask how to proceed. When
running **unattended** (the user said they can't give feedback): don't commit the unapproved work as done. Commit
it as work in progress (subject starts with `WIP:`), record the open findings in the execution report and on the
ticket (Jira comment, if a key is known), leave the ticket open, and move on only to tickets that don't depend on it.
Do the same for any decision the PRD or ticket reserves for the owner: prepare the evidence and the options, and stop
at the decision.

---

## Step 4: Commit - Save Changes

Create a git commit for all changes.

Run the `commit` skill (`.claude/skills/commit/SKILL.md`).

---

## Step 5: Learn - Feed process lessons back

Run the `execution-report` skill and then the `system-review` skill on the plan and the report. `system-review`
files each recommendation as an `ai-layer` issue. Nothing in `.claude/skills`, `.claude/agents` or
`.claude/hooks` changes on this branch.

---

## Final Summary

After completing all steps, provide:

### Feature Implementation Complete

**Original Request**: $ARGUMENTS

**Feature Name**: [feature-name from planning step]

**Steps Executed:**
1. ✅ Prime - Codebase context loaded
2. ✅ Planning - Plan created at `.claude/plans/[feature-name].md`
3. ✅ Execute - Feature implemented and validated
   ✅ Adversarial review - plan: [verdict, rounds or "not required"]; implementation: [verdict, rounds]
4. ✅ Commit - Changes committed to git
5. ✅ Learn - Execution report + system review; ai-layer issues filed: [keys]

**Outputs:**
- Plan document: `.claude/plans/[feature-name].md`
- Files created/modified: [list]
- Validate result: [report block]
- Review reports: `docs/reviews/<KEY>-<stage>-round<N>.md`, findings fixed / rebutted / deferred
- Default results: [unchanged / changed as documented]
- Commit hash: [hash]

**Next Steps:**
- Push to remote: `git push`
- Create pull request (if applicable)
- Continue with next feature
