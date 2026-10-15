---
name: close-epic
description: Closes out a Jira epic. Gathers everything the epic produced (Jira epic and children with comments, the PRD and its Confluence child pages and comments, the planning branch's breakdown and progress log, every ticket branch, review reports and responses, RCA documents, physics specs, execution and system-review reports), checks it against the PRD's acceptance criteria, and writes a detailed close-out record of what changed, the results, the decisions and who took them, the discussion, deviations and deferred work. The record passes an adversarial uedge-reviewer gate, is published as a child page of the PRD and linked from the epic. The epic moves to Done only when the owner confirms. Use when an epic's tickets are finished, or with --dry-run for a read-only draft of an epic in progress.
argument-hint: "<jira-epic-key> [--dry-run]"
---

# Close Epic: record what an epic did, then close it

## Overview

The last step of the epic flow: `create-prd` → `spec` → one PIV loop per ticket → **`close-epic`**. An epic's
history is spread over Jira (status, comments), Confluence (PRD, breakdown, comments), the planning branch (PRD copy,
breakdown, progress log, PRD reviews) and one branch per ticket (plans, reviews, RCAs, execution reports). This skill
collects it into one record that someone who wasn't there can read: what the epic set out to do, what it changed, what
it measured, what was decided by whom and why, and what is left.

Three rules hold throughout:

- **The skill reports; the owner decides.** It never marks a criterion met, a ticket done or an owner decision taken
  on its own judgement. Every "met" points to a record that shows it. When something is not done, the output is a
  *close-out draft* and the owner chooses: close anyway, defer, or file follow-ups.
- **Nothing reaches Confluence without passing an adversarial review** (Step 5), the same gate as `create-prd`.
- **The epic moves to Done only on the owner's explicit confirmation** (Step 7). Children are never transitioned:
  the record reports their states.

## Configuration

| Setting | Value |
|---|---|
| Record (repo copy) | `docs/specs/<EPIC-KEY>-closeout.md` on the planning branch `feature/v9-<EPIC-KEY>-planning` |
| Review reports | `docs/reviews/<EPIC-KEY>-closeout-round<N>.md` (same branch) |
| Confluence page | child of the PRD page, title `Close-out: <EPIC-KEY> - <epic summary without trailing period>` |
| Dry-run output | `<scratchpad>/closeout/<EPIC-KEY>-closeout-draft.md` (the session scratchpad directory; if there is none, `${TMPDIR:-/tmp}/close-epic/`) |
| Max review rounds before escalating to the owner | 3 |

`docs/specs/` is the epic-artifact path that `change_kind.py` already classes as **artifact**, next to the breakdown
and the progress log. The record never goes on an AI-layer branch or a ticket branch.

## Input

Parse `$ARGUMENTS`:

- **Epic key** (required). A token matching `^[A-Za-z][A-Za-z0-9]*-?[0-9]+$`, normalised to upper case with a hyphen
  before the number (`aiue8` → `AIUE-8`). Without one, stop and ask for it.
- **`--dry-run`** (optional). Read-only rehearsal; see below.

### Dry-run mode

`--dry-run` runs Steps 1–4 for real and Steps 5–7 as a description only. It exists to test this skill and to show
the owner a draft of an epic still in progress. In a dry run:

- **No external writes.** The only Atlassian calls allowed are reads: `getAccessibleAtlassianResources`,
  `getJiraIssue`, `searchJiraIssuesUsingJql`, `getTransitionsForJiraIssue`, `getConfluencePage`,
  `getConfluencePageDescendants`, `getConfluencePageFooterComments`, `getConfluencePageInlineComments`,
  `getConfluenceCommentChildren`, `searchConfluenceUsingCql`, `getConfluenceSpaces`. Never call
  `createConfluencePage`, `updateConfluencePage`, `addCommentToJiraIssue`, `transitionJiraIssue`, `editJiraIssue`,
  `createJiraIssue`, `createIssueLink` or any comment-creating tool.
- **No repo writes.** No file in any worktree is created or changed, nothing is staged or committed. `git fetch` is
  allowed (it only updates remote-tracking refs). Read other branches with `git show <branch>:<path>`. Helper
  scripts go in the scratchpad, never in the repo.
- The draft goes to the dry-run output path (Configuration), with status `Dry run - not reviewed, not published`.
- The adversarial review (Step 5) is skipped unless the user asks for it; if they do, the reviewer writes its report
  next to the draft, not into `docs/reviews/`.
- Step 6 lists the questions it *would* ask the owner, without waiting for answers. Step 7 lists what it *would*
  do: page title, space and parent id, create or update (from the search in Step 1), add or update the epic comment,
  and the Done transition id from `getTransitionsForJiraIssue`. Put both lists in a final appendix of the draft,
  "Dry run: what a real run would do", and in the output.

## Process

### Step 1 — Gather (read-only)

Make independent calls in parallel. Keep notes of *where* each fact came from (issue key and comment date, page id,
`branch:path`, commit hash); the record cites them and the reviewer checks them.

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
   criteria matter and the breakdown doesn't give them. Keep the comment id and date of each one you use.
5. `getTransitionsForJiraIssue` on the epic: note the id of the transition whose target status is Done
   (status category Done). Don't transition.

**Who said it.** Agents post Jira comments and Confluence pages through the owner's account, so the author field
shows the owner for both. Attribute a statement by its content and the progress log ("unattended run", "owner
authorised", "for the owner"), never by the author field. A comment the agent posted is not an owner decision.

**Confluence.**

1. Find the PRD: `mcp__atlassian__searchConfluenceUsingCql` with `type = page AND title ~ "PRD: <EPIC-KEY>"`. Keep
   only titles that are exactly `PRD: <EPIC-KEY>` or start with `PRD: <EPIC-KEY> - `, so `AIUE-8` does not match
   `AIUE-80`. If none, fall back to the epic comment `PRD: ... (Confluence page id ...)` that `create-prd` posts.
   No PRD at all → continue, but the completeness check (Step 3) can only use the breakdown and the tickets' own
   acceptance criteria; say so in the record.
2. The PRD text. The Confluence page is the source of truth (as in `spec`). If the search result's
   `lastModified` is within minutes of the local copy's last commit (`git log -1 --format=%cI -- docs/prds/`), the
   page is the create-prd publish and the local copy may be read instead; otherwise `getConfluencePage`
   (`contentFormat: "markdown"`). Say which you used. Extract: the success criteria (section 11), the binding
   decisions and assumptions (appendix), the default-results statement (section 9), the out-of-scope list, the
   review history and the MINORs carried to the tickets.
3. `getConfluencePageDescendants` on the PRD → the breakdown page (`Spec: ... - Ticket Breakdown`) and any existing
   `Close-out: <EPIC-KEY>` page (same exact-prefix rule). Read the breakdown page (it can be newer than the repo
   copy; its `version.message` says what the owner changed).
4. `getConfluencePageFooterComments` and `getConfluencePageInlineComments` (`resolutionStatus` open **and**
   resolved, `includeReplies: true`) on the PRD and the breakdown page. Comments here are discussion; record what
   was asked, who answered, and whether it changed anything.

**Planning branch** `feature/v9-<EPIC-KEY>-planning` (find its worktree with `git worktree list`; otherwise read with
`git show`):

- `docs/prds/<EPIC-KEY>-*.md` (the PRD copy; if it differs from the Confluence page, Confluence wins, as in `spec`).
- `docs/specs/*.md`: the breakdown (ticket list, dependencies, `Branch:` lines with bases) and the progress log if
  one exists (e.g. `docs/specs/<EPIC-KEY>-progress.md`). The progress log is usually the best narrative source:
  timeline, findings, owner decisions asked and answered.
- `docs/reviews/<EPIC-KEY>-prd-round*.md` and their `-response` files.

**Ticket branches.** `git fetch origin` first and compare against `origin/v9-develop`, never the local `v9-develop`
(it can be behind). For each child key find branches with `git branch -a --list '*v9-<KEY>-*'` (the trailing hyphen
keeps `AIUE-5` from matching `AIUE-50`; drop `-planning`/`-integration` branches, which belong to an epic of that
key, not to the ticket), and scratch or prototype worktrees with `git worktree list | grep -E '/<KEY>(-|$)'`
(detached worktrees hold prototypes that have no branch). For each branch:

- Base: the **actual** parent, from git. The breakdown's `Branch:` line is the plan; unmerged tickets are often
  stacked differently. The parent is the branch with the most commits over `origin/v9-develop` among the epic's
  other ticket branches, its planning branch and any AI-layer branch it was based on, whose tip is an ancestor of
  this branch (`git merge-base --is-ancestor <other> <branch>`), else `origin/v9-develop`.
  Use it for `git log --oneline <base>..<branch>`, `git diff --shortstat <base>...<branch>` and
  `git diff --dirstat=files,5 <base>...<branch>`, so a stacked ticket is not credited with its parent's commits.
  If the parent differs from the breakdown, record it as a deviation.
- Tip hash; merged into `origin/v9-develop` or not (`git merge-base --is-ancestor <branch> origin/v9-develop`); the
  merge commit if merged (`git log --merges --ancestry-path --oneline <tip>..origin/v9-develop | tail -1`); pushed
  or local only (`git branch -r --list 'origin/*v9-<KEY>-*'`).
- PR: `gh pr list --head <branch> --state all` if `gh` is installed and the branch is pushed. If `gh` is missing
  or the branch is local, record "no PR (local branch)" or "PR state unknown (gh not available)"; never guess.
- Records the branch adds (`git diff --name-status <base>...<branch> -- docs .claude/plans
  .claude/execution-reports .claude/system-reviews`): plans, review reports and responses (`docs/reviews/<KEY>-*`,
  including combined files such as `<KEY>-plan-responses.md` and `<KEY>-validation.txt`), RCAs (`docs/rca/`),
  physics specs (`docs/physics_specs/`), execution reports, system reviews, results files. Bulk run records (hundreds
  of JSON files under `docs/rca/<EPIC>-data/records/`) are counted, not read. A document several tickets extend
  (one RCA file) is read from the last branch in the stack.
- Read review reports for the **Verdict** line and **Summary** only (`git show <branch>:<file> | grep -m1 -E
  '\*\*(APPROVE|REVISE|REJECT)'` finds the verdict); read response files for what was fixed, rebutted or deferred
  (`grep -inE 'defer|rebut|owner|not done|left for'`). Note approvals that came only after an owner-authorised
  round past the cap, and commits after the approving round (unreviewed additions).
- **Default results:** first check whether the ticket changes compiled or run-time code at all
  (`git diff --name-only <base>...<branch>` matching `\.(m|v|F90|F|f|c|h)$`, `setup.py`, `Makefile*`,
  `src/uedge/`). If it doesn't, write "no compiled source changed" with that diff as the source. If it does, take the
  statement from the ticket's validate output, validation record, implementation review or commit body ("bitwise
  unchanged on …", "cases X, Y moved because …") and cite it. If no record says, write "not recorded"; never infer
  it from the diff.
- **Status claims in comments are snapshots.** Jira comments and the progress log quote tips and states at the time
  they were written; branches get restacked and tickets move afterwards. Take tips from git and states from Jira, and
  list each contradiction (comment tip vs branch tip, log state vs Jira state) in the output.

Children with no branch (not started, owner tasks, research) are listed with their Jira state only.

Other AI-layer branches the epic produced (`feature/v9-ai-*` named in the progress log or comments) are listed in
the record's AI-layer section with their state, not as tickets.

### Step 2 — Map the epic

Build one table, one row per child: key, summary, Jira status, branch, base, tip, merged (commit) / local / pushed,
PR, last review verdict and round, open findings (deferred, rebutted-not-accepted), default results (sourced).
Sort it in the breakdown's merge order if it has one, else by key.

### Step 3 — Check completion

For each PRD success criterion (and, without a PRD, each ticket's acceptance criteria), find the evidence: which
ticket, which record (`branch:path`, commit, Jira comment), what it says. Classify it as:

| Class | Meaning |
|---|---|
| **Met** | a record shows the criterion's own check passing, on code that is merged (or on a branch, if the criterion doesn't require merging; say which) |
| **Partly met** | some of the criterion's parts are met; say which aren't |
| **Not met** | a record shows it failing, or the work it needs is not done |
| **No evidence** | nothing in the records shows either way. This is never "met" |
| **Superseded** | the owner changed or dropped the criterion; cite the decision |

"Met" on an unmerged branch is written **Met (on unmerged branches)**. Criteria the PRD marks as not gating (bonus
track, quality indicators, user-experience goals) are classified like the others but don't decide completeness; the
children that carry them still appear in the not-done list.

Then list everything that is not done:

- children whose status category is not Done;
- ticket branches not merged into `v9-develop` (and branches with commits but no PR);
- reviews not ending in APPROVE, and approvals given only on an owner override (say so);
- deferred review findings and rebuttals the reviewer didn't accept (from the response files);
- open owner decisions (the PRD decision table, progress-log "your decisions" lists, Jira comments that ask the owner
  and have no answer);
- open Confluence inline comments;
- commits after a ticket's approving review round (unreviewed additions);
- merge conditions recorded on a ticket ("don't merge before …");
- the epic's own Jira state if it disagrees with the work (e.g. still To Do while children are In Review).

**The epic is complete** only if every gating criterion is Met or Superseded and every list above is empty. Otherwise the
record is a **close-out draft**: write it anyway (Step 4), then in Step 6 ask the owner, per open item, to
(a) close anyway and record it as accepted-open, (b) defer to a named follow-up ticket, or (c) keep the epic open.
Don't decide for them, and don't file follow-up tickets before they answer.

### Step 4 — Write the record

Write it to the record path (or, in a dry run, the dry-run path). On a real run, write it in the planning
worktree; create the branch from `origin/v9-develop` if it doesn't exist (`.claude/context/branching.md`). Before
writing a claim, re-check it against its source (a tip with `git rev-parse`, a count in the record it cites); the
reviewer will. Use this
structure; omit a section only when it would be empty, and say "none".

```markdown
# Close-out: <EPIC-KEY> - <epic summary>

> **Jira epic:** [<EPIC-KEY>](https://<site>/browse/<EPIC-KEY>) · **PRD:** [<title>](<url>) (page <id>) · **Breakdown:** [<title>](<url>)
> **Status:** Complete | Close-out draft - epic not complete (<n> open items) | Dry run - not reviewed, not published
> **Generated by:** close-epic on <date> · **Adversarial review:** <VERDICT> (round <N>) · report `docs/reviews/<EPIC-KEY>-closeout-round<N>.md`

## 1. Goal and outcome
   The goal in the PRD's words (2-3 lines); the outcome in 3-5 lines; one line on the completion verdict.
## 2. Acceptance criteria
   Table: criterion · class (Met / Partly / Not met / No evidence / Superseded) · evidence (record + what it shows).
## 3. What changed, per ticket
   One subsection per child in merge order: summary; branch, base, tip, merged commit or "local, not merged"; PR;
   files and areas (`git diff --stat` summary, packages touched); what it delivered; default results (changed or
   not, which reference cases moved, source); review verdict, rounds, open findings.
## 4. Results
   The key measurements (before/after, rates, timings, gates), each with its source record. Quote numbers exactly as
   the record gives them, with units and conditions (case, threads, build, machine load if the record notes it).
## 5. Decisions
   Table: date · decision · who (owner / reviewer / agent, by name or role) · why · source. Mark owner decisions still
   open separately. An agent's choice is never listed as an owner decision.
## 6. Context and discussion
   The discussions that shaped the work: questions raised in Jira or Confluence comments, review escalations,
   rebuttals, findings that changed direction. Each with its source and outcome.
## 7. Deviations from the PRD
   What was done differently from the PRD or the breakdown (scope added or dropped, criteria changed, PRD claims that
   turned out wrong), each with the reason and who agreed to it.
## 8. Open and deferred items
   Everything from Step 3's not-done lists, with the owner's choice once given (accepted-open / follow-up <KEY> /
   keeps epic open).
## 9. AI-layer lessons
   Existing execution reports and system reviews (paths), AI-layer branches the epic produced and their state,
   `ai-layer` issues filed. If there are none, say so and recommend running `execution-report` → `system-review`.
## 10. Sources
   Every record cited: Jira keys, Confluence page ids, `branch:path`, commit hashes; which PRD text was read (page or
   local copy, and why); contradictions between sources (comment tip vs branch tip, log state vs Jira state) and
   records that were missing; the review history of this record.
```

Keep it factual and dense; it is a record, not a sales document. No Mermaid (Confluence's markdown import doesn't
render it). Quote owner and reviewer statements briefly and attribute them.

### Step 5 — Adversarial review (required before any Confluence write)

The author of the record (this session) can't review it independently. Spawn a **fresh** `uedge-reviewer` agent
(Agent tool, `subagent_type: "uedge-reviewer"`). Never use a fork or a reused agent that saw the drafting. Its prompt
must be self-contained:

- `stage: closeout`, the round number, the epic key, the record's absolute path, and the absolute path for the
  report (`<planning worktree>/docs/reviews/<EPIC-KEY>-closeout-round<N>.md`);
- the sources it can check: cloudId, PRD and breakdown page ids, the planning worktree, the ticket branches;
- the owner's answers given in this session (Step 6 choices, corrections), each marked binding;
- on rounds 2+: the previous report and your response to each finding.

Then loop exactly as `create-prd` Step 5 does: wait for the completion notification; read the report; **APPROVE** →
Step 6; **REVISE** → fix every BLOCKER and MAJOR (or rebut it in a `-response` file), fresh reviewer for round N+1;
**REJECT** → stop and show the owner; after round 3 without APPROVE, stop and ask the owner whether to keep revising
or publish anyway (then set the status line to `... - review open (N findings)` and add "## Open review findings").
Record each round in the record's Sources section (round, verdict, counts, report path).

### Step 6 — Owner checkpoint

Show the owner, in the terminal: the completion verdict, the not-done list from Step 3, and what Step 7 will do.
Ask, in one message:

1. for each open item: close anyway (accepted-open), defer (to which follow-up ticket; file it or name an existing
   one), or keep the epic open;
2. whether to publish the record to Confluence now;
3. whether to move the epic to Done (only offered if the record is approved and no item is "keep the epic open").

Apply the answers to the record (section 8, status line). A change beyond recording the answers goes back through
Step 5. File follow-up tickets only for items the owner deferred to a *new* ticket:
`createJiraIssue` (project of the epic, `Task` or `Story`, description citing the record), skipping any that a
`summary ~` search already finds.

### Step 7 — Publish, link, close (only what the owner approved in Step 6)

**Precondition:** Step 5 returned APPROVE for the text being published, or the owner overrode it (Step 5).

1. **Commit the record** on the planning branch with the `commit` skill: the record and its review reports and
   responses, staged by path, `uv run .claude/hooks/change_kind.py --staged` clean. Message e.g. "Adds the
   <EPIC-KEY> close-out record". Don't push unless asked.
2. **Confluence page.** Body = the record, with the metadata block updated (page id, review verdict). If Step 1
   found a `Close-out: <EPIC-KEY>` child page, `updateConfluencePage` on it (`contentFormat: "markdown"`,
   `versionMessage` saying what changed; Confluence bumps the version). Otherwise `createConfluencePage` with the
   PRD's `spaceId`, `parentId` = the PRD page id, the title from Configuration, `contentFormat: "markdown"`. Never
   create a second close-out page. Record the page id and URL, put them into the repo copy's metadata line, and
   commit that one-line change.
3. **Epic comment.** If an earlier `close-epic` comment exists on the epic (it contains the page id), update it with
   `addCommentToJiraIssue` and its `commentId`; otherwise add one (`contentFormat: "markdown"`):

   ```markdown
   Close-out: [<page title>](<page URL>) (Confluence page id `<page-id>`). Status: <Complete | draft, n open items>.
   Children: <n> Done, <n> open (<keys>). Follow-ups: <keys or none>.
   ```

4. **Transition the epic** only if the owner said yes in Step 6: `transitionJiraIssue` with the Done transition id
   from Step 1. Re-read the epic to confirm the new status. Children are not touched.

If any Atlassian call fails, report the error verbatim, point to the committed record, and stop. Don't retry into a
different space or page.

## Output

1. Completion verdict (complete / draft with n open items / dry run), with the not-done list.
2. Record path (and commit hash, on a real run); dry run: the draft path.
3. Review outcome: verdict, rounds, report paths; or "skipped (dry run)".
4. Confluence page (title, id, URL, created or updated) and the epic comment, or what a real run would do.
5. Epic status before and after; children's states (unchanged).
6. Follow-up tickets filed, and the owner decisions still open.
7. Gaps in the sources: records that were missing or contradicted each other (e.g. Jira status vs progress log).

## Notes

- Re-running is safe: it rewrites the record, updates the same page and the same epic comment, and files no
  duplicate follow-ups. Every rerun that changes the published text goes through Step 5 again.
- The record describes; it doesn't re-review the tickets. If gathering shows something wrong in a ticket (a claim a
  record contradicts), list it in section 8 as an open item and tell the owner; don't fix it here.
- Large epics produce many records. Read summaries and verdicts first and open full reports only where a criterion,
  decision or open item depends on them.
