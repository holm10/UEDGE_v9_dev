# Review: close-epic skill (AI-layer change) - implementation round 1

Branch `feature/v9-ai-close-epic`, commit `2a87c61` on `origin/v9-develop` (`3865c79`). Worktree
`/Users/holma/Documents/uedge/src/uedge-wt/ai-close-epic`.

Note: this report sits under `docs/reviews/`, which `change_kind.py` treats as an **artifact** path. An AI-layer
branch may not carry artifacts, so don't commit this report on `feature/v9-ai-close-epic`. Keep it uncommitted, or
commit it on a planning branch the way the earlier AI-layer review reports were.

## Verdict

**REVISE**

## Summary

The skill does what the owner asked. It gathers the epic's tickets, PRD, breakdown, progress log, reviews and
comments into a record with sections for changes, results, decisions, discussion, deviations and open items. It
publishes the record under the PRD and closes the epic only when the owner says yes. Children are never transitioned,
and nothing is published before the review and the owner's confirmation. `--dry-run` uses an allowlist of
Atlassian reads plus an explicit ban on repo writes; the AIUE-8 dry run left every worktree clean. The wiring
(`CLAUDE.md`, `spec`, `branching.md`) is accurate, `change_kind.py --range` is OK and `check_context_refs.py
--changed` is clean.

Two defects block it:

- **Merged tickets.** The git recipe that finds a ticket's commits, diff, review records and default results returns
  *empty* for a ticket that has been merged. Merged tickets are the normal case at close-out, so the record would say
  "no compiled source changed" and "no review" for merged Fortran tickets. The AIUE-8 dry run never hit this path,
  because nothing in that epic is merged.
- **The review gate can't see Jira or Confluence.** The `closeout` reviewer stage is told to check Jira states,
  comments and decision attribution, but the `uedge-reviewer` agent has no Atlassian tools.

Two majors concern the final status of an epic closed with accepted-open items, and decision attribution when the
author field can't be trusted.

The conflict with `feature/v9-ai-adversarial-ticket-review` is textual only. The two branches are compatible in
substance, and the fix is to keep both sides (m7).

## Findings

### BLOCKER

**I1-B1 - Merged (and deleted, squashed or rebased) ticket branches produce an empty, false record**
(`.claude/skills/close-epic/SKILL.md:124-162`)

*Problem.* For a merged branch, the base rule (l.130-133) falls back to `origin/v9-develop`. The branch tip is then
an ancestor of the base, so every command the skill uses comes back empty:

- `git log <base>..<branch>`
- `git diff --shortstat` and `--dirstat` on `<base>...<branch>`
- `git diff --name-status <base>...<branch> -- docs .claude/plans ...`, the step that finds the reviews, RCAs and
  validation records (l.142-147)
- the default-results check `git diff --name-only <base>...<branch>` (l.152-154)

Each consequence is a wrong claim in the record:

- l.154 then writes **"no compiled source changed"**, a wrong default-results claim for a merged Fortran ticket. The
  closeout stage itself rates that MAJOR.
