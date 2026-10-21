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
        uv run .claude/hooks/change_kind.py --range origin/v9-develop...HEAD   # every file a branch touches

    Exit 0 = clean, 1 = violations (printed), 2 = could not run (not a git repo, bad range).
    --staged can't see the commit message: without --message, CLAUDE.md or .claude/context/ on a ticket branch gets a
    `NOTE:` (the code-facts trailer is checked when committing) instead of a violation.
    With --range it also checks the PR size budget and prints `WARNING: PR size budget: ...` lines (never a violation,
    never a change of the exit code): too many added files or lines outside product source and tests, an added file
    over the size cap, or data-like files. It also prints `HIGH-RISK: yes (<up to 5 paths>)` or `HIGH-RISK: no`
    (the diff touches the L-tier code of `process-tiers.md`; exit code unchanged). Raw run data belongs in .claude/work/<KEY>/ or a scratch directory.

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

# PR size budget (--range only; warnings, never violations). Source and test code is not counted: the budget is for
# what rides along with it (reports, raw data, generated files). PR #2 carried 1,282 such files.
BUDGET_MAX_FILES = 40            # added files outside source/test code
BUDGET_MAX_LINES = 3000          # added lines in files outside source/test code
BUDGET_MAX_FILE_BYTES = 1_000_000  # any single added file
CODE = re.compile(r"\.(m|v|F|F90|f|f90|c|h|py|sh)$")
DATA_LIKE = re.compile(r"\.(npz|npy|hdf5|h5|pkl|pickle|log)$|^(?!\.claude/).*\.jsonl?$", re.IGNORECASE)
BUDGET_HINT = ("not a failure: keep raw run data, logs, reports and generated files in .claude/work/<KEY>/ or a scratch directory and "
               "summarise them on the ticket page; if they really belong in the PR, say why in its description")

# High-risk code (process-tiers.md -> Tiers, the L list): a diff touching any of it makes the ticket tier L.
HIGH_RISK = re.compile(r"^(bbb/pandf[^/]*\.m$|ppp/|.*jac[^/]*$|.*\.v$|.*\.m$|setup\.py$|pyproject\.toml$|Makefile\.Forthon$|"
                       r"[^/]+/Package[^/]*$)", re.IGNORECASE)


def high_risk_paths(paths):
    return sorted({_clean(p) for p in paths if p and HIGH_RISK.match(_clean(p))})


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


def _clean(p):
    p = p.strip()
    return p[2:] if p.startswith("./") else p


def violations(branch: str, paths, message: str = "", deleted=(), renamed=None):
    """Return a list of human-readable violations for committing `paths` on `branch`.
    `deleted` names the paths among them that the commit deletes: removing a tracked working document is allowed.
    `renamed` maps a renamed path's new name to its old one: moving a working document out to another path is
    refused like adding it (copy it as a new file on purpose instead)."""
    kind = branch_kind(branch)
    paths = sorted(set(_clean(p) for p in paths if p and p.strip()))
    deleted = {_clean(p) for p in deleted}
    renamed = {_clean(k): _clean(v) for k, v in (renamed or {}).items()}
    if kind == "protected":
        return [f"'{branch}' is protected: never commit to it. Create feature/v9-* or bugfix/v9-* "
                f"(see .claude/context/branching.md)."]
    by_kind = {}
    for p in paths:
        by_kind.setdefault(path_kind(p), []).append(p)
    out = []
    working = [p for p in by_kind.get("working", []) if p not in deleted]
    if working:
        out.append(f"'{branch}': {WORKING_HINT}. Unstage: " + ", ".join(working))
    moved = [f"{old} -> {new}" for new, old in sorted(renamed.items())
             if path_kind(old) == "working" and path_kind(new) != "working" and new in paths]
    if moved:
        out.append(f"'{branch}': a working document is being moved into the repo ({', '.join(moved)}). Working "
                   f"documents are never committed; if this file really belongs in the repo (for example a physics "
                   f"spec), add it as a new file on purpose and say why in the commit message, and delete the old "
                   f"one in a separate step")
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


class Changes:
    """The paths a commit or range touches, which of them it deletes, and renames (new path -> old path)."""

    def __init__(self, paths=None, deleted=None, renamed=None):
        self.paths, self.deleted, self.renamed = list(paths or []), list(deleted or []), dict(renamed or {})

    def __iter__(self):  # paths, deleted = changes
        return iter((self.paths, self.deleted))

    def add(self, other):
        self.paths += other.paths
        self.deleted += other.deleted
        self.renamed.update(other.renamed)
        return self


def name_status_z(out):
    """Changes from `git diff --name-status -z` output: STATUS NUL path NUL, or for a rename or copy
    STATUS NUL old NUL new NUL. NUL-separated, so paths with spaces or quotes come through as they are."""
    ch, fields, i = Changes(), out.split("\0"), 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        if status[0] in "RC" and i + 2 < len(fields):
            old, new = fields[i + 1], fields[i + 2]
            ch.paths.append(new)
            if status[0] == "R":
                ch.renamed[new] = old
            i += 3
            continue
        path = fields[i + 1] if i + 1 < len(fields) else ""
        if path:
            ch.paths.append(path)
            if status.startswith("D"):
                ch.deleted.append(path)
        i += 2
    return ch


def staged_changes(cwd=None):
    return name_status_z(_git(["diff", "--cached", "--name-status", "-z", "-M"], cwd))


