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
- Repeated issues reveal missing automation → but prefer a sentence in an existing skill over a new skill, hook or
  code path (`.claude/context/process-tiers.md` → Simplicity budget); recommend code only for a guarantee a model
  can't keep by hand

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
gitignored, never committed. Its lasting content is the filed `ai-layer` issues and the record entry below.

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
`feature/v9-ai-<slug>` branch and PR (`.claude/context/branching.md`). File them in the tracker so they aren't lost
(owner, repo and Project number from `.claude/tracker.toml`; never hard-code them):

1. If `gh` is available and authenticated, find the parent issue "AI-layer improvements" by its title
   (`.claude/context/branching.md` → Guard rails):
   `gh issue list -R <owner>/<repo> --label ai-layer --state open --search "AI-layer improvements in:title" --json
   number,title --jq '[.[] | select(.title == "AI-layer improvements")]'`. The search matches words, so keep the
   exact title only; anything but exactly one match is a stop: file nothing and use the fallback below.
   Then, for each action:
   - Search for duplicates: `gh issue list -R <owner>/<repo> --label ai-layer --state open --search "<2-4 key words>"
     --json number,title`. If an open issue already covers it, add a comment with this review's evidence (`gh issue
     comment <n> -R <owner>/<repo> --body-file <file>`) instead of a new issue.
   - Otherwise write the body to a file in the working folder (the evidence: the divergence, plan and report paths;
     the target file(s); the proposed change) and create a sub-issue of the parent:
     `gh issue create -R <owner>/<repo> --type Task --label ai-layer --parent <parent n> --title "AI layer: <action>"
     --body-file <file>` (`--type Bug` for a defect in a skill, hook or helper). It prints the issue URL.
   - Add it to the Project with Tier S: `gh project item-add <project> --owner <owner> --url <issue URL> --format json
     --jq .id` gives the item id; then `gh project item-edit --id <item id> --project-id <project node id> --field-id
     <Tier field id> --single-select-option-id <S option id>`, with the ids from `gh project view <project> --owner
     <owner> --format json --jq .id` and `gh project field-list <project> --owner <owner> --format json`.
2. Without `gh` (or if a call fails), append the actions to `.claude/work/<KEY>/ai-layer-backlog.md` (local, never
   committed) with date, feature, target file and proposed change, and put them in the ticket's record (the Findings
   and decisions entry below), which keeps them; file them as issues at the next session that has `gh`. Without a
   ticket record, give them to the user in the output: the local file is lost with the worktree.
3. Code-facts corrections (a context module that is simply wrong about the code) are the exception: fix them on the
   current branch with the trailer `AI-layer: code-facts`, and list them here as done.

List the filed issue numbers (or backlog entries) in the report. For a tracker ticket `T<N>`, record them in the
ticket's record: `ticket-page T<N> log "Findings and decisions" "Agent: system review <score>/10; ai-layer issues
#<n>, … (or not filed yet: <one line per action>)"` (`uv run .claude/skills/ticket-page/ticket_page.py --caller
system-review log T<N> "Findings and decisions" "…"` from the worktree; one commit in the tracker checkout).

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
