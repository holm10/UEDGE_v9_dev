---
name: system-review
description: Performs a meta-level review of how well an implementation followed its plan, classifying divergences and recommending AI-Layer improvements. Use after an execution report exists to find bugs in the process, not the code.
argument-hint: [plan-file, default .claude/work/<KEY>/plan.md] [execution-report-file, default .claude/work/<KEY>/execution-report.md]
---

# System Review

Perform a meta-level analysis of how well the implementation followed the plan and identify process improvements.

## Purpose

**System review is NOT code review.** You're not looking for bugs in the code - you're looking for bugs in the process.

**Your job:**

- Analyze plan adherence and divergence patterns
- Identify which divergences were justified vs problematic
- Surface process improvements that prevent future issues
- Suggest updates to AI-Layer assets (CLAUDE.md, plan templates, skills)

**Philosophy:**

- Good divergence reveals plan limitations → improve planning
- Bad divergence reveals unclear requirements → improve communication
- Repeated issues reveal missing automation → create skills

## Context & Inputs

You will analyze four key artifacts:

**Plan Skill:**
Read this to understand the planning process and what instructions guide plan creation.
`.claude/skills/plan-feature/SKILL.md`

**Generated Plan:**
Read this to understand what the agent was SUPPOSED to do.
Plan file: $1

**Execute Skill:**
Read this to understand the execution process and what instructions guide implementation.
`.claude/skills/execute/SKILL.md`

**Execution Report:**
Read this to understand what the agent ACTUALLY did and why.
Execution report: $2

## Analysis Workflow

### Step 1: Understand the Planned Approach

Read the generated plan ($1) and extract:

- What features were planned?
- What architecture was specified?
- What validation steps were defined?
- What patterns were referenced?

### Step 2: Understand the Actual Implementation

Read the execution report ($2) and extract:

- What was implemented?
- What diverged from the plan?
- What challenges were encountered?
- What was skipped and why?

### Step 3: Classify Each Divergence

For each divergence identified in the execution report, classify as:

**Good Divergence ✅** (Justified):

- Plan assumed something that didn't exist in the codebase
- Better pattern discovered during implementation
- Performance optimization needed
- Security issue discovered that required different approach

**Bad Divergence ❌** (Problematic):

- Ignored explicit constraints in plan
- Created new architecture instead of following existing patterns
- Took shortcuts that introduce tech debt
- Misunderstood requirements

### Step 4: Trace Root Causes

For each problematic divergence, identify the root cause:

- Was the plan unclear, where, why?
- Was context missing, where, why?
- Was validation missing, where, why?
- Was manual step repeated, where, why?

### Step 5: Generate Process Improvements

Based on patterns across divergences, suggest the changes below. They are **process changes**: they're applied on a
`feature/v9-ai-<slug>` branch in their own PR, never on the ticket branch that was reviewed
(`.claude/context/branching.md`). For each one, say whether it's a process change (AI-layer branch) or a
code-facts correction (allowed on the ticket branch with the trailer `AI-layer: code-facts`).

- **CLAUDE.md updates:** Universal patterns or anti-patterns to document
- **Plan skill updates:** Instructions that need clarification or missing steps
- **New skills:** Manual processes that should be automated
- **Validation additions:** Checks that would catch issues earlier

## Output Format

Save your analysis to: `.claude/work/<KEY>/system-review.md` (`<slug>` without a ticket). It is a working document:
gitignored, never committed. Its lasting content is the filed `ai-layer` issues and the ticket page entry below.

### Report Structure:

#### Meta Information

- Plan reviewed: [path to $1]
- Execution report: [path to $2]
- Date: [current date]

#### Overall Alignment Score: \_\_/10

Scoring guide:

- 10: Perfect adherence, all divergences justified
- 7-9: Minor justified divergences
- 4-6: Mix of justified and problematic divergences
- 1-3: Major problematic divergences

#### Divergence Analysis

For each divergence from the execution report:

```yaml
divergence: [what changed]
planned: [what plan specified]
actual: [what was implemented]
reason: [agent's stated reason from report]
classification: good ✅ | bad ❌
justified: yes/no
root_cause: [unclear plan | missing context | etc]
```

#### Pattern Compliance

Assess adherence to documented patterns:

- [ ] Followed codebase architecture
- [ ] Used documented patterns (from CLAUDE.md)
- [ ] Applied testing patterns correctly
- [ ] Met validation requirements

#### System Improvement Actions

Based on analysis, recommend specific actions:

**Update CLAUDE.md:**

- [ ] Document [pattern X] discovered during implementation
- [ ] Add anti-pattern warning for [Y]
- [ ] Clarify [technology constraint Z]

**Update Plan Skill ($1):**

- [ ] Add instruction for [missing step]
- [ ] Clarify [ambiguous instruction]
- [ ] Add validation requirement for [X]

**Create New Skill:**

- [ ] A new skill for [manual process repeated 3+ times]

**Update Execute Skill:**

- [ ] Add [validation step] to execution checklist

#### File the actions (required)

Don't apply any of these actions yourself. Each one is a **process change** and goes through its own
`feature/v9-ai-<slug>` branch and PR (`.claude/context/branching.md`). Queue them so they aren't lost:

1. If the Atlassian MCP server is connected (`mcp__atlassian__getAccessibleAtlassianResources`), for each action:
   - Search for duplicates: `project = AIUE AND labels = ai-layer AND statusCategory != Done AND summary ~ "<2-4 key words>"`.
     If an open issue already covers it, add a comment with this review's evidence instead of a new issue.
   - Otherwise create a `Task` in project `AIUE` with label `ai-layer`, summary `AI layer: <action>`, and a
     description holding the evidence (the divergence, plan and report paths), the target file(s), and the proposed
     change.
2. If Jira isn't available, append the actions to `.claude/work/<KEY>/ai-layer-backlog.md` (local, never committed)
   with date, feature, target file and proposed change, and queue them on the ticket page (below), which keeps them
   until Atlassian is back; file them as issues at the next session that has Jira. Without a ticket record, give
   them to the user in the output: the local file is lost with the worktree.
3. Code-facts corrections (a context module that is simply wrong about the code) are the exception: fix them on the
   current branch with the trailer `AI-layer: code-facts`, and list them here as done.

List the filed issue keys (or backlog entries) in the report. For a Jira ticket, record them on the ticket page:
`ticket-page <KEY> log "Findings and decisions" "Agent: system review <score>/10; ai-layer issues <keys> (or not
filed yet: <one line per action>)" --flush`.

#### Key Learnings

**What worked well:**

- [specific things that went smoothly]

**What needs improvement:**

- [specific process gaps identified]

**For next implementation:**

- [concrete improvements to try]

## Important

- **Be specific:** Don't say "plan was unclear" - say "plan didn't specify which auth pattern to use"
- **Focus on patterns:** One-off issues aren't actionable. Look for repeated problems.
- **Action-oriented:** Every finding should have a concrete asset update suggestion
- **Suggest improvements:** Don't just analyze - actually suggest the text to add to CLAUDE.md or skills
