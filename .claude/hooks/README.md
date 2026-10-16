# Hooks — the deterministic layer of the AI Layer

Hooks are the fifth primitive. Rules, subagents, tools, and skills are all things the agent *reaches for*.
A hook is the one the agent never chooses: it fires automatically on a lifecycle event.

> **A rule asks the agent to behave. A hook guarantees it.**
>
> Reach for a rule when "usually" is fine. Reach for a hook when it **must** happen every single time.

## What ships here

| File | Event | What it does | Can it block? |
|---|---|---|---|
| `pre_tool_use.py` | **PreToolUse** | Blocks reading/writing/searching a real env file (committed `.env.example` templates are allowed), and blocks any `rm -rf` whose targets are outside this repository, are the repo root or `.git/`, or can't be resolved statically (`$VARS`, `xargs`, `find -exec`). Prints the reason to stderr and `exit(2)` → the tool is stopped and the agent is told why, so it adapts. | **Yes** — this is the guarantee |
| `pre_tool_use.py` + `change_kind.py` | **PreToolUse** (`git commit`) | Branch policy (`.claude/context/branching.md`). Blocks commits to `main`/`develop`/`v9-main`/`v9-develop`, ticket and epic working documents (`.claude/work/**` and the legacy `.claude/plans/`, `docs/{prds,specs,reviews,rca}/` paths; gitignored, their record is on Confluence) on any branch, product files on an AI-layer branch (`feature/v9-ai-*`, `v9-agentic`), and AI-layer process files on a ticket branch unless the message has the `AI-layer: code-facts` trailer. Deleting a tracked working document is allowed; moving one (a rename) into a product path is refused. It reads the staged files (`git diff --cached --name-status -z`, so paths with spaces are read as they are) plus the paths named by `git add` in the same command (`git status --porcelain -z` for `-A`/`.`; a named path that is missing counts as a deletion only if it is tracked). Before matching, only the body of each here-document (`<<EOF`, `<<'EOF'`, `<<-EOF`) is dropped, so text that only mentions a commit is not one; the rest of the opening line (`cat <<EOF | git commit -F -`) is kept and checked, a herestring (`<<<`) is not treated as a here-document, and an empty body ends at its terminator. Not checked: commands fed to another shell through a here-document (`bash <<EOF`, `sh`, `ssh host`, `xargs`), which the hook can't see (fail open). `change_kind.py` also runs on its own: `--staged`, `--range origin/v9-develop...HEAD` (three dots); `--range` also prints `WARNING: PR size budget` lines (warnings only: more than 40 added files or 3,000 added lines outside source and test code, an added file over 1 MB, data-like files). Its test: `.claude/hooks/test_change_kind.sh` (run it after changing either file). | **Yes** |
| `check_context_refs.py` | (tool, not a hook) run by `validate`, `code-review`, `execute`, `implement-fix`, `uedge-implementer` and CI (`claude-context-drift.yml`) | Drift check: every `path:line` in `CLAUDE.md`/`.claude/` is compared with the text locked in `.claude/context/refs.lock.json`. It reports MOVED (fix with `--fix`), STALE, BROKEN, NEW and MISSING, and with `--changed <base>` lists the docs that cite changed files. | Fails `validate`/CI |
| `session_guard.py` | **PreToolUse** (`Agent`, `Task`, `SendMessage`), **UserPromptSubmit** | Warns the owner (a `systemMessage`, shown in the UI) when a session drifts into the costly patterns of epic AIUE-8 (`.claude/context/process-tiers.md` → Session SOP): a 4th agent launched within 45 min; a `SendMessage` resume of an agent whose transcript (`<session dir>/subagents/agent-<id>.jsonl`, only stat-ed) is ≥2 MB; once per session, a coordinating transcript ≥15 MB or with ≥2 compactions. Thresholds are constants at the top of the file; state in `logs/session_guard.jsonl` (gitignored). Test: `uv run .claude/hooks/test_session_guard.py`. | **No** — never blocks, never sets a permission decision; fails open |
| `post_tool_use.py` | **PostToolUse** | Appends every tool call as one JSON line to `<repo>/logs/post_tool_use.jsonl` (gitignored), regardless of the agent's working directory — a full local audit trail of what the agent did. | No — the tool already ran; observe only |

