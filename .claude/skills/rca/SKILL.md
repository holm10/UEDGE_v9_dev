---
name: rca
description: Investigates a GitHub issue, identifies the root cause, and writes a structured RCA document for later implementation. Use when you need to diagnose a bug reported as a GitHub issue before fixing it.
argument-hint: [github-issue-id] [jira-key] [--no-tracker] [--tracker-dry-run]
---

# Root Cause Analysis: GitHub Issue #$ARGUMENTS

## Objective

Investigate GitHub issue #$ARGUMENTS from this repository, identify the root cause, and document findings for future implementation.

**Prerequisites:**
- Working in a local Git repository with GitHub origin
- GitHub CLI installed and authenticated (`gh auth status`)
- Valid GitHub issue ID. UEDGE issues usually live upstream: use `gh issue view $ARGUMENTS -R LLNL/UEDGE`
  when the issue is not on `origin`
- Read `CLAUDE.md` and the `.claude/context/` modules for the area involved before analysing code
- Work on the issue's own branch: create `bugfix/v9-issue-$ARGUMENTS-<slug>` and its worktree
  (`git worktree add -b <branch> ../uedge-wt/issue-$ARGUMENTS origin/v9-develop`, see
  `.claude/context/branching.md`) before writing the RCA. The RCA is a working document: it is written to that
  worktree's working folder `.claude/work/issue-$ARGUMENTS/` (gitignored) and never committed. Its lasting copy goes
  to the ticket page or the GitHub issue (see "Publish the RCA")

## Investigation Process

### 1. Fetch GitHub Issue Details

**Use GitHub CLI to retrieve issue information:**

```bash
gh issue view $ARGUMENTS
```

This fetches:
- Issue title and description
- Reporter and creation date
- Labels and status
- Comments and discussion

### 2. Search Codebase

**Identify relevant code:**
- Search for components mentioned in issue
- Find related functions, classes, or modules
- Check similar implementations
- Look for patterns or recent changes

Use grep/search to find:
- Error messages from the issue (`xerrab`/`remark` strings in `*.m`)
- Variables and switches named in the issue (declared in `*/*.v`, used via `Use(Group)`)
- The routine in the `pandf` call chain (`bbb/pandf.m`) or setup (`bbb/odesetup.m`) where the quantity is computed

### 3. Review Recent History

Check recent changes to affected areas:
!`git log --oneline -20 -- [relevant-paths]`

Look for:
- Recent modifications to affected code
- Related bug fixes
- Refactorings that might have introduced the issue

**A regression against stored references (a pytests case, a saved state):** establish a known-good baseline before
building or bisecting anything.
- Replay the failing case on LLNL's published wheels first: in a scratch venv, `pip install "uedge==<version>"` for a
  few releases (the release history at https://pypi.org/project/uedge/#history; `pip index versions uedge` may find
  none for your Python), then run the case from the pytests checkout. Also build the last upstream merge
  (`git merge-base origin/v9-develop upstream/master`). Minutes, not hours.
- If they reproduce the references, the references are right and the divergence is **fork-only**: bisect the fork's
  own commits, `git bisect start --first-parent <bad> <last upstream merge>`. If they don't, the reference or the
  test is suspect; say so before going further.
