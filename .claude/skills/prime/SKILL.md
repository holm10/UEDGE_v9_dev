---
name: prime
description: Primes the agent with UEDGE project context — CLAUDE.md, the relevant .claude/context modules, current branch state, and (optionally) Jira/Confluence task context. Use at the start of a session or before planning or implementing.
argument-hint: [task description | jira-issue-keys] [confluence-page-ids]
---

# Prime: Load UEDGE Context

## Step 0: External task context (optional)

Only if Jira keys (e.g. `UEDGE-12`, comma-separated) or numeric Confluence page ids are passed **and** the
Atlassian MCP server is connected:

1. `mcp__atlassian__getAccessibleAtlassianResources` → `cloudId`.
2. Each Jira key: `mcp__atlassian__getJiraIssue` (`responseContentFormat: "markdown"`).
3. Each page id: `mcp__atlassian__getConfluencePage` (`contentFormat: "markdown"`).

If a Jira issue has a ticket page (a `Ticket page:` comment, or `Plan page:` on older tickets, with its Confluence
page id), read the page too: its Ticket section is the scope as filed by `spec`, and its log sections record the
ticket's progress, validation, reviews and decisions so far (`ticket-page` skill). A ticket under an epic without a
PRD page keeps the same record as `PIV record` Jira comments.
Summarise the goal and acceptance criteria. If the server is not connected, say so and continue.
If the argument is a plain task description, use it as the task context instead.

## Step 1: Global rules

Read `CLAUDE.md` in full. It is the source of truth for naming, core patterns, build/validation commands,
hard rules, and gotchas — do not re-derive these from the code.

## Step 2: Task-relevant context modules

From the on-demand table in `CLAUDE.md`, load the `.claude/context/*.md` modules that match the task (always
`architecture.md` if the task is broad or unclear). Then read the source files the task points to — for
physics, the relevant `bbb/pandf_*.m` routine and its `.v` variables; for Python, the `src/uedge/` module.

If the task is new physics, note that it must go through the `uedge-physics` → `uedge-reviewer` →
`uedge-implementer` pipeline (`.claude/context/physics-workflow.md`), and check `docs/physics_specs/` for an
existing spec.

## Step 3: Current state

```bash
git branch --show-current
git status --short
git log --oneline -10
git log --oneline v9-develop..HEAD
```

Also list open work products: physics specs (`docs/physics_specs/`, committed) and the local working folder
(`ls .claude/work/`: plans, reviews, RCAs and other working documents in progress; gitignored, so `git status` doesn't
show them). For a ticket worktree, check the `ticket-page` outbox (`uv run
.claude/skills/ticket-page/ticket_page.py queue --repo . --key <KEY> --list`): queued entries are not on the page yet
and must be flushed before the worktree is removed.

Classify the branch (`.claude/context/branching.md`): protected, AI layer, or ticket. List active worktrees
(`git worktree list`). Run `uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD` and report any
violations (the wrong kind of change on this branch).

## Output

Keep it short and scannable:

- **Task context** — goal, acceptance criteria, source (Jira/Confluence/description), or "none given".
- **Relevant area** — packages, files, routines, `.v` groups, with `file:line`.
- **Rules that bite here** — the specific hard rules / gotchas / context-module points that apply
  (e.g. threadprivate, refactor-vs-physics defaults, MPPL hazards).
- **Branch state** — branch and its kind (protected / AI layer / ticket), ahead of `v9-develop` by N, uncommitted
  changes, worktrees, open specs and working documents, queued ticket-page entries, branch-policy violations. If the
  task doesn't match the branch kind

  (product work on an AI-layer branch or the reverse), say which branch and worktree to switch to.
- **Suggested next step** — `plan-feature`, the physics pipeline, `rca`, or a direct small change.
