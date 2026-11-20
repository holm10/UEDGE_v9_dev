---
name: prime
description: Primes the agent with UEDGE project context — CLAUDE.md, the relevant .claude/context modules, current branch state, and (optionally) a tracker ticket's context (issue and record). Use at the start of a session or before planning or implementing.
argument-hint: [task description | tracker keys T<N>]
---

# Prime: Load UEDGE Context

## Step 0: External task context (optional)

If `.claude/work/<KEY>/handoff.md` exists in the worktree, read it first: it is the state the last agent left (what
works, open items, how to verify), the starting point for a fresh fixer or session.

Only if tracker keys `T<N>` (comma-separated) are passed, for each one:

1. `gh issue view <N> -R <owner>/<repo> --json number,title,body,state,issueType,labels,comments`, with owner and
   repo from `.claude/tracker.toml` (the issue: title, body, type, and the comments that carry handovers and owner
   decisions). Without `--json`, `--comments` prints only the comments when stdout is not a terminal, and nothing for
   an issue without comments (T35). The parent epic is the record's Epic row, or `gh api
   repos/<owner>/<repo>/issues/<N>/parent`.
2. In the tracker checkout (`<parent of the main checkout>/<repo>`; `ticket-page` → Configuration), read
   `docs/*/T<N>-*/record.md` and the `plan.md` (or `rca.md`) next to it. The record's `## Ticket` section is the scope
   as filed by `spec`; its log sections record the ticket's progress, validation, reviews and decisions so far
   (`ticket-page` skill).

Summarise the goal and acceptance criteria. If `gh` or the checkout is missing, say so and continue.
Jira keys (`AIUE-<n>`) and Confluence page ids belong to the read-only archive in the tracker checkout:
`docs/archive/jira/AIUE-<n>.md`, and `docs/archive/confluence/` (find the page id in its `index.md`). Read them only when
the task cites them, and say that they are the archive, not the ticket's record.
If the argument is a plain task description, use it as the task context instead.

## Step 1: Global rules

Read `CLAUDE.md` in full. It is the source of truth for naming, core patterns, build/validation commands,
hard rules, and gotchas — do not re-derive these from the code.

## Step 2: Task-relevant context modules

Always load `.claude/context/uedge-gotchas.md` (UEDGE's by-design traps; short, and a missed trap costs more than
reading it). From the on-demand table in `CLAUDE.md`, also load the `.claude/context/*.md` modules that match the task
(always `architecture.md` if the task is broad or unclear). Then read the source files the task points to — for
physics, the relevant `pandf` routine (`architecture.md` → `bbb/` layout) and its `.v` variables; for Python, the `src/uedge/` module.

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
show them). For a ticket worktree, check the tracker checkout (`git status -sb` run in it; a worktree-isolated
session that refuses `git -C <other checkout>` runs it as `cd <tracker checkout> && git status -sb` in its own
command). "ahead" means record commits not yet pushed, which the next `ticket-page` call pushes. Uncommitted
changes to tracked files, or a branch other than the default one, block every `ticket-page` write (exit 2): report
them. The handoff note was read in Step 0.

Classify the branch (`.claude/context/branching.md`): protected, AI layer, or ticket. List active worktrees
(`git worktree list`). Run `uv run .claude/hooks/change_kind.py --range origin/v9-develop...HEAD` and report any
violations (the wrong kind of change on this branch).

## Output

Keep it short and scannable:

- **Task context** — goal, acceptance criteria, source (tracker issue / record / description), or "none given".
- **Relevant area** — packages, files, routines, `.v` groups, with `file:line`.
- **Rules that bite here** — the specific hard rules / gotchas / context-module points that apply
  (e.g. threadprivate, refactor-vs-physics defaults, source-form hazards), including each `uedge-gotchas.md` trap the task
  can hit.
- **Branch state** — branch and its kind (protected / AI layer / ticket), ahead of `v9-develop` by N, uncommitted
  changes, worktrees, open specs and working documents, unpushed tracker commits, branch-policy violations. If the
  task doesn't match the branch kind
  (product work on an AI-layer branch or the reverse), say which branch and worktree to switch to.
- **Suggested next step** — `plan-feature`, the physics pipeline, `rca`, or a direct small change.