That split *is* the mental model: **pre = gate, post = log** (and one **nudge**, `session_guard.py`, which only
warns). The gates and the log are always-on safety, generic to any codebase. Anything more specific to *your* workflow (a checker
that gates completion, an artifact hand-off between two skills) is a conversation with your agent away, not a
file to copy — see below.

### Exit codes — the one thing to get right

**Only `exit 2` blocks.** Not exit 1, which is what every linter, type checker and test runner returns on
failure. Converting one into the other is most of what a gate-style hook does.

| Exit | Meaning |
|---|---|
| `0` | success. stdout goes to the debug log (except on `UserPromptSubmit` / `SessionStart`, where it becomes context) |
| **`2`** | **blocking error.** stderr is handed to the agent as the reason |
| anything else | non-blocking error: noise, no effect |

What `exit 2` blocks depends on the event:

| Event | Does `exit 2` block? |
|---|---|
| `PreToolUse` | **yes** — the tool call is stopped (`pre_tool_use.py` relies on this) |
| `Stop` | **yes** — the session is prevented from finishing |
| `PostToolUse` | **no** — the tool already ran; stderr is merely shown, so `post_tool_use.py` always exits 0 |

## Turning them on

In this repo the hooks are already live: `.claude/settings.json` is committed, so everyone working here with
Claude Code inherits the same guarantees. `.claude/settings.json.example` holds just the `hooks` block, to merge
into another project's settings. Both hooks run through `uv run`, so `uv` must be on PATH.

## Try it

```
ask the agent to read your env file          -> blocked (exit 2, reason handed back)
ask it to read a committed .env.example       -> allowed
ask it to run `rm -rf build`                  -> allowed (inside the repo)
ask it to run `rm -rf ../elsewhere` or `/tmp` -> blocked
any normal command                            -> allowed, and logged to logs/post_tool_use.jsonl
```

You can also test a hook directly, without the agent:

```bash
echo '{"tool_name":"Read","tool_input":{"file_path":".env"}}' | uv run .claude/hooks/pre_tool_use.py; echo "exit=$?"
```

`exit=2` means the guard fired.

## Building your own — you don't have to write Python by hand, and this pack doesn't ship examples on purpose

The two hooks above are deliberately generic — safe defaults for any codebase. The moment you want something
specific to *your* workflow (gate completion on your own checks, hand an artifact from one skill to the next,
auto-format on edit), that's not something a generic starter pack can hand you as a ready file — it has to
know your commands, your paths, your checks. Describe it to your agent instead, in plain English, e.g.:

> "Don't let me finish until my tests pass — run my test command when I try to stop, and if it fails, block the
> stop and tell me why."

Claude Code (and most current coding agents) can pick the right lifecycle event, write the script, and wire it
into `settings.json` for you from a description like that — no need to hand-write hook JSON. Common shapes
worth knowing by name before you ask for one:

- **react** (`PostToolUse`) — something fires because a file changed. Auto-format on edit is the classic case.
- **gate** (`Stop`) — the agent can't declare done while your checks are red. **Bound it yourself** — a
  hook has no memory, so if it can retry, give it its own attempt counter on disk. Don't trust an
  undocumented flag to bound a loop for you; verify what actually happens before you rely on it.
- **baton** — one skill's artifact lands, and the hook starts the next skill in a **fresh** context. Guard it
  on file state (input present, output absent), never on memory — the guard is what makes it safe to fire a
  hundred times and act exactly once.

## Two things to know

- **Hooks run real code, automatically, with your credentials, with no sandbox.** Review a hook the way you'd
  review a CI script. Only run hooks you have read and trust. This is the same caution as MCP servers.
- **Coverage is yours.** The hook is guaranteed to *run*; what it *catches* is only as good as the check you
  wrote. It is the enforcement point, not omniscience.

## Portability

This is not a Claude Code party trick. Codex and Cursor use the same shape (a script, JSON on stdin,
`exit 2` to block); Gemini CLI does the same job by reading a structured JSON decision instead of the exit
code; Pi and opencode run hooks in-process as plugins. Learn it once, it transfers — the same way `AGENTS.md`
became the shared rules file.