- The ticket gets no review verdict and no records.
- If the branch was deleted after the merge (GitHub's auto-delete, or cleanup), `git branch -a --list` finds nothing.
  The ticket drops to "Children with no branch ... Jira state only" (l.162), and the "What changed" section loses it.
- If GitHub "Squash" or "Rebase and merge" is used, `git merge-base --is-ancestor` reports **not merged** for
  delivered work, because those methods create new commits.

*Evidence.* `feature/v9-ai-layer` was merged by PR #1 (`0fac655`):

- `git diff --shortstat origin/v9-develop...feature/v9-ai-layer` prints nothing, and `git log --oneline
  origin/v9-develop..feature/v9-ai-layer | wc -l` gives `0`.
- The real change, `git diff --shortstat 0fac655^1 0fac655`, is `44 files changed, 4910 insertions(+)`.
- The skill's own merge-commit recipe (l.138) finds `0fac655` correctly; the diff steps just never use it.

*Acceptance.*

- For a merged ticket, the skill takes its commits, diff, records and default results from the merge
  (`<merge>^1..<merge>`, or the PR's merge commit or the squash commit from `gh pr view --json mergeCommit,state`).
- It finds merged tickets whose branches are gone (merge commits or PRs that mention the key, e.g.
  `git log origin/v9-develop --merges --grep '<KEY>-'` or `gh pr list --state merged --search <KEY>`).
- It treats "not an ancestor, but the PR is MERGED" as merged.
- A walk-through on `feature/v9-ai-layer` (or any merged branch) gives its real diffstat and records.

**I1-B2 - The `closeout` reviewer can't read Jira or Confluence, so the gate can't do the checks it promises**
(`.claude/agents/uedge-reviewer.md:4`, `:69-91`; `SKILL.md:22`, `:258-268`)

*Problem.* The agent frontmatter is `tools: Read, Grep, Glob, Bash, Write, WebSearch, WebFetch`, with no
`mcp__atlassian__*` tools. Several closeout checks need Atlassian reads:

- check 1: "Jira states"
- check 3: grep "the comments" for open items
- check 4: decision attribution, whose sources are mostly Jira and Confluence comments
- the skill's Step 5 hands the reviewer "the sources it can check: cloudId, PRD and breakdown page ids"

`WebFetch` can't help, because Atlassian pages need authentication. So every Jira or Confluence claim in the record
(states, comment ids, the PRD criteria text when it is read from Confluence, Confluence discussion) passes the gate
on the author's word. Yet the skill's second rule says "Nothing reaches Confluence without passing an adversarial
review".

*Evidence.* This review runs as `uedge-reviewer` and was asked to spot-check claims against Jira cloudId
`710f4b18-...`. It has no Atlassian tool and couldn't check any Jira claim in the dry-run draft (see "What was
checked").

*Acceptance.* The closeout reviewer can read the Atlassian sources. One option is to add the read-only tools to the
frontmatter: `getAccessibleAtlassianResources`, `getJiraIssue`, `searchJiraIssuesUsingJql`,
`getTransitionsForJiraIssue`, `getConfluencePage`, `getConfluencePageDescendants`,
`getConfluencePageFooterComments`, `getConfluencePageInlineComments` and `searchConfluenceUsingCql`. Listing only
reads also makes "never write to Jira, Confluence" hold by tooling rather than by prose. A dedicated read-only
closeout agent would also work. If the owner prefers neither, the stage must at least list every Jira or Confluence
claim under "Not independently verified", and the skill must say plainly that the gate covers git-sourced claims
only.

### MAJOR

**I1-M1 - No final status for an epic closed with accepted-open or deferred items**
(`SKILL.md:203-206`, `:220-221`, `:286`, `:308`; `uedge-reviewer.md:88-89`)

*Problem.* The status line allows only `Complete | Close-out draft - epic not complete (<n> open items) | Dry run`.
Reviewer check 6 says anything not fully complete "must say Close-out draft". Now take the normal ending, where the
owner answers (a) "close anyway" or (b) "defer to a follow-up" for every open item and says yes to Done. The published
permanent record and the epic comment ("Status: draft, n open items") then still read "Close-out draft - epic not
complete", on an epic that is Done. That contradicts the owner's goal to "close it all out". Step 6 also says "apply
the answers to ... status line" without saying what the line becomes.

*Acceptance.* There is a defined status (and epic-comment wording) for "Closed by the owner on <date>; n items
accepted-open, m deferred to <KEYs>". Reviewer check 6 allows it once owner answers are recorded for every open item.
The draft or complete distinction stays for the pre-answer record.

**I1-M2 - Attribution has no rule for the ambiguous case, and the owner never confirms what is attributed to them**
(`SKILL.md:91-93`, `:276-289`; `uedge-reviewer.md:83-86`)

*Problem.* The skill rightly says the author field is useless, because agents post as the owner. The dry run
confirms it (draft l.183-185). But "attribute by content and the progress log" leaves the common case open: a Jira
or Confluence comment with no marker such as "unattended run" or "for the owner". The record then has to guess,
either crediting an agent statement to the owner (a BLOCKER under check 4) or discarding a real owner statement. The
reviewer can't settle it either (I1-B2, and the comment metadata carries no signal). The record's most
consequential column, the "who" column for owner decisions, rests on this.

*Acceptance.*

- Statements whose authorship the sources can't prove are marked "attribution unverified (posted via owner
  account)".
- They are never listed as owner decisions until confirmed.
- Step 6 shows the owner every decision credited to them, and every unverified one, for confirmation in the same
  message.
- Optional, as an `ai-layer` follow-up rather than on this branch: a convention that agent-posted comments carry a
  fixed prefix.

### MINOR

**I1-m1 - The PRD local-copy shortcut contradicts "Confluence wins"** (`SKILL.md:102-105`). The rule says to read the
local copy when the page's `lastModified` is "within minutes" of the copy's commit. That is a heuristic, while the
skill's own line 118 and `spec` both say Confluence is the source of truth. An owner edit made shortly after publish
would be missed, and the success criteria are the basis of the completion check. One `getConfluencePage` call
removes the risk. *Acceptance:* always read the page, or diff it against the local copy.

**I1-m2 - Branch and worktree discovery patterns** (`SKILL.md:125-128`). `grep -E '/<KEY>(-|$)'` on `git worktree
list` output never matches a worktree directory named exactly `<KEY>`, because the path is followed by spaces, not
end of line. Verified: `/AIUE-47` and `/AIUE-5` are not matched, only `/AIUE-47-serial*`. That is harmless for
worktrees with a branch, but a detached prototype in `uedge-wt/<KEY>` would be missed. `git branch -a --list` also
returns both local and `remotes/origin/` copies once a branch is pushed, so the skill doesn't say which tip to report.
*Acceptance:* use `git worktree list --porcelain` (or `'/<KEY>(-[^ ]*)? '`), and use one tip per branch, with
local-ahead-of-remote noted.

**I1-m3 - The default-results file filter misses build and run-time inputs** (`SKILL.md:152-154`). The regex
`\.(m|v|F90|F|f|c|h)$`, `setup.py`, `Makefile*`, `src/uedge/` doesn't catch:

- `pyproject.toml` (build flags)
- `rates/` and other data files (`*.dat`)
- `*.inc` and `com/mpivarsmod.F.in`
- the `*.py` files in package directories

A change to any of these would be written up as "no compiled source changed". *Acceptance:* widen the filter, or
invert it (only `docs/`, `.claude/`, `tests/` and `*.md` count as "no compiled or run-time change").

**I1-m4 - The epic-comment update path is unverified** (`SKILL.md:304-305`). The skill assumes
`addCommentToJiraIssue` with a `commentId` edits an existing comment. A Rovo MCP community report (Aug 2026)
describes `commentId` as "ID of an existing comment to update", but also says that updating a public comment fails
because `commentVisibility` can't express "public". Atlassian's current tool list names it
`addOrEditJiraIssueComment`. `getConfluenceCommentChildren` (allowlist l.55) and `createIssueLink` (ban list l.57)
appear in no other skill, and I couldn't check them against the installed server. The dry-run rule is an allowlist,
so a renamed *write* tool is still excluded, which is good. *Acceptance:* confirm the installed schema; if the update
fails, add a new comment that references the old one instead of stopping.

**I1-m5 - The closeout checks don't name the "unmerged presented as delivered" failure** (`uedge-reviewer.md:69-91`;
`SKILL.md:229`). The skill has a "Met (on unmerged branches)" class, but the reviewer's checks don't require
it. Its "what it delivered" heading invites overclaiming: the dry-run draft writes "Delivered:" for every local,
unmerged branch. *Acceptance:*

