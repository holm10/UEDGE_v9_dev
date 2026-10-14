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
  process   CLAUDE.md, .mcp.json, .claude/** (skills, agents, context, hooks, settings), .githooks/**,
            .github/workflows/claude-*.yml. Changes how agents work.
  shared    .gitignore. Allowed on any branch.
  record    .claude/execution-reports/**, .claude/system-reviews/**. Process records; allowed on any branch.
  artifact  .claude/plans/**, docs/{prds,specs,reviews,rca,physics_specs}/**. Belong to a ticket/epic.
  product   everything else (Fortran, .v, build, Python, CI, docs).

Branch classes
  protected main, develop, v9-main, v9-develop            -> no commits at all
  ai        feature/v9-ai-*, v9-agentic                   -> process + record only
  ticket    every other branch                            -> product + artifact + record;
            process paths only with the commit trailer `AI-layer: code-facts`
            (= the edit only keeps the AI layer factually in line with the code this branch changes).
"""

import argparse
import re
import subprocess
import sys

PROTECTED_BRANCHES = {"main", "develop", "v9-main", "v9-develop"}
AI_BRANCH = re.compile(r"^(feature/v9-ai-.+|v9-agentic)$")
CODE_FACTS_TRAILER = "AI-layer: code-facts"

RECORD = re.compile(r"^\.claude/(execution-reports|system-reviews)/")
ARTIFACT = re.compile(r"^(\.claude/plans/|docs/(prds|specs|reviews|rca|physics_specs)/)")
PROCESS = re.compile(r"^(CLAUDE\.md$|\.mcp\.json$|\.claude/|\.githooks/|\.github/workflows/claude-[^/]*\.ya?ml$)")
SHARED = {".gitignore"}


def path_kind(path: str) -> str:
    path = path.strip()
    if path.startswith("./"):
        path = path[2:]
    if path in SHARED:
        return "shared"
    if RECORD.match(path):
        return "record"
    if ARTIFACT.match(path):
        return "artifact"
    if PROCESS.match(path):
        return "process"
    return "product"


def branch_kind(branch: str) -> str:
    if branch in PROTECTED_BRANCHES:
        return "protected"
    if AI_BRANCH.match(branch):
        return "ai"
    return "ticket"


def violations(branch: str, paths, message: str = ""):
    """Return a list of human-readable violations for committing `paths` on `branch`."""
    kind = branch_kind(branch)
    paths = sorted(set(p for p in paths if p))
    if kind == "protected":
        return [f"'{branch}' is protected: never commit to it. Create feature/v9-* or bugfix/v9-* "
                f"(see .claude/context/branching.md)."]
    by_kind = {}
    for p in paths:
        by_kind.setdefault(path_kind(p), []).append(p)
    out = []
    if kind == "ai":
        bad = by_kind.get("product", []) + by_kind.get("artifact", [])
        if bad:
            out.append(f"'{branch}' is an AI-layer branch; it may not carry product files or ticket "
                       f"artifacts. Move these to a ticket branch: " + ", ".join(bad))
    else:
        bad = by_kind.get("process", [])
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


def staged_paths(cwd=None):
    return _git(["diff", "--cached", "--name-only"], cwd).splitlines()


def modified_tracked_paths(cwd=None):
    return _git(["diff", "--name-only"], cwd).splitlines()


def range_paths(rng, cwd=None):
    return _git(["diff", "--name-only", rng], cwd).splitlines()


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
        paths = range_paths(a.range) if a.range else staged_paths()
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
        print(f"  {path_kind(p):8s} {p}")
    v = violations(branch, paths, message)
    for line in v:
        print("VIOLATION: " + line)
    if not v:
        print("OK")
    return 1 if v else 0


if __name__ == "__main__":
    sys.exit(main())
