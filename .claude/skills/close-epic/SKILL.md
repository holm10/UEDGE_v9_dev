---
name: close-epic
description: Closes out a tracker epic. Gathers everything the epic produced from the private tracker named by .claude/tracker.toml and from git only (the epic issue and its sub-issues with comments and Project fields; epic.md, breakdown.md and progress.md; each ticket's record.md with its plans, reviews, validation results and decisions, and plan.md or rca.md; the PRs and merge commits the records name, every ticket branch or merge and its git history, physics specs, and a legacy planning branch if one exists), saves a local snapshot of the tracker and issue sources, checks it against epic.md's success criteria, and writes a detailed close-out record of what changed, the results, the decisions and who took them, the discussion, deviations and deferred work. The record passes an adversarial uedge-reviewer gate, is committed as docs/T<E>-<slug>/closeout.md in the tracker and linked from the epic issue. The epic is closed (Project Done) only when the owner confirms. Use when an epic's tickets are finished, or with --dry-run for a read-only draft of an epic in progress.
argument-hint: "T<E> [--dry-run]"
---

# Close Epic: record what an epic did, then close it

## Overview

The last step of the epic flow: `create-prd` → `spec` → one PIV loop per ticket → **`close-epic`**. An epic's
history is in the tracker and in git:

- **The tracker's issues:** the epic issue and its sub-issues (state, comments, "blocked by"), and the Project
  (Status, Tier).
- **The tracker's documents:** `epic.md` (the PRD, its Decisions and Reviews), `breakdown.md` and `progress.md` in
  `docs/T<E>-<slug>/`, and one directory per ticket with its `record.md` (Ticket section, Progress, Validation,
  Reviews, Findings and decisions) and `plan.md` or `rca.md`.
- **Git:** one branch or merge per ticket in the public repo, with its commits and physics specs; the PRs the records
  name.

Ticket and epic working documents are never committed to the public repo (`.claude/context/branching.md`), so the
records are where plans, reviews and validation results are found; epics started before that rule also left them on
a planning branch and in ticket branches (legacy sources, read with `git show`). **This skill reads nothing else**: for
an epic imported from the old tracker, its earlier history is what the import copied into `epic.md`, `breakdown.md`
and the records, and the old keys are cited as they appear there; the Jira and Confluence archive is not read (owner,
2026-11-18, tracker #9).
This skill collects it into one record that someone who wasn't there can read: what the epic set out to do, what it
changed, what it measured, what was decided by whom and why, and what is left.

Four rules hold throughout:

- **The skill reports; the owner decides.** It never marks a criterion met, a ticket done or an owner decision taken
  on its own judgement. Every "met" points to a record that shows it. When something is not done, the owner chooses
  per item: close anyway, defer, or keep the epic open.
- **Every claim has a checkable source.** Git claims cite a commit or `branch:path`; tracker claims cite a tracker path
  and the tracker commit the snapshot read (Step 1); issue claims cite the snapshot.
- **Nothing reaches the tracker's `docs/` without passing an adversarial review** (Step 5), the same gate as
  `create-prd`.
- **The epic is closed only on the owner's explicit confirmation** (Step 7). Children are never closed or moved: the
  record reports their states.

## Configuration

| Setting | Value |
|---|---|
| Tracker | `.claude/tracker.toml` in the main checkout: `owner`, `repo`, `project`. Below, `<o>/<r>` is owner/repo and `<P>` the Project number; never write them out in this skill |
| Tracker checkout `<T>` | `<parent of the main checkout>/<repo>`, as `ticket-page` uses it (the main checkout is the parent of `git rev-parse --path-format=absolute --git-common-dir`) |
| Public repo `<pub>` | owner/repo of the UEDGE checkout's `origin` remote (`git remote get-url origin`), for `gh pr` calls |
| Epic directory | `docs/T<E>-*/` in `<T>` (exactly one; none → stop and say so) |
| Record (local working copy) | `.claude/work/T<E>/closeout.md` in the current checkout |
| Sources snapshot (local) | `.claude/work/T<E>/closeout-sources/` |
| Review reports (local) | `.claude/work/T<E>/reviews/T<E>-closeout-round<N>.md` and `-response.md` |
| Published record | `closeout.md` in the epic directory: the record's lasting home |
| Dry-run output | `<scratch>/closeout/T<E>-closeout-draft.md` and `<scratch>/closeout/T<E>-closeout-sources/`, where `<scratch>` is the session scratchpad directory, or `${TMPDIR:-/tmp}` if there is none |
| Max review rounds before escalating to the owner | 3 |

The local files are working documents: gitignored, never committed to the public repo, on any branch
(`change_kind.py` refuses them). The record's lasting copy is `closeout.md` in the tracker; the review rounds are
summarised in its section 10; the snapshot stays local, and section 10 lists what it holds (read time, the tracker
commit read, issue `updatedAt` values, comment ids) so the sources can be read again. Keep the local files until
`closeout.md` is committed and pushed.

**Tracker reads** never change the checkout: `git -C <T> fetch -q`, then list with `git -C <T> ls-tree -r --name-only
origin/main -- <epic directory>` and read with `git -C <T> show origin/main:<path>` (use the default branch's name if
it is not `main`). The snapshot names the commit read (`git -C <T> rev-parse origin/main`).

**Tracker writes** (Step 7 only; the same rule as `ticket-page`): `git -C <T> status --porcelain
--untracked-files=no` must be empty and `git -C <T> symbolic-ref --short HEAD` the default branch; otherwise write
nothing and report. Then `git -C <T> pull --rebase -q` (a conflict: `git -C <T> rebase --abort`, write nothing,
report), write the file, `git -C <T> add -- <paths>`, `git -C <T> commit -q -m "T<E> close-epic: <what>" -- <paths>`
and `git -C <T> push -q`.

## Input

Parse `$ARGUMENTS`:

- **Epic** (required). `T<E>` (also `t<E>` or `#<E>`; normalise to `T<E>`). Without one, stop and ask for it.
- **`--dry-run`** (optional). Read-only rehearsal; see below.

### Dry-run mode

`--dry-run` runs Steps 1–4 for real and Steps 6–7 as a description only. It exists to test this skill and to show
the owner a draft of an epic still in progress. In a dry run:

- **No external writes.** The only `gh` calls allowed are reads: `gh issue view`, `gh issue list`, `gh pr view`,
  `gh pr list`, `gh project view`, `gh project field-list`, `gh project item-list`, `gh repo view`, `gh api` GET
  requests and `gh api graphql` queries. Every other `gh` call is forbidden, in particular `gh issue create`, `edit`,
  `comment` and `close`, `gh project item-add` and `item-edit`, and `gh api` with `-X POST`, `PATCH` or `DELETE`.
- **No repo writes.** No file in any worktree or in `<T>` is created or changed (not even in `.claude/work/`),
  nothing is staged, committed or pushed. `git fetch` is allowed in both (it only updates remote-tracking refs). Read
  other branches and the tracker with `git show <rev>:<path>`. Helper scripts, the snapshot and the draft go in the
  dry-run output directory, never in a repo.
- The draft's status is `Dry run - not reviewed, not published`.
- The adversarial review (Step 5) runs only if the user asks; the reviewer then writes its report next to the draft.
- Step 6 lists the questions it *would* ask the owner, without waiting for answers. Step 7 lists what it *would*
  do: the tracker path, create or replace, the commit message, add or update the epic comment, and the epic's Project
  item id and the Status option id of Done. Put both lists in a final appendix of the draft, "Dry run: what a real
  run would do", with each value's source in the snapshot, and in the output.

## Process

### Step 1 — Gather (read-only) and snapshot

Make independent calls in parallel. Keep notes of *where* each fact came from; the record cites them.

**The sources snapshot.** Write each tracker and issue read you use into the snapshot directory as you go, verbatim
in the fields you use (no paraphrase; avatar and `url` fields of authors may be dropped):

| File | Content |
|---|---|
| `issue-epic.json` | the epic: `gh issue view <E> -R <o>/<r> --json number,title,body,state,stateReason,issueType,labels,createdAt,updatedAt,closedAt,comments` |
| `issue-children.json` | every sub-issue: number, title, type, labels, state and state reason, createdAt, updatedAt, closedAt, and its "blocked by" numbers |
| `issue-comments.md` | every sub-issue comment used: issue number, comment URL, createdAt, body verbatim (markdown avoids JSON-escaping long bodies) |
| `project-items.json` | the Project items of the epic and its sub-issues (and the PRs added to the Project): item id, issue number, Status, Tier, `Jira key`; plus the Status field id and its Done option id |
| `tracker-files.txt` | the commit read (`origin/main` sha) and the `ls-tree` listing of the epic directory, with each file's last commit (`git -C <T> log -1 --format='%h %ad' origin/main -- <path>`) |
| `tracker-epic.md`, `tracker-breakdown.md`, `tracker-progress.md` | the epic documents as read |
| `tracker-records.md` | per ticket record: its path, the header, the Ticket section and the four log sections verbatim (Progress, Validation, Reviews, Findings and decisions). `plan.md`/`rca.md` are left out unless a criterion depends on them (then quote the part used): record the publish date and sha256 the header cites |
| `prs.json` | the public PRs the records and comments name: `gh pr view <N> -R <pub> --json number,title,state,headRefName,baseRefName,mergeCommit,mergedAt,url`. A public PR is one written `<pub>#<N>` or a PR URL of `<pub>`, or one in a record's `PR` row; a bare `#<N>` or `PR #<N>` in the tracker is the tracker's own issue or PR |
| `snapshot.md` | header: UTC time of the gather; the tracker commit read; `origin/v9-develop` sha; a legacy planning branch tip, if one exists; every ticket branch, merge commit or prototype worktree with its tip and `git status --short` line count; each issue's `updatedAt` |

The record states its snapshot (section 10). Facts that change after it are the reviewer's to flag, not errors.

**Issues and the Project.**

1. The epic (`issue-epic.json` above). If it doesn't exist, stop. If its type isn't `Epic`, ask whether to continue.
2. Its sub-issues: `gh api repos/<o>/<r>/issues/<E>/sub_issues --paginate`; per sub-issue, `gh issue view <N> -R
   <o>/<r> --json number,title,state,stateReason,issueType,labels,createdAt,updatedAt,closedAt,comments` (the
   comments too) and its "blocked by" (`gh api repos/<o>/<r>/issues/<N>/dependencies/blocked_by --jq
   '[.[].number]'`).
3. The Project: `gh project item-list <P> --owner <o> --format json --limit 1000` (keep the epic, its sub-issues and
   the PRs the records name) and `gh project field-list <P> --owner <o> --format json` (the Status field and its Done
   option). An item's `Jira key` field names the old key of an imported ticket: use it to find that ticket's older git
   work (below) and cite it as history.

**Who said it.** Agents post issue comments and tracker commits through the owner's account, so the author field
shows the owner either way and proves nothing. Attribute a statement as follows:

| Attribution | When |
|---|---|
| **Owner** | a source records it as the owner's: `epic.md`'s Decisions entries marked `Owner:` with their source, a record or progress line that says the owner decided, approved, asked or authorised (citing a source), an owner reply in the conversation, or the owner's confirmation in Step 6 |
| **Agent** | the source marks it as the agent's (`Agent:`, "unattended run", "proposed", "for the owner", a response entry, a commit) |
| **Reviewer** | a review entry marked `Reviewer:`, or a legacy review report |
| **Attribution unverified (posted via owner account)** | anything else, including passive wording ("Docker started", "workaround added") and commit messages in the tracker |

An unverified statement is never listed as an owner decision. Step 6 asks the owner to confirm each one.

**Tracker documents** (Tracker reads; save each as the snapshot table says):

1. `epic.md`, the PRD (as in `spec`). No `epic.md` → continue, but Step 3 can only use the breakdown and the tickets'
   own acceptance criteria; say so. Extract: the success criteria (`## Success criteria`), the binding decisions
   (`## Decisions`), the default-results statement (`## Physics & Numerics Impact`, if the PRD has it), the
   out-of-scope list (`## Scope`), the review history (`## Reviews`), and the MINORs the PRD carried to the tickets.
2. `breakdown.md` and `progress.md`. The progress log is usually the best narrative source; read all of it, including
   every owner decision and every owner follow-up line. An existing `closeout.md` (a re-run) is read too.
3. **Ticket records** (written by the `ticket-page` skill): `<epic directory>/T<N>-*/record.md` for each sub-issue,
   with `plan.md` or `rca.md` next to it. A ticket moved in from another epic may keep its record there: for each
   sub-issue with no record here, look for `docs/*/T<N>-*/record.md` across the tracker and include it, noting where
   it lives. A `Plan` header that says "not written yet" means only "plan not published in the record": never infer
   "never planned" from it. For a backfilled record (status `Backfilled`, or a Progress entry saying so), or a ticket
   whose Project Status is beyond To Do, look for a plan in its issue comments and, for legacy tickets, committed on
   its branch, and write "plan not published in the record"; only a To Do ticket with no plan anywhere counts as not
   planned. The log sections are **the** record of each ticket's progress, validation results, review rounds
   (verdict, findings, responses) and decisions: the working files they summarise were never committed. Cite the
   record entry (path, section, date) for those claims and git (commit, `rev:path`) for code claims; for legacy
   tickets, the committed reports are a second source. An entry marked Owner was written by an agent: it counts as an
   owner decision only when the source it cites does (the attribution table above). A ticket with work but no record
   is noted in section 10, not an open item.

**Legacy planning branch** (epics whose work started before working documents left git): if the epic or a ticket
has an old key (the import's `Jira key` field, or a key `epic.md` cites) and `feature/v9-<OLD-KEY>-planning` exists
(`git branch -a --list '*v9-<OLD-KEY>-planning'`), or its archive tag does (`git ls-remote --tags origin
'archive/<OLD-KEY>-planning'`; AIUE-5, AIUE-8 and AIUE-9 have one), or the tag `archive/AIUE-8-docs` holds the
epic's files, read with `git show` the PRD copy (`docs/prds/<OLD-KEY>-*.md`), the breakdown and the progress log
(`docs/specs/*.md`) and the review reports (`docs/reviews/<OLD-KEY>-*`) as historical sources, and read all of a
progress log found there as for `progress.md`. Newer epics have no planning branch; nothing is written to one.

**Tickets: find each child's work.** `git fetch origin` first. Compare against `origin/v9-develop`, never the local
`v9-develop` (it can be behind). A ticket's **keys** are `T<N>` and, for an import, its old key. For each child, in
this order:

1. **Merged.** First the record: its `PR` header row and its `Committed` Progress entries name the PR and the merge
   commit; confirm them with `gh pr view <N> -R <pub> --json state,mergeCommit,mergedAt,headRefName` and `git
   merge-base --is-ancestor <commit> origin/v9-develop`. Otherwise a merge or squash commit on `origin/v9-develop`
   that carries a key: `git log --first-parent -E --grep='(^|[^A-Za-z0-9])T<N>([^0-9]|$)|tracker #<N>([^0-9]|$)'
   --format='%H %s' origin/v9-develop` (subject and body; squash subjects end in the public PR number `(#M)`, which
   is not the tracker number), and the same with the old key. A hit only in a commit body ("left for tracker #5") is
   not that ticket's merge: keep it only when the subject names the key or the PR's head branch is the ticket's. With
   `gh`: `gh pr list -R <pub> --state merged --search '<key>' --json number,headRefName,mergeCommit,mergedAt`. A PR
   whose state is MERGED counts as merged even when the branch tip is not an ancestor (squash, rebase). **Without
   `gh`**, also try, in order:
   - a PR number or branch name `progress.md`, a record or an issue comment gives;
   - patch identity, when the branch still exists: `git cherry origin/v9-develop <branch>` (every line `-` means each
     commit landed, as in a rebase merge); for a squash, compare
     `git diff <parent>...<branch> | git patch-id --stable` with `git show <S> | git patch-id --stable` for the
     first-parent commits after the branch's fork point.

   If none finds it, the merge is **undeterminable**: say so for that child, list "merge not located" as an open item
   when the issue is closed as completed or the branch is gone, and state the limitation in section 10.
2. **Branch.** The record's `Branch` row, then `git branch --list '*v9-T<N>-*' '*v9-ai-[Tt]<N>-*'` (local) and `git
   branch -r --list 'origin/*v9-T<N>-*' 'origin/*v9-ai-[Tt]<N>-*'`, and the same with the old key. The trailing
   hyphen keeps `T1` from matching `T10`. Drop `-planning` and `-integration` branches, which belong to an epic of
   that key. Report one tip per branch: the local one, noting if it is ahead of or behind its `origin/` copy. A
   branch whose tip is an ancestor of `origin/v9-develop` is merged; find its merge with
   `git rev-list --first-parent --merges --ancestry-path <tip>..origin/v9-develop | tail -1`.
3. **Prototype worktrees.** `git worktree list --porcelain`, keeping `worktree` paths whose last component is
   `T<N>` or starts with `T<N>-` (or the old key). For each: HEAD, branch or detached, and `git -C <path> status
   --short`. Uncommitted changes in a prototype are an open item (they exist nowhere else; working documents in its
   `.claude/work/` are not), and so are commits reachable only from a detached HEAD (`git branch -a --contains <HEAD>`
   empty); list those commits (`git log --oneline <merge-base with origin/v9-develop>..<HEAD>`). Say what each
   worktree is when a record names it (a negative control or seeded race is deliberate; its open item is only the
   clean-up). Before writing "not named in a record", grep the records for the worktree's name and its HEAD's short
   sha: the snapshot (`grep -rn -e '<name>' -e '<sha7>' <snapshot dir>`), and, for legacy records, `git grep -n -e
   '<name>' -e '<sha7>' <rev> -- docs .claude/plans` for a legacy planning tip and every ticket tip.

   Agent work in progress outside the repos (a session scratchpad, a running study) is **in progress, not a
   source**: name it in section 8 if a record mentions it, and never cite its numbers as evidence.

Then, per child, the **range** that holds its own work:

| Case | Commits | Diff | Records read from |
|---|---|---|---|
| merged by merge commit `M` | `git log --oneline M^1..M^2` | `git diff M^1 M` | `M:<path>` |
| squash or single rebased commit `S` | `S` | `git diff S^ S` | `S:<path>` |
| rebase-merged series | the PR's commits (`gh pr view <N> -R <pub> --json commits`), else the first-parent run carrying the key | first^..last | last commit |
| unmerged branch | `git log --oneline <parent>..<branch>` | `git diff <parent>...<branch>` | `<branch>:<path>` |

**Stacked tickets merged together.** If two children resolve to the same merge or squash commit, or `M^1..M^2`
contains another child's tip, the merge range covers more than one ticket. Then take each child's commits, diff and
records from its own range, `<parent-tip>..<tip>` with the actual-base rule below (tips from the branches, or, if
they are gone, from the snapshot, `progress.md` or the records), and note the shared merge in each child's entry. If
the tips can't be recovered, say the range is shared and attribute nothing ticket by ticket.

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
- **Reviews:** each round's Reviews entries in the ticket's record: the verdict, counts, findings, what the diff range
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

  To tell a requested fix from an unreviewed change, compare the diff with the findings and the response entry: every
  changed claim must trace to a finding.
- **Default results (every ticket gets a line).** If every changed path is under `docs/`, `.claude/`, `tests/`,
  `.github/`, or is `*.md`, `.gitignore`, `.mcp.json`, write "no change to built or run-time code" with the diff as
  the source. Otherwise (sources, `.v`, build files, `pyproject.toml`, `setup.py`, rate or data files, `src/uedge/`,
  package `*.py`), take the statement from the ticket's validation record, validate output, implementation review or
  commit body ("bitwise unchanged on …", "cases X, Y moved because …") and cite it, including the commit it was
  measured on (the record's Validation entries, its implementation Reviews entry, or the commit body). If none says,
  write "not recorded"; never infer it from the diff.
- **Evidence across tickets.** Where a criterion rests on several unmerged tickets (two fixes, a fix and its test
  tool), say whether any record shows them tested together. If not, the criterion is at best **Partly met**, with
  the combined check as the missing part.
- **Status claims in comments are snapshots and summaries.** Issue comments and `progress.md` quote tips and states
  at the time they were written, and summarise records. Take tips from git, states from the issues and the Project,
  and results from the record a comment summarises; list each contradiction in section 10.

Children with no work anywhere are listed with their issue state and Project Status only. AI-layer branches the epic
produced (`feature/v9-ai-*` named in `progress.md`, the records or comments) are listed in section 9 with their state,
not as tickets.

### Step 2 — Map the epic

Build one table, one row per child: `#<N>`, title, issue state and Project Status, merged (commit, PR) or branch with
parent and tip, pushed or local, last review verdict and round, open findings, unreviewed post-APPROVE changes,
default results (sourced). Sort it in the breakdown's merge order if it has one, else by number.

### Step 3 — Check completion

For each success criterion in `epic.md` (and, without one, each ticket's acceptance criteria), find the evidence:
which ticket, which record, what it says. Use only these classes:

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
- children that are still open or whose Project Status is not Done;
- ticket work not merged into `v9-develop` (and branches with commits but no PR);
- reviews not ending in APPROVE, and approvals given only on an owner override;
- unreviewed post-APPROVE changes (the third class above);
- deferred review findings, accepted gaps with no ticket, and rebuttals the reviewer didn't accept;
- open owner decisions: every owner-decision item in `progress.md`, the records' Findings and decisions and `epic.md`'s
  Decisions, questions to the owner in issue comments with no answer, and open sub-issues with the label
  `owner-decision`. An item counts as answered only if a source attributed to the owner answers it; an experiment
  that answers the technical question still needs the owner's acceptance;
- prototype worktrees with uncommitted changes, and commits on no branch;
- merges that could not be located;
- merge conditions recorded on a ticket ("don't merge before …");
- the epic's own state (issue state, Project Status, `epic.md`'s header Status) if it disagrees with the work (e.g.
  To Do while children are In Progress).

**The epic is complete** only if the list above is empty; an unmet gating criterion is on it, so it can't be skipped.
Otherwise write the record as a close-out draft (Step 4); the owner decides each open item in Step 6. A close-out
draft always has at least one open item: if the list is empty while a criterion is unmet, the list is wrong.

### Step 4 — Write the record

Write it to the record path (dry run: the dry-run path). On a real run it is a local working copy in the current
checkout, on any branch: nothing is committed to the public repo and no branch is needed
(`.claude/context/branching.md`). Before writing a claim, re-check it against its source (a tip with `git
rev-parse`, a count in the record it cites, an issue state in the snapshot); the reviewer will.

The status line takes exactly one of:

| Status | When |
|---|---|
| `Dry run - not reviewed, not published` | `--dry-run` |
| `Complete` | Step 3 found the epic complete |
| `Close-out draft - epic not complete (<n> open items)` | n ≥ 1 open items (unmet gating criteria included), before the owner has answered all of them |
| `Closed by the owner on <date> - <a> accepted-open, <d> deferred to <#N…>` | the owner answered every open item, including every unmet gating criterion, with close anyway or defer, and said yes to Done; a + d equals the number of open items |

An epic the owner keeps open stays at `Close-out draft`.

```markdown
# Close-out: T<E> - <epic title>

> **Epic:** #<E> · **Epic document:** `epic.md` · **Breakdown:** `breakdown.md` · **This file:** `closeout.md` in `docs/T<E>-<slug>/` (or "not published")
> **Status:** <one of the four above>
> **Generated by:** close-epic on <date> · **Snapshot:** <UTC time>, tracker `<sha>`, `origin/v9-develop` `<sha>` (local, not published; contents in section 10)
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
   The discussions that shaped the work: questions in issue comments, review escalations, rebuttals, findings that
   changed direction. Each with its source and outcome.
## 7. Deviations from the PRD
   What was done differently from the PRD or the breakdown (scope added or dropped, tickets added or rescoped,
   criteria changed, actual bases that differ from the plan, PRD claims that turned out wrong). Each with the reason
   and who agreed to it ("not recorded" if no source says).
## 8. Open and deferred items
   Everything from Step 3's not-done lists, with its source and the owner's choice once given (accepted-open /
   deferred to #<N> / keeps the epic open).
## 9. AI-layer lessons
   The execution-report and system-review entries in the records (Findings and decisions; legacy: committed reports,
   by path), AI-layer branches the epic produced and their state, `ai-layer` issues filed, process lessons recorded in
   `progress.md`. If there are none, say so and recommend `execution-report` → `system-review`.
## 10. Sources
   The snapshot (time, the tracker commit and git tips, what it holds; it stays local); every record cited (issue
   numbers and comment URLs, tracker paths with section and entry date, `rev:path`, commit hashes); contradictions
   between sources; records that were missing; the review history of this record, round by round (verdict, counts,
   each finding in one line and its response), since the review reports are not kept.
```

Keep it factual and dense; it is a record, not a sales document. Prefer tables to diagrams. Quote owner and
reviewer statements briefly and attribute them.

### Step 5 — Adversarial review (required before any tracker write)

The author of the record (this session) can't review it independently. Spawn a **fresh** `uedge-reviewer` agent
(Agent tool, `subagent_type: "uedge-reviewer"`). Never use a fork or a reused agent that saw the drafting. Its prompt
must be self-contained:

- `stage: closeout`, the round number, the epic (`T<E>`), the record's absolute path, the snapshot directory, and the
  absolute path for the report (`<checkout>/.claude/work/T<E>/reviews/T<E>-closeout-round<N>.md`, local, never
  committed);
- the git sources: the ticket branches, merges and prototype worktrees (and a legacy planning branch, if any);
- the tracker checkout's path and the tracker commit the snapshot read, so the reviewer can check tracker claims
  against `git -C <T> show <sha>:<path>` as well as the snapshot;
- that it checks issue and Project claims against the snapshot, tracker claims against the snapshot and that commit,
  git claims against the current tips, and lists what it could not verify in its "Not independently verified
  (environment)" section;
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
   accepts it as unmet), defer (to which follow-up: an existing issue, or a new ticket to file), or keep the epic open;
2. for each decision the record credits to the owner, and each "attribution unverified" one: confirm, correct, or
   mark as not the owner's;
3. whether to publish the record to the tracker now;
4. *if* every open item is answered with close anyway or defer: whether to close the epic (Done).

If question 4 couldn't be asked (an item stays open, or answers are missing), don't offer Done; ask again only after
the answers allow it. Apply the answers to the record: section 8, the "who" column, the status line (table in
Step 4). A change beyond recording the answers goes back through Step 5.

File follow-up tickets only for items the owner deferred to a *new* ticket: `gh issue create -R <o>/<r> --type
<Task|Feature|Bug> --title … --body-file …` with a body citing the record, put on the Project as To Do (`gh project
item-add` and `item-edit`, as `spec` → Project fields does), **no parent** unless the owner names an epic (never the
epic being closed, which would leave a closed epic with an open child). Skip any that `gh issue list -R <o>/<r>
--state all --search '<title> in:title'` already finds.

### Step 7 — Publish, link, close (only what the owner approved in Step 6)

**Preconditions:** Step 5 returned APPROVE for the text being published, or the owner overrode it (Step 5). The
recorded owner answers pass a self-check: every open item in section 8 has an answer (close anyway, defer to #<N>,
or keep open); for "Closed by the owner", accepted + deferred = n and no item is kept open; every decision credited to
the owner was confirmed in Step 6. If the check fails, fix the record or go back to Step 6. And the sources haven't
moved: compare the ticket tips (and a legacy planning tip) and the prototype worktrees with the snapshot, each
issue's `updatedAt` (`gh issue view <N> -R <o>/<r> --json updatedAt`) with the snapshot's, and the epic directory's
last tracker commit after a fetch (`git -C <T> log -1 --format=%h origin/main -- <epic directory>`) with the commit
the snapshot read. If anything changed, re-gather what moved, update the record and the snapshot, and go back
through Step 5.

1. **Nothing is committed to the public repo.** The record, the snapshot and the review reports stay in
   `.claude/work/T<E>/` (gitignored); keep them until `closeout.md` is committed, pushed and its content checked.
2. **The tracker file.** Put `closeout.md` in the record's "This file" field, then write it as **Tracker writes**
   says: one commit of `closeout.md` (a re-run replaces it; never a second file), `T<E> close-epic: closeout.md
   (<status line>)`. If the owner said yes to Done, the same commit sets `epic.md`'s header Status to `Done` and its
   Last update to today.
3. **Epic comment:** `gh issue comment <E> -R <o>/<r> --body-file <file>` with

   ```markdown
   Close-out: docs/T<E>-<slug>/closeout.md (<tracker commit>). Status: <the record's status line>.
   Children: <n> Done, <n> open (#<N>, …). Follow-ups: #<N>, … or none.
   ```

   If an earlier close-epic comment exists on the epic (it links `closeout.md`), update it instead: `gh api -X PATCH
   repos/<o>/<r>/issues/comments/<comment id> -F body=@<file>`. If that update fails, add a new comment that starts
   "Supersedes <comment URL>" instead of stopping.
4. **Close the epic** only if the owner said yes in Step 6: `gh issue close <E> -R <o>/<r> --reason completed`, then
   its Project Status to Done (`gh project item-edit --id <epic's item id> --project-id <project id> --field-id
   <Status field id> --single-select-option-id <Done option id>`, ids from Step 1). Re-read the epic (`gh issue view
   <E> -R <o>/<r> --json state,projectItems`) to confirm it is closed and Done. Children are not touched.

If any tracker or `gh` write fails, report the error verbatim, point to the local record (not committed; the only copy
until `closeout.md` is pushed, so keep it), and stop.

## Output

1. Completion verdict and status line, with the not-done list.
2. Record and snapshot paths (local, not committed); dry run: the draft and snapshot paths.
3. Review outcome: verdict, rounds, report paths; or "not run (dry run)".
4. The tracker file (`closeout.md` path, commit, created or replaced, pushed) and the epic comment, or what a real run
   would do.
5. Epic state and Project Status before and after; children's states (unchanged).
6. Follow-up tickets filed; owner decisions still open; attributions the owner hasn't confirmed.
7. Contradictions between sources and records that were missing.

## Notes

- Re-running is safe: it rewrites the record and snapshot, replaces the same `closeout.md`, updates the same epic
  comment, and files no duplicate follow-ups. Every rerun that changes the published text goes through Step 5 again.
- The record describes; it doesn't re-review the tickets. If gathering shows something wrong in a ticket (a claim a
  record contradicts), list it in section 8 and tell the owner; don't fix it here.
- Large epics produce many records. Read verdicts, summaries and response entries first; open full plans or legacy
  reports only where a criterion, decision or open item depends on them.