- The closeout checks include "Met, or delivered, only for merged work, unless it is labelled on unmerged branches".
- "Partly met" names the missing parts.
- The contradictions between snapshots and live state that Step 1 requires are listed.
- The template says "What the branch contains" for unmerged tickets.

**I1-m6 - Small procedural gaps.** Location and fix for each:

- `SKILL.md:284`: Step 6 question 3 is offered "only if ... no item is keep the epic open", but it is asked in the
  same message as question 1. *Fix:* make it conditional on the answers.
- `SKILL.md:287-289`: the parent of a follow-up `createJiraIssue` is not specified. Creating it under the epic being
  closed leaves a Done epic with an open child. *Fix:* say it goes to no parent, or to an epic the owner names.
- `SKILL.md:219-221`, `:302`: Step 7.2 fills the close-out page id into "the repo copy's metadata line", which has no
  field for it. *Fix:* add the field.
- `SKILL.md:33`: the dry-run fallback directory is `close-epic/`, but the primary is `closeout/`. *Fix:* use one name.
- Metadata block: create-prd records finding counts in its metadata; close-epic only "VERDICT (round N)". *Fix:*
  align the two.

**I1-m7 - Conflict with `feature/v9-ai-adversarial-ticket-review`.** This is guidance, not a defect of this branch.
`git merge-tree --write-tree` reports content conflicts in `.claude/agents/uedge-reviewer.md` and `CLAUDE.md`. The
two branches agree in substance; each adds a stage and an ID prefix, and they edit the same lines. Resolve by keeping
both sides:

1. **`CLAUDE.md`.** Keep that branch's "Refactor ..." and "Bug ..." rows and this branch's "Large epics" row. The
   lines are only adjacent, there is no semantic overlap.
2. **Reviewer `description`.** List create-prd → PRD, end-to-end-feature/plan-feature/execute/implement-fix → plans
   and implementations, and close-epic → close-out records.
3. **Stage list.** `spec`, `plan`, `implementation`, `prd`, `closeout`. Keep that branch's "reference" bullet.
4. **Stage sections.** Keep both new sections between "PRD stage" and "implementation stage".
5. **Finding-ID examples.** `S`, `P`, `L`, `I`, `C`; they are all distinct, and lower-case `m` is used for minors on
   both sides.
