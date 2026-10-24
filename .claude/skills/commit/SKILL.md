---
name: commit
description: Creates a git commit for the current work with an explicit file list and a repo-style imperative message (optional CI tags). Use when work is complete and ready to be committed.
---

# Commit

## Process

1. Inspect the work: `git status`, `git diff HEAD --stat`, `git diff HEAD`.
2. Check the branch and the change class (`.claude/context/branching.md`). After staging (step 3), run
   `uv run .claude/hooks/change_kind.py --staged` and resolve every VIOLATION before committing:
   - protected branch (`main`, `develop`, `v9-main`, `v9-develop`) → stop and create the ticket branch;
   - a working document on any branch (anything in `.claude/work/`, a plan, review report or response, validation
     record, RCA, execution or system review, PRD copy, breakdown, progress log or close-out record, also under the
     old paths `.claude/plans/`, `docs/{prds,specs,reviews,rca}/`) → unstage it. It is never committed: its lasting
     content belongs on the ticket page (`ticket-page`) or the epic's Confluence pages. Physics specs
     (`docs/physics_specs/`) are product files and are committed with the physics change;
   - product files on an AI-layer branch (`feature/v9-ai-*`, `v9-agentic`) → unstage them and commit them on their
     ticket branch;
   - AI-layer process files on a ticket branch → if they only keep `CLAUDE.md`/`.claude/context/` accurate about
     code this branch changes, add the trailer `AI-layer: code-facts`. Otherwise unstage them and move them to a
     `feature/v9-ai-<slug>` branch. `--staged` can't see the message, so for `CLAUDE.md`/`.claude/context/` it prints
     a `NOTE:` instead of a VIOLATION; add `--message "<the message>"` to check the trailer before committing.
   The PreToolUse hook runs the same check on `git commit` and blocks violations, so fix them here instead of
   working around the block. **Never** add the trailer to get a process change through.
3. **Stage explicitly** by path: only files that belong to this change. Never `git add -A` / `git add .`.
   Do not stage `logs/`, build output, generated `.F` files, scratch scripts, large data files unless asked, or
   working documents (`.claude/work/` and the old working paths are gitignored; never `git add -f` them).
   New `.f`/`.c` sources need `git add -f` (gitignored patterns).
4. Write the message in the repo's style:
   - Subject: imperative, capitalised, no tag prefix, ≤ 72 chars — "Fixes …", "Adds …", "Updates …",
     "Simplifies …" (see `git log --oneline`).
   - Body (if needed): what changed and why, wrapped at ~72 chars. For physics changes, state whether default
     results change and which reference cases move.
   - Optional CI tags on their own line after `#`: `#@notest`, `#@nowheel` (only when the user asks to skip those
     CI stages). Both are inert at present and there is no BASIS CI, so no `#@nobasis` (`testing.md` → CI facts).
   - Trailer `AI-layer: code-facts` (before the attribution line) only in the case described in step 2.
   - End with the attribution line from the session instructions, if one is given.

```
Fixes X-point padding in OMP RHS chunks

Core-boundary cells next to the X-point cut were skipped when
Nchunks > Nthreads.
```

5. Commit with a heredoc, then show `git log -1 --stat`.

## Output

### What Changed
3–6 sentences: the problem solved and the key files touched.

### AI Layer Changes
Only if files under `.claude/` or `CLAUDE.md` changed: one line per file on what evolved and why, and whether it
was a process change (AI-layer branch) or a code-facts update (ticket branch, trailer).

## The pull request description (when a PR is opened)

This skill doesn't open PRs, but the description that goes with this branch's PR carries what the working documents
can't keep:
- with a ticket record: a link to the ticket page, the criteria not independently verified, and which default results
  changed (`CLAUDE.md` → Hard rules);
- **without a ticket record** (no Jira key, `--no-tracker`, physics without a ticket): also the review summary, i.e.
  each round's verdict, counts, one line per finding and the response, and the validate report block, since nothing
  else keeps them once the worktree is removed (`.claude/context/branching.md`).