def staged_paths(cwd=None):
    return staged_changes(cwd).paths


def modified_tracked_changes(cwd=None):
    return name_status_z(_git(["diff", "--name-status", "-z", "-M"], cwd))


def modified_tracked_paths(cwd=None):
    return modified_tracked_changes(cwd).paths


def range_changes(rng, cwd=None):
    return name_status_z(_git(["diff", "--name-status", "-z", "-M", rng], cwd))


def range_paths(rng, cwd=None):
    return range_changes(rng, cwd).paths


def budget_warnings(rng, cwd=None):
    """PR size budget warnings for the files a range adds (see the BUDGET_* constants)."""
    right = (rng.split("...")[-1] if "..." in rng else rng.split("..")[-1] if ".." in rng else "") or "HEAD"
    added = [p for p in _git(["diff", "--name-only", "--no-renames", "--diff-filter=A", "-z", rng], cwd).split("\0")
             if p]
    lines = 0
    for rec in _git(["diff", "--numstat", "--no-renames", "-z", rng], cwd).split("\0"):
        parts = rec.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and not CODE.search(parts[2]):
            lines += int(parts[0])
    counted = [p for p in added if not CODE.search(p)]
    sizes = {}
    for rec in _git(["ls-tree", "-r", "-l", "-z", right], cwd).split("\0"):
        meta, _, path = rec.partition("\t")
        if path and meta.split()[-1].isdigit():
            sizes[path] = int(meta.split()[-1])
    out = []
    if len(counted) > BUDGET_MAX_FILES or lines > BUDGET_MAX_LINES:
        out.append(f"the branch adds {len(counted)} files and {lines} lines outside source and test code (budget "
                   f"{BUDGET_MAX_FILES} files / {BUDGET_MAX_LINES} lines)")
    big = [f"{p} ({sizes[p] // 1000} kB)" for p in added if sizes.get(p, 0) > BUDGET_MAX_FILE_BYTES]
    if big:
        out.append(f"added files over {BUDGET_MAX_FILE_BYTES // 1_000_000} MB: {', '.join(big)}")
    data = [p for p in added if DATA_LIKE.search(p)]
    if data:
        shown = ", ".join(data[:10]) + (f" and {len(data) - 10} more" if len(data) > 10 else "")
        out.append(f"data-like files added ({len(data)}): {shown}")
    return out + [BUDGET_HINT] if out else out


def is_tracked(path, cwd=None) -> bool:
    try:
        _git(["ls-files", "--error-unmatch", "--", path], cwd)
        return True
    except subprocess.CalledProcessError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="check the staged files (default)")
    g.add_argument("--range", help="check every file changed in a git range, e.g. origin/v9-develop...HEAD "
                   "(three dots: the branch's own changes since it forked)")
    ap.add_argument("--branch", help="branch to check against (default: current branch)")
    ap.add_argument("--message", default=None,
                    help="commit message (for the code-facts trailer; when given, even empty, it is checked)")
    a = ap.parse_args()
    try:
        branch = a.branch or current_branch()
        ch = range_changes(a.range) if a.range else staged_changes()
    except subprocess.CalledProcessError as e:
        print(e.stderr.strip() or str(e), file=sys.stderr)
        return 2
    message = a.message or ""
    if a.range and not message:
        # On a range, the trailer may sit in any commit of the branch.
        try:
            # A three-dot range (what CI and the skills use) names the branch's own commits on its right side.
            message = _git(["log", "--format=%B", *(["--right-only"] if "..." in a.range else []), a.range])
        except subprocess.CalledProcessError:
            message = ""
    print(f"branch: {branch} ({branch_kind(branch)})")
    for p in sorted(set(ch.paths)):
        print(f"  {path_kind(p):8s} {p}" + ("  (deleted)" if p in ch.deleted else "")
              + (f"  (renamed from {ch.renamed[p]})" if p in ch.renamed else ""))
    v = violations(branch, ch.paths, message, ch.deleted, ch.renamed)
    if not a.range and a.message is None:
        # --staged can't see the commit message, so a missing code-facts trailer is a note here; the PreToolUse hook
        # checks it on `git commit`. Every other violation stands.
        with_trailer = violations(branch, ch.paths, CODE_FACTS_TRAILER, ch.deleted, ch.renamed)
        if len(with_trailer) < len(v):
            facts = sorted(p for p in set(map(_clean, ch.paths)) if CODE_FACTS.match(p))
            print(f"NOTE: '{branch}' is a ticket branch: {', '.join(facts)} may change only in a code-facts "
                  f"edit (it only keeps the AI layer factually in line with code this branch changes), with the "
                  f"trailer '{CODE_FACTS_TRAILER}' in the commit message. --staged can't see the message: the "
                  f"PreToolUse hook checks it on git commit (or pass --message to check it now).")
            v = with_trailer
    for line in v:
        print("VIOLATION: " + line)
    if not v:
        print("OK")
    if a.range:
        hr = high_risk_paths(ch.paths)
        print(f"HIGH-RISK: yes ({', '.join(hr[:5])}{', ...' if len(hr) > 5 else ''})" if hr else "HIGH-RISK: no")
        try:
            for w in budget_warnings(a.range):
                print("WARNING: PR size budget: " + w)
        except (subprocess.CalledProcessError, ValueError, IndexError) as e:
            print(f"WARNING: PR size budget not checked ({e})")
    return 1 if v else 0


if __name__ == "__main__":
    sys.exit(main())
