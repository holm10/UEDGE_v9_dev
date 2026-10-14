---
name: end-to-end-feature
description: Autonomously develops a complete feature from priming through planning, execution, and commit by chaining the four core PIV-loop skills. Use when you want a full hands-off feature build from a single description.
argument-hint: [feature-description]
---

# End-to-End Feature Development

**Feature Description**: $ARGUMENTS

This skill chains the 4 core PIV-loop skills for autonomous feature development. Never run it on
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

## Step 3: Execute - Implement the Feature

Implement the feature from the plan document.

Run the `execute` skill (`.claude/skills/execute/SKILL.md`) with the plan file path: `.claude/plans/[feature-name].md`.

Do not continue to Step 4 unless the `validate` gate is green (or the only moved cases are the ones the plan
documents for an intended physics/numerics change).

(Use the feature name from Step 2.)

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

After completing all 5 steps, provide:

### Feature Implementation Complete

**Original Request**: $ARGUMENTS

**Feature Name**: [feature-name from planning step]

**Steps Executed:**
1. ✅ Prime - Codebase context loaded
2. ✅ Planning - Plan created at `.claude/plans/[feature-name].md`
3. ✅ Execute - Feature implemented and validated
4. ✅ Commit - Changes committed to git
5. ✅ Learn - Execution report + system review; ai-layer issues filed: [keys]

**Outputs:**
- Plan document: `.claude/plans/[feature-name].md`
- Files created/modified: [list]
- Validate result: [report block]
- Default results: [unchanged / changed as documented]
- Commit hash: [hash]

**Next Steps:**
- Push to remote: `git push`
- Create pull request (if applicable)
- Continue with next feature
