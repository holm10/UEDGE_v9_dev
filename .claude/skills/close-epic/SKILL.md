---
name: close-epic
description: Closes out a Jira epic. Gathers everything the epic produced (Jira epic and children with comments, the PRD and its Confluence child pages and comments - breakdown, PRD reviews, progress log - the per-ticket pages under "Ticket plans" for the epic with their plans, reviews, validation results and decisions, every ticket branch or merge and its git history, physics specs, and a legacy planning branch if one exists), saves a local snapshot of the Jira and Confluence sources, checks it against the PRD's success criteria, and writes a detailed close-out record of what changed, the results, the decisions and who took them, the discussion, deviations and deferred work. The record passes an adversarial uedge-reviewer gate, is published as a child page of the PRD and linked from the epic. The epic moves to Done only when the owner confirms. Use when an epic's tickets are finished, or with --dry-run for a read-only draft of an epic in progress.
argument-hint: "<jira-epic-key> [--dry-run]"
---

# Close Epic: record what an epic did, then close it

## Overview

The last step of the epic flow: `create-prd` → `spec` → one PIV loop per ticket → **`close-epic`**. An epic's
history is spread over Jira (status, comments), Confluence (the PRD and its children: `PRD reviews`, the breakdown,
`Progress`, the ticket pages with each ticket's plan, reviews, validation results and decisions; comments) and git
(one branch or merge per ticket, with its commits and physics specs). Ticket and epic working documents are never
committed (`.claude/context/branching.md`), so the Confluence pages are where plans, reviews and validation records
are found; epics started before that rule also left them on a planning branch and in ticket branches (legacy sources,
read with `git show`).
This skill collects it into one record that someone who wasn't there can read: what the epic set out to do, what it
changed, what it measured, what was decided by whom and why, and what is left.

Four rules hold throughout:

- **The skill reports; the owner decides.** It never marks a criterion met, a ticket done or an owner decision taken
  on its own judgement. Every "met" points to a record that shows it. When something is not done, the owner chooses
  per item: close anyway, defer, or keep the epic open.
- **Every claim has a checkable source.** Git claims cite a commit or `branch:path`; Jira and Confluence claims cite
  the sources snapshot (Step 1), because the reviewer has no Atlassian access.
- **Nothing reaches Confluence without passing an adversarial review** (Step 5), the same gate as `create-prd`.
- **The epic moves to Done only on the owner's explicit confirmation** (Step 7). Children are never transitioned:
  the record reports their states.

## Configuration

| Setting | Value |
|---|---|
| Record (local working copy) | `.claude/work/<EPIC-KEY>/closeout.md` in the current checkout |
| Sources snapshot (local) | `.claude/work/<EPIC-KEY>/closeout-sources/` |
| Review reports (local) | `.claude/work/<EPIC-KEY>/reviews/<EPIC-KEY>-closeout-round<N>.md` and `-response.md` |
| Confluence page | child of the PRD page, title `Close-out: <EPIC-KEY> - <epic summary without trailing period>`: the record's lasting home |
| Dry-run output | `<scratch>/closeout/<EPIC-KEY>-closeout-draft.md` and `<scratch>/closeout/<EPIC-KEY>-closeout-sources/`, where `<scratch>` is the session scratchpad directory, or `${TMPDIR:-/tmp}` if there is none |
| Max review rounds before escalating to the owner | 3 |

The local files are working documents: gitignored, never committed, on any branch (`change_kind.py` refuses them).
The record's lasting copy is its Confluence page; the review rounds are summarised in its section 10; the snapshot
stays local, and section 10 lists what it holds (read times, issue `updated` values, page ids and versions, comment
ids) so the sources can be read again. Keep the local files until the page is published.

## Input

Parse `$ARGUMENTS`:

- **Epic key** (required). A token matching `^[A-Za-z][A-Za-z0-9]*-?[0-9]+$`, normalised to upper case with a hyphen
  before the number (`aiue8` → `AIUE-8`). Without one, stop and ask for it.
- **`--dry-run`** (optional). Read-only rehearsal; see below.

### Dry-run mode

`--dry-run` runs Steps 1–4 for real and Steps 6–7 as a description only. It exists to test this skill and to show
the owner a draft of an epic still in progress. In a dry run:

- **No external writes.** The only Atlassian calls allowed are reads: `getAccessibleAtlassianResources`,
  `getJiraIssue`, `searchJiraIssuesUsingJql`, `getTransitionsForJiraIssue`, `getConfluencePage`,
  `getConfluencePageDescendants`, `getConfluencePageFooterComments`, `getConfluencePageInlineComments`,
  `getConfluenceCommentChildren`, `searchConfluenceUsingCql`, `getConfluenceSpaces`. Any other Atlassian tool is
  forbidden, in particular `createConfluencePage`, `updateConfluencePage`, `addCommentToJiraIssue`,
  `transitionJiraIssue`, `editJiraIssue`, `createJiraIssue` and every comment-creating tool.
- **No repo writes.** No file in any worktree is created or changed (not even in `.claude/work/`), nothing is staged
  or committed. `git fetch` is
  allowed (it only updates remote-tracking refs). Read other branches with `git show <rev>:<path>`. Helper scripts,
  the snapshot and the draft go in the dry-run output directory, never in the repo.
- The draft's status is `Dry run - not reviewed, not published`.
- The adversarial review (Step 5) runs only if the user asks; the reviewer then writes its report next to the draft.
- Step 6 lists the questions it *would* ask the owner, without waiting for answers. Step 7 lists what it *would*
  do: page title, space and parent id, create or update, add or update the epic comment, the Done transition id.
  Put both lists in a final appendix of the draft, "Dry run: what a real run would do", with each value's source in
  the snapshot, and in the output.

## Process

### Step 1 — Gather (read-only) and snapshot

Make independent calls in parallel. Keep notes of *where* each fact came from; the record cites them.

**The sources snapshot.** Write each Atlassian read you use into the snapshot directory as you go, verbatim in the
fields you use (no paraphrase; avatar and `self` URLs may be dropped):

| File | Content |
|---|---|
| `jira-epic.json` | the epic (summary, status, resolution, updated, comments) |
| `jira-children.json` | every child: key, summary, type, status and status category, resolution, created, updated |
| `jira-comments.md` | every child comment used: issue key, comment id, created, body verbatim (markdown avoids JSON-escaping long bodies) |
| `jira-transitions.json` | the epic's transitions (id, name, target status category) |
| `confluence-pages.json` | PRD, `PRD reviews: <EPIC>`, breakdown, `Progress: <EPIC>`, the `Ticket plans: <EPIC>` container and its ticket pages (and any existing close-out page): id, title, spaceId, parentId, version number, version message, createdAt / lastModified |
| `confluence-ticket-pages.md` | per ticket page: page id, version, and the header, the Ticket section (scope as filed by `spec`, absent on pages made before `spec` created them) and the four log sections verbatim (Progress, Validation, Reviews, Findings and decisions). The Plan section is left out unless a criterion depends on it (then quote the part used): record the publish date and sha256 the header cites (older pages cite a plan commit instead) |
| `confluence-prd.md`, `confluence-prd-reviews.md`, `confluence-breakdown.md`, `confluence-progress.md` | the page bodies as read (each page is the only copy: there is no repo copy to compare with) |
| `confluence-comments.json` | footer and inline comments (open and resolved, with replies) on those pages, or `[]` |
| `snapshot.md` | header: UTC time of the gather; `origin/v9-develop` sha; a legacy planning branch tip, if one exists; every ticket branch, merge commit or prototype worktree with its tip and `git status --short` line count; each Jira issue's `updated` |

The record states its snapshot (section 10). Facts that change after it are the reviewer's to flag, not errors.

**Jira.**

1. `mcp__atlassian__getAccessibleAtlassianResources` → the `cloudId` of the site with Jira scopes. Reuse it.
2. `mcp__atlassian__getJiraIssue` on the epic, `responseContentFormat: "markdown"`, `fields: ["summary",
   "description", "issuetype", "project", "status", "resolution", "created", "updated", "comment"]`. If it doesn't
   exist, stop. If its type isn't `Epic`, ask whether to continue.
3. `mcp__atlassian__searchJiraIssuesUsingJql` with `parent = <EPIC-KEY> ORDER BY key ASC`, `fields: ["summary",
   "status", "resolution", "issuetype", "labels", "created", "updated"]`, `maxResults: 100` (page with
   `nextPageToken` if there are more).
4. The children's comments in **one** call: the same JQL with `fields: ["comment", "issuelinks"]` and
   `responseContentFormat: "markdown"`. Read a child's description (`getJiraIssue`) only when its acceptance
   criteria matter and the breakdown doesn't give them.
5. `getTransitionsForJiraIssue` on the epic: the id of the transition whose target status category is Done.

**Who said it.** Agents post Jira comments and Confluence edits through the owner's account, so the author field
shows the owner either way and proves nothing. Attribute a statement as follows:

| Attribution | When |
|---|---|
| **Owner** | a source records it as the owner's: the PRD's binding decisions, a progress-log line that says the owner decided, approved, asked or authorised, an owner reply in the conversation, or the owner's confirmation in Step 6 |
| **Agent** | the source marks it as the agent's ("unattended run", "proposed", "for the owner", a response file, a commit) |
| **Reviewer** | a review report |
| **Attribution unverified (posted via owner account)** | anything else, including passive wording ("Docker started", "workaround added") and Confluence version messages |

An unverified statement is never listed as an owner decision. Step 6 asks the owner to confirm each one.

**Confluence.**

1. Find the PRD: `mcp__atlassian__searchConfluenceUsingCql` with `type = page AND title ~ "PRD: <EPIC-KEY>"`. Keep
   only titles that are exactly `PRD: <EPIC-KEY>` or start with `PRD: <EPIC-KEY> - `, so `AIUE-8` does not match
   `AIUE-80`. If none, fall back to the epic comment `PRD: ... (Confluence page id ...)` that `create-prd` posts.
   No PRD at all → continue, but Step 3 can only use the breakdown and the tickets' own acceptance criteria; say so.
2. `getConfluencePage` on the PRD (`contentFormat: "markdown"`). The page is the PRD (as in `spec`; a legacy
   planning branch's copy, if any, is history only). Extract: the success criteria (section 11),
   the binding decisions and assumptions (appendix), the default-results statement (section 9), the out-of-scope
   list, the review history, and the MINORs the PRD carried to the tickets.
3. `getConfluencePageDescendants` on the PRD → the breakdown page (`Spec: ... - Ticket Breakdown`), `PRD reviews:
   <EPIC-KEY>`, `Progress: <EPIC-KEY>`, the `Ticket plans: <EPIC-KEY>` container (exact titles) and any existing
   `Close-out: <EPIC-KEY>` page (same exact-prefix rule). `getConfluencePage` on the breakdown, the reviews page and
   the progress page. The progress page is usually the best narrative source; read all of it, including every
   "owner decisions" list and every owner follow-up section.
4. **Ticket pages** (written by the `ticket-page` skill): `searchConfluenceUsingCql` with `type = page AND parent =
   <container id>`, following `next` until every child is listed → one `Plan: <KEY> - …` page per ticket, created by
   `spec` when the ticket was filed (or by `plan-feature` for a ticket filed otherwise), mirroring its plan, or its RCA
   for an `implement-fix` ticket. `getConfluencePage` (`contentFormat: "markdown"`) on each. A Plan section that is
   still the placeholder means only "plan not mirrored": never infer "never planned" from it. On a page with a
   `**Backfilled:**` header field (made after the ticket was filed), or for a ticket whose Jira status is beyond To
   Do, look for a plan in the ticket's Jira comments and, for legacy tickets, committed on its branch, and write
   "plan not mirrored on the ticket page"; only a To Do ticket with no plan anywhere counts as not planned. A ticket moved in from another epic keeps its page under that epic's
   container: for each child with no page here, take the id from its `Ticket page:`/`Plan page:` link comment,
   confirm it with CQL `id = <id>`, and include that page, noting where it lives. Their log sections are
   **the** record of each ticket's progress, validation results, review rounds (verdict, findings, responses) and
   decisions: the working files they summarise were never committed. Cite the page entry (page id, version, section,
   date) for those claims and git (commit, `rev:path`) for code claims; for legacy tickets, the committed reports are
   a second source. A page entry marked Owner was written by an agent: it counts as an owner decision only when the
   source it cites does (the attribution table above). Tickets without an epic PRD page keep the same log as `PIV record:`
   comments on the Jira ticket, which step 4 of Jira already reads. A ticket with work but no page or PIV comments
   is noted in section 10, not an open item.
5. `getConfluencePageFooterComments` and `getConfluencePageInlineComments` (`resolutionStatus` open **and**
   resolved, `includeReplies: true`) on the PRD, the breakdown page and the ticket pages.

**Legacy planning branch** (epics started before working documents left git): if `feature/v9-<EPIC-KEY>-planning`
exists (`git branch -a --list '*v9-<EPIC-KEY>-planning'`), or its archive tag does (`git ls-remote --tags origin
'archive/<EPIC-KEY>-planning'`; AIUE-5, AIUE-8 and AIUE-9 have one), or the tag `archive/AIUE-8-docs` holds the epic's files,
read with `git show` the PRD copy (`docs/prds/<EPIC-KEY>-*.md`), the breakdown and the progress log
(`docs/specs/*.md`) and the review reports (`docs/reviews/<EPIC-KEY>-*`) as historical sources, and read all of a
progress log found there as for the progress page. Newer epics have no planning branch; nothing is written to one.

**Tickets: find each child's work.** `git fetch origin` first. Compare against `origin/v9-develop`, never the local
`v9-develop` (it can be behind). For each child key, in this order:

1. **Merged.** A merge or squash commit on `origin/v9-develop` that carries the key:
   `git log --first-parent --format='%H %s' origin/v9-develop | grep -E '<KEY>([^0-9]|$)'` (PR merge subjects name
   the branch, `Merge pull request #N from <owner>/feature/v9-<KEY>-<slug>`; squash subjects end in `(#N)` and usually
   name the key). With `gh`: `gh pr list --state merged --search '<KEY>' --json number,headRefName,mergeCommit,mergedAt`.
   A PR whose state is MERGED counts as merged even when the branch tip is not an ancestor (squash, rebase).
   **Without `gh`**, also try, in order:
   - the key in GitHub's humanised squash title or in a commit body: `git log --first-parent -E
     --grep='<PROJ>[- ]<N>([^0-9]|$)' --format='%H %s' origin/v9-develop` (searches subject and body, keeps the hash), and a PR number or branch name the progress log or a
     Jira comment gives;
   - patch identity, when the branch still exists: `git cherry origin/v9-develop <branch>` (every line `-` means each
     commit landed, as in a rebase merge); for a squash, compare
     `git diff <parent>...<branch> | git patch-id --stable` with `git show <S> | git patch-id --stable` for the
     first-parent commits after the branch's fork point.

   If none finds it, the merge is **undeterminable**: say so for that child, list "merge not located" as an open item
   when Jira says Done or the branch is gone, and state the limitation in section 10.
2. **Branch.** `git branch --list '*v9-<KEY>-*'` (local) and `git branch -r --list 'origin/*v9-<KEY>-*'`. The
   trailing hyphen keeps `AIUE-5` from matching `AIUE-50`. Drop `-planning` and `-integration` branches, which belong
   to an epic of that key. Report one tip per branch: the local one, noting if it is ahead of or behind its
   `origin/` copy. A branch whose tip is an ancestor of `origin/v9-develop` is merged; find its merge with
   `git rev-list --first-parent --merges --ancestry-path <tip>..origin/v9-develop | tail -1`.
3. **Prototype worktrees.** `git worktree list --porcelain`, keeping `worktree` paths whose last component is
   `<KEY>` or starts with `<KEY>-`. For each: HEAD, branch or detached, and `git -C <path> status --short`.
   Uncommitted changes in a prototype are an open item (they exist nowhere else; working documents in its
   `.claude/work/` are not, but entries still queued in its `ticket-page` outbox are: they are not on the page), and
   so are commits reachable only
   from a detached HEAD (`git branch -a --contains <HEAD>` empty); list those commits (`git log --oneline
   <merge-base with origin/v9-develop>..<HEAD>`). Say what each worktree is when a record names it (a negative
   control or seeded race is deliberate; its open item is only the clean-up). Before writing "not named in a
   record", grep the records for the worktree's name and its HEAD's short sha: the snapshot's page bodies and
   comments (`grep -rn -e '<name>' -e '<sha7>' <snapshot dir>`), and, for legacy records, `git grep -n -e '<name>' -e
   '<sha7>' <rev> -- docs .claude/plans` for a legacy planning tip and every ticket tip.

   Agent work in progress outside the repo (a session scratchpad, a running study) is **in progress, not a source**:
   name it in section 8 if a record mentions it, and never cite its numbers as evidence.

Then, per child, the **range** that holds its own work:

| Case | Commits | Diff | Records read from |
|---|---|---|---|
| merged by merge commit `M` | `git log --oneline M^1..M^2` | `git diff M^1 M` | `M:<path>` |
| squash or single rebased commit `S` | `S` | `git diff S^ S` | `S:<path>` |
| rebase-merged series | the PR's commits (`gh pr view <N> --json commits`), else the first-parent run carrying the key | first^..last | last commit |
| unmerged branch | `git log --oneline <parent>..<branch>` | `git diff <parent>...<branch>` | `<branch>:<path>` |

**Stacked tickets merged together.** If two children resolve to the same merge or squash commit, or `M^1..M^2`
contains another child's tip, the merge range covers more than one ticket. Then take each child's commits, diff and
records from its own range, `<parent-tip>..<tip>` with the actual-base rule below (tips from the branches, or, if
they are gone, from the snapshot, the progress log or the Jira comments), and note the shared merge in each child's
entry. If the tips can't be recovered, say the range is shared and attribute nothing ticket by ticket.

For an unmerged branch, `<parent>` is the **actual** base from git, not the breakdown's planned `Branch:` line:
the branch with the most commits over `origin/v9-develop` among the epic's other ticket branches, a legacy planning
branch and any AI-layer branch it was based on, whose tip is an ancestor of this branch
(`git merge-base --is-ancestor <other> <branch>`), else `origin/v9-develop`. Record every ticket whose actual base
differs from the breakdown, per ticket, as a deviation.

From the range:

- Size and areas: `--shortstat` and `--dirstat=files,5` on the diff.
- Records the range adds: `--name-status` on the diff limited to `docs`: physics specs (`docs/physics_specs/`) and
  other product documentation. Legacy tickets (before working documents left git) may also add plans, review reports
  and responses, RCAs, execution and system reviews and results files under `docs .claude/plans
  .claude/execution-reports .claude/system-reviews`; read them as a second source (bulk run records, e.g. hundreds of
  JSON files under `docs/rca/<EPIC>-data/records/`, are counted, not read). A document several tickets extend is read
  from the last range in the stack.
- **Reviews:** each round's Reviews entries on the ticket page: the verdict, counts, findings, what the diff range
  reviewed, and the response entry for what was fixed, rebutted, deferred or left. Legacy tickets: the verdict line of
  each committed report (`git show <rev>:<file> | grep -m1 -E '\*\*(APPROVE|REVISE|REJECT)'`) and the response files
  (`grep -inE 'defer|rebut|owner|not done|left for|follow-up|not covered'`). Note approvals that came only after an
  owner-authorised round past the cap.
- **Commits after the approving round.** List every commit after the one the approving Reviews entry names as
  reviewed (legacy: every commit that adds or follows the approving report, including changes committed *together
  with* it, since the reviewer saw the work before them), and give each one class:

  | Class | What it is | Open item? |
  |---|---|---|
  | **Text only** | comments, docs or wording that adds or changes no claim | no |
  | **Requested fix** | a change to a document or record that does what the approving review's own findings asked (cite the finding ids) and no more, e.g. a corrected number or a qualifier the reviewer asked for | no; listed, low risk |
  | **Unreviewed change** | any change to code, tests, data or behaviour (even when a finding asked for it: the `end-to-end-feature` rule requires a new round), or new results or claims nobody asked for | yes |

  To tell a requested fix from an unreviewed change, compare the diff with the findings and the response file: every
  changed claim must trace to a finding.
- **Default results (every ticket gets a line).** If every changed path is under `docs/`, `.claude/`, `tests/`,
  `.github/`, or is `*.md`, `.gitignore`, `.mcp.json`, write "no change to built or run-time code" with the diff as
  the source. Otherwise (sources, `.v`, build files, `pyproject.toml`, `setup.py`, rate or data files, `src/uedge/`,
  package `*.py`), take the statement from the ticket's validation record, validate output, implementation review or
  commit body ("bitwise unchanged on …", "cases X, Y moved because …") and cite it, including the commit it was
  measured on (the ticket page's Validation entries, its implementation Reviews entry, or the commit body). If none
  says, write "not recorded"; never infer it from the diff.
- **Evidence across tickets.** Where a criterion rests on several unmerged tickets (two fixes, a fix and its test
  tool), say whether any record shows them tested together. If not, the criterion is at best **Partly met**, with
  the combined check as the missing part.
- **Status claims in comments are snapshots and summaries.** Jira comments and the progress log quote tips and
  states at the time they were written, and summarise records. Take tips from git, states from Jira, and results
  from the record a comment summarises; list each contradiction in section 10.

Children with no work anywhere are listed with their Jira state only. AI-layer branches the epic produced
(`feature/v9-ai-*` named in the progress log or comments) are listed in section 9 with their state, not as tickets.

### Step 2 — Map the epic

Build one table, one row per child: key, summary, Jira status, merged (commit, PR) or branch with parent and tip,
pushed or local, last review verdict and round, open findings, unreviewed post-APPROVE changes, default results
(sourced). Sort it in the breakdown's merge order if it has one, else by key.

### Step 3 — Check completion

For each PRD success criterion (and, without a PRD, each ticket's acceptance criteria), find the evidence: which
ticket, which record, what it says. Use only these classes:

| Class | Meaning |
|---|---|
| **Met** | a record shows the criterion's own check passing on merged code |
| **Met (on unmerged branches)** | the same, but the code or record is only on unmerged branches; name them |
| **Partly met** | some parts are met; name the parts that aren't |
| **Not met** | a record shows it failing, or the work it needs is not done |
| **No evidence** | nothing in the records shows either way. Never "met" |
| **Superseded** | the owner changed or dropped the criterion; cite the decision |

Criteria the PRD marks as not gating (bonus track, quality indicators, user-experience goals) are classified the same
way but don't decide completeness; the children that carry them still appear below. The PRD's MINORs carried to the
tickets each get a disposition: applied in which ticket, or not found.

Then list everything that is not done (the **open items**):

- each gating criterion whose class is not Met or Superseded, with its class and the missing part;
- children whose status category is not Done;
- ticket work not merged into `v9-develop` (and branches with commits but no PR);
- reviews not ending in APPROVE, and approvals given only on an owner override;
- unreviewed post-APPROVE changes (the third class above);
- deferred review findings, accepted gaps with no ticket, and rebuttals the reviewer didn't accept;
- open owner decisions: every item of every "owner decisions" list in the progress log, the PRD decision table, and
  Jira or Confluence questions to the owner with no answer. An item counts as answered only if a source attributed to
  the owner answers it; an experiment that answers the technical question still needs the owner's acceptance;
- prototype worktrees with uncommitted changes, and commits on no branch;
- merges that could not be located;
- merge conditions recorded on a ticket ("don't merge before …");
- open Confluence inline comments;
- the epic's own Jira state if it disagrees with the work (e.g. still To Do while children are In Review).

**The epic is complete** only if the list above is empty; an unmet gating criterion is on it, so it can't be skipped.
Otherwise write the record as a close-out draft (Step 4); the owner decides each open item in Step 6. A close-out
draft always has at least one open item: if the list is empty while a criterion is unmet, the list is wrong.

### Step 4 — Write the record

Write it to the record path (dry run: the dry-run path). On a real run it is a local working copy in the current
checkout, on any branch: nothing is committed and no branch is needed (`.claude/context/branching.md`). Before
writing a claim,
re-check it against its source (a tip with `git rev-parse`, a count in the record it cites, a Jira state in the
snapshot); the reviewer will.

The status line takes exactly one of:

| Status | When |
|---|---|
| `Dry run - not reviewed, not published` | `--dry-run` |
| `Complete` | Step 3 found the epic complete |
| `Close-out draft - epic not complete (<n> open items)` | n ≥ 1 open items (unmet gating criteria included), before the owner has answered all of them |
| `Closed by the owner on <date> - <a> accepted-open, <d> deferred to <KEYs>` | the owner answered every open item, including every unmet gating criterion, with close anyway or defer, and said yes to Done; a + d equals the number of open items |

An epic the owner keeps open stays at `Close-out draft`.

```markdown
# Close-out: <EPIC-KEY> - <epic summary>

> **Jira epic:** [<EPIC-KEY>](https://<site>/browse/<EPIC-KEY>) · **PRD:** [<title>](<url>) (page <id>) · **Breakdown:** [<title>](<url>) (page <id>) · **This page:** <page id, or "not published">
> **Status:** <one of the four above>
> **Generated by:** close-epic on <date> · **Snapshot:** <UTC time>, `origin/v9-develop` `<sha>` (local, not published; contents in section 10)
> **Adversarial review:** <VERDICT> (round <N>, <B> blocker / <M> major / <m> minor raised in total; rounds in section 10)

## 1. Goal and outcome
   The goal in the PRD's words (2-3 lines); the outcome in 3-5 lines; one line on the completion verdict.
## 2. Acceptance criteria
   Table: criterion · class (Step 3 classes only) · evidence (record + what it shows). Then the disposition of the
   PRD's carried MINORs.
## 3. What changed, per ticket
   One subsection per child in merge order: summary; merged (commit, PR, date) or branch, actual base, tip, "local,
   not merged"; files and areas; **"What it delivered"** for merged work, **"What the branch contains"** for unmerged
   work; default results (changed or not, which reference cases moved, source); review verdict, rounds, open
   findings, post-APPROVE commits (text only, requested fix, or unreviewed change).
## 4. Results
   The key measurements (before/after, rates, timings, gates), each with its source. Quote numbers exactly as the
   record gives them, with units and conditions (case, threads, build, machine load if the record notes it).
## 5. Decisions
   Table: date · decision · who (Owner / Agent / Reviewer / Attribution unverified) · why · source. Open owner
   decisions in a separate list.
## 6. Context and discussion
   The discussions that shaped the work: questions in Jira or Confluence comments, review escalations, rebuttals,
   findings that changed direction. Each with its source and outcome.
## 7. Deviations from the PRD
   What was done differently from the PRD or the breakdown (scope added or dropped, tickets added or rescoped,
   criteria changed, actual bases that differ from the plan, PRD claims that turned out wrong). Each with the reason
   and who agreed to it ("not recorded" if no source says).
## 8. Open and deferred items
   Everything from Step 3's not-done lists, with its source and the owner's choice once given (accepted-open /
   deferred to <KEY> / keeps the epic open).
## 9. AI-layer lessons
   The execution-report and system-review entries on the ticket pages (Findings and decisions; legacy: committed
   reports, by path), AI-layer branches the epic produced and their state, `ai-layer` issues filed, process lessons
   recorded in the progress log. If there are none, say so and recommend `execution-report` → `system-review`.
## 10. Sources
   The snapshot (time, tips, what it holds; it stays local); every record cited (Jira keys and comment ids, page ids,
   versions and sections, `rev:path`, commit hashes); contradictions between sources; records that were missing; the
   review history of this record, round by round (verdict, counts, each finding in one line and its response),
   since the review reports are not kept.
```

Keep it factual and dense; it is a record, not a sales document. No Mermaid (Confluence's markdown import doesn't
render it). Quote owner and reviewer statements briefly and attribute them.

### Step 5 — Adversarial review (required before any Confluence write)

The author of the record (this session) can't review it independently. Spawn a **fresh** `uedge-reviewer` agent
(Agent tool, `subagent_type: "uedge-reviewer"`). Never use a fork or a reused agent that saw the drafting. Its prompt
must be self-contained:

- `stage: closeout`, the round number, the epic key, the record's absolute path, the snapshot directory, and the
  absolute path for the report (`<checkout>/.claude/work/<EPIC-KEY>/reviews/<EPIC-KEY>-closeout-round<N>.md`, local,
  never committed);
- the git sources: the ticket branches, merges and prototype worktrees (and a legacy planning branch, if any);
- that the reviewer has no Atlassian access: it checks Jira and Confluence claims against the snapshot, git claims
  against the current tips, and lists what it could not verify in its "Not independently verified (environment)"
  section;
- the owner's answers given in this session (Step 6 choices, confirmations, corrections), each marked binding;
- on rounds 2+: the previous report and the response file (`...-closeout-round<N>-response.md`).

Then loop as `create-prd` Step 5 does: wait for the completion notification; read the report; **APPROVE** → Step 6;
**REVISE** → fix every BLOCKER and MAJOR (or rebut it in the response file), fresh reviewer for round N+1 as a
verification round (`.claude/context/process-tiers.md` → Review rounds; MINORs alone never start a round);
**REJECT** → stop and show the owner; after round 3 without APPROVE, stop and ask the owner whether to keep revising
or publish anyway (then add `- review open (N findings)` to the status line and a "## Open review findings"
section). Record each round in section 10 (round, verdict, counts, each finding in one line and its response). A text-only change after APPROVE
needs no new round; any change to a claim, a class, a status or an item does, except recording the owner's Step 6
answers, which is covered by the mechanical self-check in Step 7.

### Step 6 — Owner checkpoint

Show the owner, in the terminal: the completion verdict, the not-done list, and what Step 7 will do. Ask, in one
message:

1. for each open item, unmet gating criteria included: close anyway (accepted-open; for a criterion, the owner
   accepts it as unmet), defer (to which follow-up: an existing key, or a new ticket to file), or keep the epic open;
2. for each decision the record credits to the owner, and each "attribution unverified" one: confirm, correct, or
   mark as not the owner's;
3. whether to publish the record to Confluence now;
4. *if* every open item is answered with close anyway or defer: whether to move the epic to Done.

If question 4 couldn't be asked (an item stays open, or answers are missing), don't offer Done; ask again only after
the answers allow it. Apply the answers to the record: section 8, the "who" column, the status line (table in
Step 4). A change beyond recording the answers goes back through Step 5.

File follow-up tickets only for items the owner deferred to a *new* ticket: `createJiraIssue` in the epic's project,
`Task` or `Story`, description citing the record, **no parent** unless the owner names an epic (never the epic being
closed, which would leave a Done epic with an open child). Skip any that a `summary ~` search already finds.

### Step 7 — Publish, link, close (only what the owner approved in Step 6)

**Preconditions:** Step 5 returned APPROVE for the text being published, or the owner overrode it (Step 5). The
recorded owner answers pass a self-check: every open item in section 8 has an answer (close anyway, defer to <KEY>,
or keep open); for "Closed by the owner", accepted + deferred = n and no item is kept open; every decision credited to
the owner was confirmed in Step 6. If the check fails, fix the record or go back to Step 6. And the
sources haven't moved: compare the ticket tips (and a legacy planning tip), the prototype worktrees, each Jira issue's
`updated` and each page's version with the snapshot. This is the only freshness check on Jira and Confluence: the
reviewer can't query them. If anything changed, re-gather what moved, update the record and the snapshot, and go
back through Step 5.

1. **Nothing is committed.** The record, the snapshot and the review reports stay in `.claude/work/<EPIC-KEY>/`
   (gitignored); keep them until the page is published and its content checked.
2. **Confluence page.** Body = the record. If Step 1 found a `Close-out: <EPIC-KEY>` child page,
   `updateConfluencePage` on it (`contentFormat: "markdown"`, `versionMessage` saying what changed; Confluence bumps
   the version). Otherwise `createConfluencePage` with the PRD's `spaceId`, `parentId` = the PRD page id, the title
   from Configuration, `contentFormat: "markdown"`. Never create a second close-out page. Then put the page id and
   URL in the record's "This page" field and update the page once with it.
3. **Epic comment** (`contentFormat: "markdown"`):

   ```markdown
   Close-out: [<page title>](<page URL>) (Confluence page id `<page-id>`). Status: <the record's status line>.
   Children: <n> Done, <n> open (<keys>). Follow-ups: <keys or none>.
   ```

   If an earlier close-epic comment exists on the epic (it contains the page id), update it with
   `addCommentToJiraIssue` and its `commentId`. If that update fails, add a new comment that starts "Supersedes
   comment <id>" instead of stopping.
4. **Transition the epic** only if the owner said yes in Step 6: `transitionJiraIssue` with the Done transition id
   from Step 1. Re-read the epic to confirm the new status. Children are not touched.

If any Atlassian call fails, report the error verbatim, point to the local record (not committed; the only copy until
the page is published, so keep it), and stop. Don't retry into a different space or page.

## Output

1. Completion verdict and status line, with the not-done list.
2. Record and snapshot paths (local, not committed); dry run: the draft and snapshot paths.
3. Review outcome: verdict, rounds, report paths; or "not run (dry run)".
4. Confluence page (title, id, URL, created or updated) and the epic comment, or what a real run would do.
5. Epic status before and after; children's states (unchanged).
6. Follow-up tickets filed; owner decisions still open; attributions the owner hasn't confirmed.
7. Contradictions between sources and records that were missing.

## Notes

- Re-running is safe: it rewrites the record and snapshot, updates the same page and the same epic comment, and files
  no duplicate follow-ups. Every rerun that changes the published text goes through Step 5 again.
- The record describes; it doesn't re-review the tickets. If gathering shows something wrong in a ticket (a claim a
  record contradicts), list it in section 8 and tell the owner; don't fix it here.
- Large epics produce many records. Read verdicts, summaries and response files first; open full reports only where
  a criterion, decision or open item depends on them.
