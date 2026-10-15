# Response to the close-epic review, round 1

Two reports. The first is the skill review, `docs/reviews/ai-close-epic-round1.md` (REVISE, 2 blocker / 2 major /
7 minor). The second is a close-out-stage test on the first AIUE-8 dry-run draft,
`scratchpad/closeout/AIUE-8-closeout-review-round1.md` (REVISE, 0 blocker / 4 major / 6 minor, plus an assessment of
the stage).

The changes are on `feature/v9-ai-close-epic`:
- `9660c36` revises `.claude/skills/close-epic/SKILL.md`, the close-out stage of `.claude/agents/uedge-reviewer.md`,
  and the planning row of `.claude/context/branching.md`.

Before that commit, the revised text was dry-run again on AIUE-8, read-only, and what the run showed was folded in
(last section). That run produced a new draft, `scratchpad/closeout/AIUE-8-closeout-draft-r2.md`, and its snapshot
directory, `scratchpad/closeout/AIUE-8-closeout-sources/`.

## Skill review

| Finding | Response |
|---|---|
| **I1-B1** Merged, squashed, rebased or deleted branches give an empty record | **Fixed.** Step 1 now finds each child's work in a set order: a merge or squash on `origin/v9-develop` first-parent history (subject carries the key or branch; `gh pr list --state merged` when available, and a MERGED PR counts as merged even when the tip isn't an ancestor), then branches, then prototype worktrees. A range table says where the commits, diff and records come from: `M^1..M^2` / `M^1 M` / `M:<path>` for a merge, `S^ S` for a squash, the PR's commits for a rebase series, and `<parent>...<branch>` only for unmerged work. Checked on `feature/v9-ai-layer`: `git rev-list --first-parent --merges --ancestry-path a420824..origin/v9-develop \| tail -1` gives `0fac655` "Merge pull request #1 from holm10/feature/v9-ai-layer". `M^1..M^2` gives 6 commits. `git diff --shortstat 0fac655^1 0fac655` gives 44 files changed, +4910. The first-parent subject search also finds `0fac655` without the branch. The default-results filter flags `.gitignore`/`.mcp.json` as needing no statement (both are on the allowlist) and nothing else outside `docs/`, `.claude/`, `*.md`. The squash and rebase rows could not be exercised: no such merge exists in this repo, and `gh` is not installed. |
| **I1-B2** The closeout reviewer has no Atlassian tools | **Fixed by a sources snapshot, as directed.** The tool list stays as it is. Step 1 writes every Jira and Confluence read it uses into `docs/specs/<EPIC>-closeout-sources/` (the scratch directory in a dry run): the epic, the children with status and `updated`, verbatim comment bodies, transitions, page versions, page bodies (or the repo blob hash when identical, with the comparison method), and page comments. A `snapshot.md` header records the UTC time, `origin/v9-develop`, the planning tip, every branch/merge/worktree tip with its dirty count, and each issue's `updated`. The reviewer stage checks Jira/Confluence claims against the snapshot and git claims against the current repo, and lists what it could check neither way. Its new check 2 makes source movement after the snapshot a finding. Step 7 re-checks the snapshot before publishing and goes back through review if anything moved. The skill's rules now include "every claim has a checkable source". |
| **I1-M1** No status for an epic closed with accepted-open items | **Fixed.** Step 4 has a status table with four values: `Dry run - …`, `Complete`, `Close-out draft - epic not complete (<n> open items)`, and `Closed by the owner on <date> - <a> accepted-open, <d> deferred to <KEYs>`. The last applies once the owner has answered every item with close anyway or defer, and said yes to Done. The epic comment quotes the record's status line. Reviewer check 7 lists the same four and their conditions, so a dry run is no longer told to say "Close-out draft". |
| **I1-M2** Attribution of unmarked statements; the owner never confirms | **Fixed.** Step 1 has an attribution table: Owner, Agent, Reviewer, and "Attribution unverified (posted via owner account)". The last covers passive wording and Confluence version messages. An unverified statement is never an owner decision. Step 6 question 2 asks the owner to confirm, correct or reject every owner-credited and every unverified decision. Reviewer check 5 makes an owner credit without a supporting source a BLOCKER. The convention of a fixed prefix on agent-posted comments is left as a possible `ai-layer` follow-up and was not done here. |
| I1-m1 PRD local-copy shortcut | **Fixed.** The skill always reads the PRD page and diffs it against the local copy. When the body matches, the snapshot stores the blob hash, the comparison method and the differences instead of the body. |
| I1-m2 Worktree and branch patterns | **Fixed.** Prototypes come from `git worktree list --porcelain`, keeping paths whose last component is `<KEY>` or starts with `<KEY>-`. This now matches `uedge-wt/AIUE-47` as well as `AIUE-47-serial*`. There is one tip per branch (the local one, with ahead/behind against `origin/`). |
| I1-m3 Default-results filter | **Fixed, inverted.** "No change to built or run-time code" applies only when every path is under `docs/`, `.claude/`, `tests/` or `.github/`, or is `*.md`, `.gitignore` or `.mcp.json`. Any other path (`pyproject.toml`, rate/data files, `*.inc`, package `*.py`, …) needs a sourced statement or "not recorded", and the statement gives the commit it was measured on. |
| I1-m4 Epic-comment update path | **Answered and hardened.** The installed `addCommentToJiraIssue` schema, read in this session, describes `commentId` as "ID of an existing comment to update. If omitted, a new comment is added". `getConfluenceCommentChildren` and `createIssueLink` are both in this session's deferred Atlassian tool list. If the update fails, Step 7 now adds a new comment, "Supersedes comment <id>", instead of stopping. The dry-run rule stays an allowlist; the ban list is now framed as examples ("in particular"). |
| I1-m5 "Delivered" for unmerged work | **Fixed.** There is a separate class, **Met (on unmerged branches)**. The template says "What it delivered" for merged work and "What the branch contains" for unmerged work. "Partly met" must name the missing parts. Reviewer check 3 requires all of this, and section 10 lists contradictions. |
| I1-m6 Procedural gaps | **Fixed.** Step 6 question 4 (Done) is asked only if every item is answered with close or defer; otherwise it is not offered until the answers allow it. Follow-up tickets have no parent unless the owner names an epic, and never the epic being closed. The metadata has a "This page" field, filled after the page is created. The dry-run fallback is `${TMPDIR:-/tmp}/closeout/`, the same name as the primary. The review metadata now carries counts as in `create-prd`. |
| I1-m7 Conflict with `feature/v9-ai-adversarial-ticket-review` | **Left for merge time, as directed.** The resolution keeps both sides. In `CLAUDE.md`, keep that branch's "Refactor …" and "Bug …" rows and this branch's "Large epics" row. In the reviewer `description`, list create-prd → PRDs, end-to-end-feature/plan-feature/execute/implement-fix → plans and implementations, and close-epic → close-out records. The stage list is `spec`, `plan`, `implementation`, `prd`, `closeout`, keeping that branch's "reference" bullet. Keep both new stage sections between the PRD and implementation stages. The ID examples are `S`, `P`, `L`, `I`, `C`. For Output, take that branch's absolute-path wording and its "Not independently verified (environment)" section, and add the close-out naming example; the close-out stage's "Not independently verified" list belongs in that section. |