6. **Output.** Take that branch's "absolute path the prompt gives" wording and its "Not independently verified
   (environment)" section, and add this branch's close-out naming example. That section is also the natural place
   for whatever Atlassian claims stay unverifiable after I1-B2.

Neither branch's skills depend on the other's text. close-epic's `docs/reviews/<KEY>-*` and `-response` reading
matches the `<KEY>-<stage>-round<N>[-response].md` names `end-to-end-feature` uses on that branch. No AI-layer doc
cites either file by line number, so the merge moves no `check_context_refs` lock.

## Status of previous findings

Round 1; none.

## What was checked and how

- **Diff.** `git diff origin/v9-develop..HEAD`: 5 files, +370/-8. The whole `SKILL.md` was read, along with the
  reviewer, `branching.md`, `spec` and `CLAUDE.md` hunks. Compared against `create-prd` (Step 5 loop and 3-round cap,
  Step 6 precondition "run one more round", template sections §9/§11/§15) and `spec` (Confluence wins, PRD-comment
  fallback). The section numbers the skill cites match the `create-prd` template.
- **Branch policy and drift.** `uv run .claude/hooks/change_kind.py --range origin/v9-develop..HEAD` gave `ai`
  branch, 5 process paths, `OK`, exit 0. `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop`
  gave `OK`, exit 0. Read `change_kind.py`: `docs/specs/` and `docs/reviews/` are artifact paths; a
  `feature/v9-<EPIC>-planning` branch classifies as `ticket`, so the record and its reviews may be committed there.
  The `branching.md` row is consistent with that.
- **Other references.** `grep` found no other skill index that should list `close-epic`.
- **Merged-branch behaviour (I1-B1).** On `feature/v9-ai-layer`: the skill's recipe gives an empty shortstat and 0
  commits; the merge-commit diff `0fac655^1..0fac655` gives 44 files / +4910.
- **Discovery patterns (I1-m2).** Ran `git worktree list | grep -E '/AIUE-47(-|$)'` and `/AIUE-5(-|$)`, and
  `git branch -a --list '*v9-AIUE-5-*'`.
- **Reviewer tools (I1-B2).** Frontmatter line 4; this session has no Atlassian tool.
- **MCP tool names.** Searched the repo for the `mcp__atlassian__*` names in use. Checked Atlassian's supported-tools
  page and the community post on `addCommentToJiraIssue` `commentId`.
- **Merge conflict.** `git merge-tree --write-tree --name-only HEAD feature/v9-ai-adversarial-ticket-review` lists
  both conflicting files. Read that branch's diff of both files and its `end-to-end-feature` report naming.
- **Dry-run write safety.** `git status --short` is clean in the `AIUE-8-planning`, `ai-close-epic`, `AIUE-55` and
  `AIUE-56` worktrees. The helper `branches.sh` and the draft are in the scratchpad.
- **Dry-run draft spot-checks** against git. Jira and Confluence claims could not be checked (I1-B2):
  1. All 11 ticket tips, bases (stack parents), commit counts and shortstats in draft §3: re-run with the draft's
     script. All match (e.g. AIUE-47 `e71fafc`, 14 commits, 11 files +2234; AIUE-55 base AIUE-54, `01e2d8e`).
  2. AIUE-56 validation: `docs/reviews/AIUE-56-validation.txt:6` reads `RESULT: AGREE (bitwise identical; complete
     gate)  [pairs serial+omp0, cases all (42)]`; l.81 has ratio 0.995; l.124-127 show Te box 1/30 and full 0/30.
     Matches draft rows 1, 2 and 6.
  3. AIUE-54 reviews: round 1 and round 2 both `**REVISE**`. Matches.
  4. AIUE-55: rounds 1-3 `REVISE`, round 4 `APPROVE` (recorded in `3bf736c`), then `01e2d8e` (+31 lines in the RCA)
     after the approval. The "unreviewed addendum" claim holds.
  5. AIUE-46 default results: no compiled file in the diff, so the claim holds. But the draft's area list ("`tests/`,
     `docs/`, `.claude/` only") omits `CLAUDE.md`, which the branch also changes. That is a small inaccuracy of the
     kind the gate exists to catch.
  6. PRD commit time: `3865c79` was committed at 2026-10-14T19:27:33-07:00 (02:27:33Z), as the draft says. The
     planning tip has since moved from `118d412` to `82b5be8` (10:31, after the draft); that is a snapshot, not an
     error.

  The draft is good evidence that Steps 1-4 and the dry-run appendix work for an **unmerged** epic. It is no evidence
  for the merged path (I1-B1).
- **Not run.** No Atlassian calls (no tool), no builds, no commits.
