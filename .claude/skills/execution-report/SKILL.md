---
name: execution-report
description: Generates a structured implementation report reflecting on a just-completed feature — what was done, divergences, challenges. Use right after finishing an implementation, as the input to a system review.
---

# Execution Report

Review and deeply analyze the implementation you just completed.

## Context

You have just finished implementing a feature. Before moving on, reflect on:

- What you implemented
- How it aligns with the plan
- What challenges you encountered
- What diverged and why

## Generate Report

Save to: `.claude/work/<KEY>/execution-report.md` in the ticket's worktree (`<slug>` without a ticket). It is a
working document: gitignored, never committed (`.claude/context/branching.md`). Keep it **≤100 lines** (an S ticket needs a
fraction of that): divergences and lessons, not a retelling of the plan; omit sections with nothing to say
(`.claude/context/process-tiers.md` → Report caps).

For a Jira ticket, put its lasting content on the ticket page once it is written: `ticket-page <KEY> log "Findings and
decisions" "Agent: execution report: <each divergence in a line: planned / actual / why>; skipped: <items or none>;
deferred MINORs: <ids or none>; recommendations: <one line each>"`. It stays queued: the `system-review` that follows
flushes it with the commit entry (`ticket-page` → "When to flush"); run on its own, add `--flush`. `--no-tracker`
skips it. Without a ticket record the report stays local: say so, and put anything a
later reader needs in the PR description.

### Meta Information

- Plan file: [path to the plan's working copy, and its published sha256 on the ticket page if any]
- Files added: [list with paths]
- Files modified: [list with paths]
- Lines changed: +X -Y

### Validation Results

- Build (serial): ✓/✗ [first error / new warnings in touched files]
- Smoke import: ✓/✗
- Regression suites: ✓/⚠️/✗ [suites run; passed/failed; cases that moved and whether that was documented]
- OpenMP check: ✓/✗/skipped [why skipped]

### What Went Well

List specific things that worked smoothly:

- [concrete examples]

### Challenges Encountered

List specific difficulties:

- [what was difficult and why]

### Divergences from Plan

For each divergence, document:

**[Divergence Title]**

- Planned: [what the plan specified]
- Actual: [what was implemented instead]
- Reason: [why this divergence occurred]
- Type: [Better approach found | Plan assumption wrong | Security concern | Performance issue | Other]

### Skipped Items

List anything from the plan that was not implemented:

- [what was skipped]
- Reason: [why it was skipped]

### Recommendations

Based on this implementation, what should change for next time?

- Plan skill improvements: [suggestions]
- Execute skill improvements: [suggestions]
- CLAUDE.md additions: [suggestions]