## Close-out stage test

| Finding | Response |
|---|---|
| **C1-M1** Draft stale against the planning branch (`82b5be8`) | **Fixed in the skill.** It now has a snapshot header, reviewer check 2 (freshness), and a Step 7 re-check before publishing. **Fixed in the r2 draft:** it is gathered at planning tip `82b5be8`. It records the owner's AIUE-62 approval, the owner's requests (cost study, close-epic skill), the post-fix RHS probe (B1, results, AIUE-58 row), and the `AIUE-61-cost` worktree with its uncommitted `ppp/` changes. AIUE-54 I1-M4 stays open until the AIUE-54 section records the decision. Section 9 lists `feature/v9-ai-close-epic`. |
| **C1-M2** Owner item (4) phi and AIUE-50 I1-m6 missing | **Fixed in the skill.** Step 3 lists every item of every owner-decision list. An item counts as answered only by an owner-attributed source, and "an experiment that answers the technical question still needs the owner's acceptance". "Accepted gaps with no ticket" are now listed, and the response-file grep includes "follow-up" and "not covered". **Fixed in the r2 draft:** both items are in section 8, and phi is also in section 5 and row 4. |
| **C1-M3** AIUE-46's post-APPROVE code changes not flagged | **Fixed in the skill.** The post-APPROVE rule borrows `end-to-end-feature`'s line: text only vs code, tests, data, behaviour or new results. It also covers changes committed *together with* the approving report. **Fixed in the r2 draft:** `f5fee63` is listed as unreviewed (with its three files), and AIUE-55's `01e2d8e` is listed as new results after APPROVE. Every other post-APPROVE commit is classified as text only, per ticket. |
| **C1-M4** Clang workaround credited to the owner without a source | **Fixed.** The r2 draft marks it "Attribution unverified". It cites the breakdown's own "(owner, 2026-10-15)" marker, written by the agent's commit `ed33738` at 00:03 at the start of the unattended run. Step 6 asks the owner to confirm it. |
| C1-m1 Row 7 and AIUE-47's serial check | **Fixed in the r2 draft.** It cites `AIUE-53-validation.txt` R2-1 (l.317, l.419) on `460aa5f`/`d137d53`, and notes that the tip differs by a `bbb.v` `#` description only. It states that 47 and 56 were never built or checked together (AIUE-56 validation l.128). The skill now asks for this kind of cross-ticket evidence. |
| C1-m2 Class labels | **Fixed.** The skill says "use only these classes", including Met (on unmerged branches). In the r2 draft, row 3 and UX use that class, and Q is "Partly met" and names the missing RHS times. |
| C1-m3 AIUE-62 has no default-results line | **Fixed.** The skill says "every ticket gets a line", and the r2 draft has one. |
| C1-m4 §7 lacks "who agreed" | **Fixed.** The template asks for "who agreed ('not recorded' if no source says)". The r2 draft's section 7 is a table with that column, including the AIUE-61 rescope. The rescope also has a section 5 row. |
| C1-m5 Per-ticket base deviations | **Fixed.** The skill records "every ticket whose actual base differs from the breakdown, per ticket". The r2 draft states this for AIUE-49 (contains 46 only) and AIUE-54 (doesn't contain AIUE-52), and lists the rest in section 7. |
| C1-m6 Docker credited to the owner | **Fixed.** The r2 draft marks it "Attribution unverified" because the source is passive. |
| Stage: no Atlassian access | Answered by I1-B2 (the snapshot). |
| Stage: sources that move | New reviewer check 2 (freshness). The record states its snapshot. |
| Stage: unclear "unreviewed after APPROVE" | Answered by C1-M3 (the text-only rule, borrowed). |
| Stage: check 6 vs dry-run status; severity; REJECT | Check 7 now names all four statuses. Severity: a number whose error changes what it shows is MAJOR, a rounding or wording slip MINOR. REJECT is defined for a record: one that can't be made true from its sources. |
| Stage: scratch worktrees, carried minors, evidence across tickets, dry-run appendix | All four are now in the stage (checks 3, 4 and 8) and the skill (Step 1 prototypes, Step 3 carried minors, Step 1 evidence across tickets, the dry-run appendix with sources). |

## Second dry run (AIUE-8, read-only)

The run was read-only: Atlassian reads only, no repo writes, and output in the scratch directory.

The verdict is unchanged: **not complete**. 0 of 17 children are Done, nothing is merged, and criteria 1, 6 and 8 are
not met.

Differences from the first draft:
- It now has the snapshot.
- The owner's AIUE-62 approval and the two new requests are recorded.
- Five owner items are open; the first draft had three plus one shown as answered.
- Two unreviewed post-APPROVE changes and one accepted gap with no ticket are added.
- The replay prototype commits are on no branch, and the cost-study worktree is dirty.
- Six control worktrees are named with their records.
- AIUE-47 and AIUE-56 were never tested together.
- The PRD's carried minors each have a disposition.
- Two attributions are downgraded to unverified.
- It finds a new contradiction: Jira 10009 says AIUE-57 was red on "the C1-fixed build (AIUE-56)", but the AIUE-57
  validation record says the build was the C1 swap proxy, and that no fixed build existed then.

The r2 run also changed the skill, in the same commit `9660c36`. Comment bodies are stored as markdown. Page bodies that match the repo copy are
stored as a blob hash plus a comparison note. Commits that exist only on a detached HEAD are flagged. Named controls
are told apart from lost work. New results added to a document count as an unreviewed change. Results come from the
record a comment summarises.
