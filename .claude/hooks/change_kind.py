#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Branch hygiene: keep AI-layer (process) work and product work on separate branches.

The policy lives in `.claude/context/branching.md`. This file is the deterministic check behind it:

  * imported by `pre_tool_use.py`, which runs `commit_violations()` before every `git commit` the agent makes;
  * runnable by hand, by the `commit`/`validate` skills, or by CI:

        uv run .claude/hooks/change_kind.py --staged              # what is staged now
        uv run .claude/hooks/change_kind.py --range v9-develop..HEAD   # every file a branch touches

    Exit 0 = clean, 1 = violations (printed), 2 = could not run (not a git repo, bad range).

Path classes
  working   .claude/work/** (the local working folder) and the legacy working-document paths .claude/plans/**,
            .claude/execution-reports/**, .claude/system-reviews/**, .claude/code-reviews/**,
            docs/{prds,specs,reviews,rca}/**. Ticket and epic working documents: plans, review reports and
            responses, validation records, RCAs, execution and system reviews, PRD copies, breakdowns, progress logs,
            close-out records. Never committed, on any branch: their lasting content goes to the ticket's Confluence
            page (`ticket-page` skill) or the epic's Confluence pages. Deleting one that is still tracked is allowed.
  process   CLAUDE.md, .mcp.json, .claude/** (skills, agents, context, hooks, settings), .githooks/**,
            .github/workflows/claude-*.yml. Changes how agents work.
  shared    .gitignore. Allowed on any branch.
  product   everything else (Fortran, .v, build, Python, CI, docs), including docs/physics_specs/**: an approved
            physics spec is committed with the physics change it specifies.

Branch classes
  protected main, develop, v9-main, v9-develop            -> no commits at all
  ai        feature/v9-ai-*, v9-agentic                   -> process only
  ticket    every other branch                            -> product;
            CLAUDE.md and .claude/context/** only with the commit trailer `AI-layer: code-facts`
            (= the edit only keeps the AI layer factually in line with the code this branch changes);
            other process paths (skills, agents, hooks, settings) never.
  Working documents are refused on every branch (deletions of tracked ones excepted).
"""

import argparse
import re
import subprocess
import sys

PROTECTED_BRANCHES = {"main", "develop", "v9-main", "v9-develop"}
AI_BRANCH = re.compile(r"^(feature/v9-ai-.+|v9-agentic)$")
CODE_FACTS_TRAILER = "AI-layer: code-facts"

# Ticket and epic working documents: the local working folder and the legacy paths they used to be committed under.
WORKING = re.compile(r"^(\.claude/(work|plans|execution-reports|system-reviews|code-reviews)/|"
                     r"docs/(prds|specs|reviews|rca)/)")
WORKING_HINT = ("working documents are never committed (plans, reviews and responses, validation records, RCAs, "
                "execution and system reviews, PRD copies, breakdowns, progress logs, close-out records). Keep "
                "them in the gitignored working folder .claude/work/<KEY>/ and put their lasting content on the "
                "ticket's Confluence page with the ticket-page skill (epic documents: the PRD page and its "
                "children). Physics specs belong in docs/physics_specs/ (.claude/context/branching.md)")
# The only process paths a ticket branch may touch, and only with the code-facts trailer: descriptions of the code.
CODE_FACTS = re.compile(r"^(CLAUDE\.md$|\.claude/context/)")
PROCESS = re.compile(r"^(CLAUDE\.md$|\.mcp\.json$|\.claude/|\.githooks/|\.github/workflows/claude-[^/]*\.ya?ml$)")
SHARED = {".gitignore"}


def path_kind(path: str) -> str:
    path = path.strip()
    if path.startswith("./"):
        path = path[2:]
    if path in SHARED:
        return "shared"
    if WORKING.match(path):
        return "working"
    if PROCESS.match(path):
        return "process"
    return "product"


def branch_kind(branch: str) -> str:
    if branch in PROTECTED_BRANCHES:
        return "protected"
    if AI_BRANCH.match(branch):
        return "ai"
    return "ticket"


def violations(branch: str, paths, message: str = "", deleted=()):
    """Return a list of human-readable violations for committing `paths` on `branch`.
    `deleted` names the paths among them that the commit deletes: removing a tracked working document is allowed."""
    kind = branch_kind(branch)
    paths = sorted(set(p.strip() for p in paths if p and p.strip()))
    deleted = {p.strip()[2:] if p.strip().startswith("./") else p.strip() for p in deleted}
    if kind == "protected":
        return [f"'{branch}' is protected: never commit to it. Create feature/v9-* or bugfix/v9-* "
                f"(see .claude/context/branching.md)."]
    by_kind = {}
    for p in paths:
        by_kind.setdefault(path_kind(p), []).append(p)
    out = []
    working = [p for p in by_kind.get("working", []) if (p[2:] if p.startswith("./") else p) not in deleted]
    if working:
        out.append(f"'{branch}': {WORKING_HINT}. Unstage: " + ", ".join(working))
    if kind == "ai":
        bad = by_kind.get("product", [])
        if bad:
            out.append(f"'{branch}' is an AI-layer branch; it may not carry product files. Move these to a ticket "
                       f"branch: " + ", ".join(bad))
    else:
        bad = by_kind.get("process", [])
        never = [p for p in bad if not CODE_FACTS.match(p)]
        if never:
            out.append(f"'{branch}' is a ticket branch; skills, agents, hooks and settings change only on a "
                       f"feature/v9-ai-* branch (the code-facts trailer covers only CLAUDE.md and "
                       f".claude/context/). Files: " + ", ".join(never))
            bad = [p for p in bad if CODE_FACTS.match(p)]
        if bad and CODE_FACTS_TRAILER not in message:
            out.append(f"'{branch}' is a ticket branch; AI-layer process files need their own "
                       f"feature/v9-ai-* branch. If this edit only keeps the AI layer factually in line "
                       f"with code this branch changes, add the trailer '{CODE_FACTS_TRAILER}' to the "
                       f"commit message. Files: " + ", ".join(bad))
    return out


def _git(args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def current_branch(cwd=None) -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).strip()


def _name_status(out):
    """(paths, deleted) from `git diff --name-status` output (a rename counts as its new path)."""
    paths, deleted = [], []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        paths.append(path)
        if status.startswith("D"):
            deleted.append(path)
    return paths, deleted


def staged_changes(cwd=None):
    return _name_status(_git(["diff", "--cached", "--name-status"], cwd))


def staged_paths(cwd=None):
    return staged_changes(cwd)[0]


def modified_tracked_changes(cwd=None):
    return _name_status(_git(["diff", "--name-status"], cwd))


def modified_tracked_paths(cwd=None):
    return modified_tracked_changes(cwd)[0]


def range_changes(rng, cwd=None):
    return _name_status(_git(["diff", "--name-status", rng], cwd))


def range_paths(rng, cwd=None):
    return range_changes(rng, cwd)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="check the staged files (default)")
    g.add_argument("--range", help="check every file changed in a git range, e.g. v9-develop..HEAD")
    ap.add_argument("--branch", help="branch to check against (default: current branch)")
    ap.add_argument("--message", default="", help="commit message (for the code-facts trailer)")
    a = ap.parse_args()
    try:
        branch = a.branch or current_branch()
        paths, deleted = range_changes(a.range) if a.range else staged_changes()
    except subprocess.CalledProcessError as e:
        print(e.stderr.strip() or str(e), file=sys.stderr)
        return 2
    message = a.message
    if a.range and not message:
        # On a range, the trailer may sit in any commit of the branch.
        try:
            message = _git(["log", "--format=%B", a.range])
        except subprocess.CalledProcessError:
            message = ""
    print(f"branch: {branch} ({branch_kind(branch)})")
    for p in sorted(set(paths)):
        print(f"  {path_kind(p):8s} {p}" + ("  (deleted)" if p in deleted else ""))
    v = violations(branch, paths, message, deleted)
    for line in v:
        print("VIOLATION: " + line)
    if not v:
        print("OK")
    return 1 if v else 0


if __name__ == "__main__":
    sys.exit(main())
