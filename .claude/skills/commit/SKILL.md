---
name: commit
description: Creates a git commit for the current work with an explicit file list and a repo-style imperative message (optional CI tags). Use when work is complete and ready to be committed.
---

# Commit

## Process

1. Inspect the work: `git status`, `git diff HEAD --stat`, `git diff HEAD`.
2. Check the branch. Never commit to `main`, `develop`, `v9-main`, or `v9-develop` — stop and ask for a
   `feature/v9-*` / `bugfix/v9-*` branch instead (`doc/workflow.md`).
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
Only if files under `.claude/` or `CLAUDE.md` changed: one line per file on what evolved and why.