- Before bisecting, record the **final value** (e.g. the case's `fnrm`) at the bad end and confirm that the good end
  reproduces the reference. Then classify each step by the final value, not by "matches the reference": equals the
  final value → `bad`; runs and gives any other value → `good`; doesn't build or crashes → `git bisect skip`. This
  keeps a window where the case is wrong in another way from hiding the change. If the skips leave several
  candidates, git names them: read their diffs. The bisect finds the last commit that produced the final value; if
  an earlier commit also moved it, bisect again with that commit's parent as the bad end. Building old commits on
  macOS needs the flags in `.claude/context/testing.md` → "Bisecting old commits on macOS".

### 4. Investigate Root Cause

**Analyze the code to determine:**
- What is the actual bug or issue?
- Why is it happening?
- What was the original intent?
- Is this a logic error, edge case, or missing validation?
- Are there related issues or symptoms?

**Attributions come from the diff.** A claim that commit X introduced, changed or set a default or a value quotes the
diff line that does it (`git show X -- <file> | grep -n '<name>'`). `git log -S`/`-G` only finds commits that touch
the string: the commit that added a variable with one default is not the one that changed it (AIUE-116: f5bd464
added `ismolcrm` with `/0/`; 174ce09 set `/1./`).

**Consider (UEDGE-typical causes):**
- Index errors at guard cells, cuts or X-points (`ix±1` instead of `ixm1`/`ixp1`; `nxpt=2`; snowflake/slab
  geometries)
- Loop ranges in local (Jacobian) evaluation vs full RHS (`initialize_ranges`, `Selec`)
- OpenMP: variables written in `pandf` that are not `+threadprivate`; chunk padding (compare serial vs parallel
  with `ppp.CheckPandf1` / `ppp.CheckJac`)
- Units (temperatures in J), species/indexing (`ifld`, `igsp`, `nisp` vs `nusp`)
- MPPL conversion artefacts (`#`/`float`/`break` substitutions in `setup.py`)
- Uninitialised or not-reallocated arrays after grid/species changes (`gchange`)
- Save/restore format issues in `src/uedge/hdf5.py`

### 5. Assess Impact

**Determine:**
- How widespread is this issue?
- What features are affected?
- Are there workarounds?
- What is the severity?
- Does it change physical results of existing cases (which ones), and do published/benchmark runs depend on it?

### 6. Propose Fix Approach

**Design the solution:**
- What needs to be changed?
- Which files will be modified?
- What is the fix strategy?
- Are there alternative approaches?
- What testing is needed?
- Are there any risks or side effects?

## Output: Create RCA Document

Save analysis as: `.claude/work/issue-$ARGUMENTS/rca.md` in the issue's worktree (local, never committed), then
publish it (below).

### Required RCA Document Structure

```markdown
# Root Cause Analysis: GitHub Issue #$ARGUMENTS

## Issue Summary

- **GitHub Issue ID**: #$ARGUMENTS
- **Issue URL**: [Link to GitHub issue]
- **Title**: [Issue title from GitHub]
- **Reporter**: [GitHub username]
- **Severity**: [Critical/High/Medium/Low]
- **Status**: [Current GitHub issue status]

## Problem Description

[Clear description of the issue]

**Expected Behavior:**
[What should happen]

**Actual Behavior:**
[What actually happens]

**Symptoms:**
- [List observable symptoms]

## Reproduction

**Steps to Reproduce:**
1. [Build type (serial/OpenMP), input deck or script, key switches]
2. [Command, e.g. `bbb.exmain()`]
3. [Observed error/value vs expected]

**Reproduction Verified:** [Yes/No]

## Root Cause

### Affected Components

- **Files**: [List of affected files with paths]
- **Functions/Classes**: [Specific code locations]
- **Dependencies**: [Any external deps involved]

### Analysis

[Detailed explanation of the root cause]

**Why This Occurs:**
[Explanation of the underlying issue]

**Code Location:**
```
[File path:line number]
[Relevant code snippet showing the issue]
```

### Related Issues

- [Any related issues or patterns]

## Impact Assessment

**Scope:**
- [How widespread is this?]

**Affected Features:**
- [List affected features]

**Severity Justification:**
[Why this severity level]

**Results Impact:**
[Which cases/configurations give wrong results today; whether the fix will change default results]

## Proposed Fix

### Fix Strategy

[High-level approach to fixing]

### Files to Modify

1. **[file-path]**
   - Changes: [What needs to change]
   - Reason: [Why this change fixes it]

2. **[file-path]**
   - Changes: [What needs to change]
   - Reason: [Why this change fixes it]

### Alternative Approaches

[Other possible solutions and why the proposed approach is better]

### Risks and Considerations

- [Any risks with this fix]
- [Side effects to watch for]
- [Breaking changes if any]

### Testing Requirements

**Test Cases Needed:**
1. [Test case 1 - verify fix works]
2. [Test case 2 - verify no regression]
3. [Test case 3 - edge cases]

**Validation:**
- Reproduction script/input deck and expected outcome after the fix
- `validate` skill suites to run (and `--omp` if the `pandf` tree or `ppp/` is involved)
- Expected change in default results (none / named cases)

## Implementation Plan

[Brief overview of implementation steps]

This RCA document should be used by the `implement-fix` skill.

## Next Steps

1. Review this RCA document
2. Run the `implement-fix` skill with issue #$ARGUMENTS to implement the fix
3. Run the `commit` skill after implementation complete
```

## Publish the RCA

The local file is lost with the worktree, so give it a lasting copy right away:

- **The issue maps to a Jira ticket** (the user or the issue names the key): `ticket-page <KEY> publish --rca
  .claude/work/issue-$ARGUMENTS/rca.md`. It mirrors the RCA under `## RCA` on the ticket's page (or posts a short
  `PIV record: plan` Jira comment when the epic has no PRD page). Pass on `--no-tracker` / `--tracker-dry-run`.
- **A GitHub issue only:** post the RCA as a comment on the issue, where the issue lives: `gh issue comment
  $ARGUMENTS [-R LLNL/UEDGE] --body-file <file>`, the file being the RCA preceded by one line, "RCA written by an
  agent (rca skill) for the fix on branch `<branch>`; not reviewed yet." Build that file through the ticket-page
  helper first, as a page entry is: `uv run .claude/skills/ticket-page/ticket_page.py sanitize --repo <worktree>
  --max-chars 60000 < <header + rca> > <scratch>/rca-comment.md`. It replaces local absolute paths with placeholders,
  refuses secret-like strings (exit 1: rewrite the RCA, never post the raw file) and stays under GitHub's 65 536
  character comment limit (exit 1 over 60 000: shorten it). Posting is a public write: when the issue
  lives in a repository the user doesn't own (`LLNL/UEDGE` upstream), ask the user first. If they decline or `gh`
  fails, say plainly in the output that the RCA exists only in this worktree and will be lost with it, and suggest
  putting its root cause and fix strategy in the PR description.

Report which of these happened (page URL, comment URL, or "local only").
