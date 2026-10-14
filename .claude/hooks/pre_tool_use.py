#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
PreToolUse hook — the deterministic guardrail.

Fires BEFORE every matched tool call. It inspects what the agent is about to do
and, if the call crosses a line you never want crossed, blocks it: print the
reason to stderr and exit(2). Claude Code stops the tool and hands the reason
back to the agent, so it adapts instead of doing the thing.

Two guarantees ship here:
  1. The agent can never reach your secrets — not the env file, not the other
     credential files (ssh keys, .pem, .aws, .netrc, credentials.json), and not
     by dumping the process environment. Committed `.env.example` is allowed.
  2. A recursive-force delete (`rm -rf`) may only target paths inside this
     repository (never the repo root itself or .git/). Anything outside the
     repo, or any target that can't be resolved statically ($VARS, `cmd`,
     xargs, find -exec), is blocked.

Everything else is allowed (exit 0). The hook FAILS OPEN: any unexpected error
exits 0, so a bug in this script can never brick your session.

MAKE IT YOURS: `is_secret_access` and `dangerous_rm_reason` below are the entire policy. Add your own
(protected paths, prod config, lockfiles, migrations) by hand, or describe the
guarantee you want in plain English and have your agent write it for you.

A note on coverage: the hook is GUARANTEED to run — what it CATCHES is only as
good as the checks below. This blocks the obvious routes, not every conceivable
one. The hook is the enforcement point; you still own the coverage.
"""

import glob
import json
import os
import re
import shlex
import sys
from pathlib import Path

# Committed template files that are safe to read. Everything else that looks like
# an env file is treated as real secrets. Change this one line if your repo uses a
# different convention (e.g. add ".env.sample" or ".env.template").
ENV_TEMPLATE_SUFFIXES = (".env.example",)

# Secrets do not only live in `.env` — these are the other usual homes.
SECRET_PATH = re.compile(
    r"\.env\b|\.pem$|\.key$|id_rsa|id_ed25519|\.ssh/|\.aws/credentials|\.netrc|credentials\.json",
    re.IGNORECASE,
)

# ...and they do not only live in FILES. Each of these reads them straight out of
# the process environment, which a file-only guard waves right through.
ENV_DUMP = (
    re.compile(r"\bprintenv\b", re.IGNORECASE),
    re.compile(r"^\s*env\s*(\||>|$)", re.IGNORECASE),            # bare `env`, maybe piped
    re.compile(r"\becho\b.*\$\{?[A-Z_]*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", re.IGNORECASE),
    re.compile(r"os.environ|process\.env|ENV\[", re.IGNORECASE),
)

BLOCKED_ENV_MESSAGE = (
    "BLOCKED: access to secrets is not allowed.\n"
    "Read a committed .env.example template instead."
)
BLOCKED_RM_MESSAGE = (
    "BLOCKED: rm -rf is only allowed on paths inside this repository "
    "(not the repo root or .git/). Reason: {reason}"
)

UNRESOLVABLE = re.compile(r"[$`]|<\(")
RM_WORD = re.compile(r"(^|[\s;&|(/])rm\s")


def _is_template(path: str) -> bool:
    return path.endswith(ENV_TEMPLATE_SUFFIXES)


def is_secret_access(tool_name: str, tool_input: dict) -> bool:
    """True if the call would reach a credential — by file OR by environment."""
    # File tools: check the path argument.
    if tool_name in ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit"):
        path = tool_input.get("file_path", "").replace("\\", "/")
        return bool(SECRET_PATH.search(path)) and not _is_template(path)

    # Search tools: block reading secrets out via a pattern or a scoped path.
    if tool_name in ("Grep", "Glob"):
        target = f"{tool_input.get('pattern', '')} {tool_input.get('path', '')}".replace("\\", "/")
        return bool(SECRET_PATH.search(target)) and ".env.example" not in target

    # Bash: the command may name a credential file OR dump the environment.
    if tool_name == "Bash":
        command = tool_input.get("command", "").replace("\\", "/")
        if any(p.search(command) for p in ENV_DUMP):
            return True
        return bool(SECRET_PATH.search(command)) and ".env.example" not in command

    return False


def _project_root() -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(root).resolve() if root else Path(__file__).resolve().parents[2]


def _rm_flags(args: list) -> tuple:
    """Return (recursive, force, targets) for the arguments following `rm`."""
    recursive = force = False
    targets = []
    end_of_flags = False
    for arg in args:
        if not end_of_flags and arg == "--":
            end_of_flags = True
        elif not end_of_flags and arg.startswith("--"):
            recursive |= arg == "--recursive"
            force |= arg == "--force"
        elif not end_of_flags and arg.startswith("-") and len(arg) > 1:
            recursive |= "r" in arg or "R" in arg
            force |= "f" in arg
        else:
            targets.append(arg)
    return recursive, force, targets


def _outside_reason(target: str, cwd, root: Path):
    """None if `target` is a safe in-repo path, otherwise a short reason."""
    if UNRESOLVABLE.search(target):
        return f"cannot resolve '{target}' statically"
    path = os.path.expanduser(target)
    if not os.path.isabs(path):
        if cwd is None:
            return f"unknown working directory for relative path '{target}'"
        path = os.path.join(cwd, path)
    candidates = glob.glob(path) if glob.has_magic(path) else []
    for candidate in candidates or [path]:
        resolved = Path(os.path.realpath(candidate))
        if resolved == root:
            return "target is the repository root"
        if root not in resolved.parents:
            return f"'{target}' resolves outside the repository ({resolved})"
        if (root / ".git") == resolved or (root / ".git") in resolved.parents:
            return f"'{target}' is inside .git/"
    return None


def _simple_commands(command: str) -> list:
    """Split a command line into simple commands (lists of words), respecting quotes."""
    lexer = shlex.shlex(command.replace("\n", ";"), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments, words = [], []
    for token in lexer:
        if token and all(c in "();<>|&" for c in token):
            if words:
                segments.append(words)
            words = []
        else:
            words.append(token)
    if words:
        segments.append(words)
    return segments


def dangerous_rm_reason(tool_name: str, tool_input: dict, cwd):
    """Reason string if a Bash command runs rm -rf on anything outside the repo."""
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "")
    if not RM_WORD.search(command):
        return None
    root = _project_root()
    try:
        segments = _simple_commands(command)
    except ValueError:
        return "could not parse a command that contains rm"
    for words in segments:
        if words[0] == "cd":
            target = words[1] if len(words) > 1 else "~"
            if UNRESOLVABLE.search(target):
                cwd = None
            else:
                base = cwd or str(root)
                cwd = os.path.normpath(os.path.join(base, os.path.expanduser(target)))
            continue
        for i, word in enumerate(words):
            if os.path.basename(word) != "rm":
                continue
            recursive, force, targets = _rm_flags(words[i + 1:])
            if not (recursive and force):
                break
            if any(w in ("xargs", "-exec", "-execdir") for w in words[:i]):
                return "rm -rf fed by xargs/find -exec cannot be checked"
            for target in targets:
                reason = _outside_reason(target, cwd, root)
                if reason:
                    return reason
            break
    return None


def main() -> None:
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})

        if is_secret_access(tool_name, tool_input):
            # exit 2 = block the tool; stderr goes back to the agent as the reason.
            print(BLOCKED_ENV_MESSAGE, file=sys.stderr)
            sys.exit(2)

        reason = dangerous_rm_reason(tool_name, tool_input, data.get("cwd"))
        if reason:
            print(BLOCKED_RM_MESSAGE.format(reason=reason), file=sys.stderr)
            sys.exit(2)

        sys.exit(0)  # allow

    except Exception:
        # Fail open — never let a hook error stop the agent from working.
        sys.exit(0)


if __name__ == "__main__":
    main()
