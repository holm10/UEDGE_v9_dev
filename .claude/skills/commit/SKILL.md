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
   - product files or ticket artifacts on an AI-layer branch (`feature/v9-ai-*`, `v9-agentic`) → unstage them and
     commit them on their ticket branch;
   - AI-layer process files on a ticket branch → if they only keep `CLAUDE.md`/`.claude/context/` accurate about
     code this branch changes, add the trailer `AI-layer: code-facts`. Otherwise unstage them and move them to a
     `feature/v9-ai-<slug>` branch.
   The PreToolUse hook runs the same check on `git commit` and blocks violations, so fix them here instead of
   working around the block. **Never** add the trailer to get a process change through.
3. **Stage explicitly** by path: only files that belong to this change. Never `git add -A` / `git add .`.
   Do not stage `logs/`, build output, generated `.F` files, scratch scripts, or large data files unless asked.
   New `.f`/`.c` sources need `git add -f` (gitignored patterns).
4. Write the message in the repo's style:
   - Subject: imperative, capitalised, no tag prefix, ≤ 72 chars — "Fixes …", "Adds …", "Updates …",
     "Simplifies …" (see `git log --oneline`).
   - Body (if needed): what changed and why, wrapped at ~72 chars. For physics changes, state whether default
     results change and which reference cases move.
   - Optional CI tags on their own line after `#`: `#@notest`, `#@nowheel`, `#@nobasis`
     (only when the user asks to skip those CI stages).
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
