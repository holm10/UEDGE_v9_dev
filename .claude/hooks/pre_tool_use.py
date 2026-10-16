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

Three guarantees ship here:
  1. The agent can never reach your secrets — not the env file, not the other
     credential files (ssh keys, .pem, .aws, .netrc, credentials.json), and not
     by dumping the process environment. Committed `.env.example` is allowed.
  2. A recursive-force delete (`rm -rf`) may only target paths inside this
     repository (never the repo root itself or .git/). Anything outside the
     repo, or any target that can't be resolved statically ($VARS, `cmd`,
     xargs, find -exec), is blocked.

  3. A `git commit` must respect the branch policy (`.claude/context/branching.md`,
     checked by `change_kind.py`): nothing on protected branches, no ticket or epic working
     documents on any branch (they live in the gitignored `.claude/work/` and on Confluence),
     no product files on AI-layer branches, no AI-layer process files on ticket branches
     unless the message carries the `AI-layer: code-facts` trailer.

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


GIT = r"\bgit\s+(?:-C\s+(?P<C>\S+)\s+)?"
GIT_COMMIT = re.compile(GIT + r"commit\b(?P<args>[^\n;&|]*)")
GIT_ADD = re.compile(GIT + r"add\s+(?P<args>[^\n;&|]*)")
GIT_NEW_BRANCH = re.compile(GIT + r"(?:checkout\s+-[bB]|switch\s+-[cC])\s+(?P<b>[^\s;&|]+)")
CD = re.compile(r"(?:^|[;&|]\s*)cd\s+(?P<d>[^\s;&|]+)")
# A here-document body (<<EOF ... EOF, <<'EOF', <<-EOF): text, not commands, so it is dropped before matching the git
# commands above. The commit message itself (git commit -F - <<'EOF') stays in the full command for the trailer check.
# Limitation: commands fed to a shell through a here-document (bash <<EOF ... EOF) are not seen (fail open).
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\1[^\n]*\n.*?\n[ \t]*(?P=tag)[ \t]*(?=\n|$)",
                     re.S)


def strip_heredocs(command: str) -> str:
    return HEREDOC.sub("<<heredoc", command)


def _porcelain_z(workdir):
    """Changes from `git status --porcelain -z -uall` (what `git add -A` would stage): NUL-separated entries
    'XY path', a rename followed by its old path as the next field."""
    import subprocess
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import change_kind as ck
    out = subprocess.run(["git", "status", "--porcelain", "-z", "-uall"], cwd=workdir,
                         capture_output=True, text=True, check=True).stdout
    ch, fields, i = ck.Changes(), out.split("\0"), 0
    while i < len(fields) and fields[i]:
        xy, path = fields[i][:2], fields[i][3:]
        ch.paths.append(path)
        if "D" in xy:
            ch.deleted.append(path)
        if "R" in xy or "C" in xy:
            if "R" in xy and i + 1 < len(fields):
                ch.renamed[path] = fields[i + 1]
            i += 2
            continue
        i += 1
    return ch


def commit_hygiene_reason(tool_name: str, tool_input: dict, cwd):
    """Reason string if a `git commit` would break the branch policy (.claude/context/branching.md)."""
    if tool_name != "Bash":
        return None
    full = tool_input.get("command", "")
    command = strip_heredocs(full)
    m = GIT_COMMIT.search(command)
    if not m:
        return None
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import change_kind as ck

    head = command[:m.start()]
    workdir = cwd or str(_project_root())
    for d in CD.finditer(head):
        if UNRESOLVABLE.search(d.group("d")):
            return None  # cannot tell where the commit runs; fail open
        workdir = os.path.normpath(os.path.join(workdir, os.path.expanduser(d.group("d"))))
    if m.group("C"):
        workdir = os.path.normpath(os.path.join(workdir, os.path.expanduser(m.group("C"))))

    branch = ck.current_branch(workdir)
    for b in GIT_NEW_BRANCH.finditer(head):
        branch = b.group("b")

    ch = ck.staged_changes(workdir)
    for a in GIT_ADD.finditer(head):
        try:
            args = shlex.split(a.group("args"))
        except ValueError:
            args = a.group("args").split()
        files = [x for x in args if not x.startswith("-")]
        if any(x in (".", "-A", "--all") for x in args) or any(os.path.isdir(os.path.join(workdir, f)) for f in files):
            ch.add(_porcelain_z(workdir))
        else:
            ch.paths += files
            # Adding a path that no longer exists stages its deletion, but only for a tracked path: a file the same
            # command creates first (echo > x && git add x) doesn't exist yet when the hook runs and is an addition.
            ch.deleted += [f for f in files
                           if not os.path.lexists(os.path.join(workdir, f)) and ck.is_tracked(f, workdir)]
    commit_args = m.group("args").split()
    if "--all" in commit_args or any(x.startswith("-") and not x.startswith("--") and "a" in x
                                     for x in commit_args if not x.startswith("-m")):
        ch.add(ck.modified_tracked_changes(workdir))

    problems = ck.violations(branch, ch.paths, full, ch.deleted, ch.renamed)
    return " ".join(problems) if problems else None


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

        reason = commit_hygiene_reason(tool_name, tool_input, data.get("cwd"))
        if reason:
            print("BLOCKED by branch policy: " + reason, file=sys.stderr)
            sys.exit(2)

        sys.exit(0)  # allow

    except Exception:
        # Fail open — never let a hook error stop the agent from working.
        sys.exit(0)


if __name__ == "__main__":
    main()
