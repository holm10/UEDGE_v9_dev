# Response to the close-epic review, round 2

The report is `docs/reviews/ai-close-epic-round2.md`. It covers two jobs:
- **Job A**, the skill: REVISE, 0 blocker / 1 major / 3 minor.
- **Job B**, the close-out stage tested on the r2 draft: REVISE, 0 blocker / 2 major / 4 minor.

The fixes are in `feature/v9-ai-close-epic` `c9fa77a`. They touch `.claude/skills/close-epic/SKILL.md` and the
close-out stage and output line of `.claude/agents/uedge-reviewer.md`.

The dry-run draft was updated to r3 for the flagged items only. Everything stayed read-only: the Jira children,
transitions and Confluence comments were re-read with exact times. The r3 files are:
- `scratchpad/closeout/AIUE-8-closeout-draft-r3.md`
- the snapshot in `scratchpad/closeout/AIUE-8-closeout-sources/`

## Job A (skill)

| Finding | Response |
|---|---|
| **I2-M1** An unmet gating criterion never becomes an owner question | **Fixed.** The first entry of Step 3's not-done list (now named "the open items") is "each gating criterion whose class is not Met or Superseded, with its class and the missing part". The epic is complete only if that list is empty. A close-out draft always has at least one open item, and "if the list is empty while a criterion is unmet, the list is wrong". Step 6 question 1 covers "each open item, unmet gating criteria included"; for a criterion, "close anyway" means the owner accepts it as unmet. The status table's `Closed by the owner` row needs an answer for every open item, unmet criteria included, with a + d equal to the number of open items. `Close-out draft` needs n ≥ 1. Reviewer check 7 says the same and makes "a draft with 0 open items, or Closed over an unmet criterion without the owner's answer" a BLOCKER. |
| I2-m1 Stacked tickets merged through one merge share `M` | **Fixed.** When two children resolve to the same merge or squash commit, or `M^1..M^2` contains another child's tip, each child's commits, diff and records come from `<parent-tip>..<tip>` under the actual-base rule, and the shared merge is noted. Tips come from the branches or, if those are gone, from the snapshot, the progress log or the Jira comments. If they can't be recovered, the range is reported as shared and nothing is attributed ticket by ticket. |
| I2-m2 No git-only fallback for squash or rebase merges | **Fixed.** Without `gh`, the skill also tries: <ul><li>the key in GitHub's humanised squash title or in commit bodies (`<PROJ>[- ]<N>`);</li><li>a PR number or branch name from the progress log or Jira;</li><li>`git cherry origin/v9-develop <branch>` for rebase merges;</li><li>`git patch-id --stable` of the branch diff compared with candidate first-parent commits, for squashes.</li></ul>If none of these finds the merge, it is "undeterminable" for that child. "Merge not located" becomes an open item when Jira says Done or the branch is gone, and the limitation goes in section 10. This path is untested here: there is no squash merge in the repo and no `gh`. |
| I2-m3 Reviewer can't check Jira freshness | **Fixed.** Check 2 is now "Freshness (git only)": the planning tip, ticket tips, merges, prototype HEADs and dirty counts. Jira and Confluence freshness is the author's Step 7 re-check, and Step 7 now names it as the only one. The reviewer checks that the snapshot is internally consistent and lists the rest under "Not independently verified (environment)". It also notes that the snapshot files are the author's copies, so agreeing with them shows consistency, not faithful reads. |

## Job B (stage test on the r2 draft)

| Finding | Response |
|---|---|
| **C2-M1** `AIUE-50-scratch` commits on no branch missed; the worktree misdescribed | **Fixed in the skill.** Before writing "not named in a record", grep the records for the worktree's name and HEAD sha (`git grep -n -e <name> -e <sha7> <rev> -- docs .claude/plans`, over the planning tip and every ticket tip). Commits on no branch are listed (`git log --oneline <merge-base>..<HEAD>`). Reviewer check 4 repeats the grep. **Fixed in r3:** the snapshot's prototype table was redone with that grep, and every worktree is named in some record (three were labelled "not named" before: AIUE-47-serial, AIUE-50-scratch, AIUE-56-serial). `AIUE-50-scratch` (`de2d327`, `c9d2872`, `14abb0d` on no branch; `AIUE-55-implementation-round1.md` l.166-169) is in section 8 with the owner's choice of keep, push or discard. The AIUE-61 prototype commits are on no branch and are also cited as RCA evidence (RCA l.75, l.95); r3 now says so. |
| **C2-M2** AIUE-56 `35974c9` (and AIUE-55 `3bf736c`) not listed | **Fixed.** The skill has a third post-APPROVE class, **requested fix**: a change to a document or record that does what the approving review's own findings asked, cited by finding id, and no more. It is listed but not an open item. The tie-breaker: compare the diff with the findings and the response, and every changed claim must trace to a finding. A change to code, tests, data or behaviour is still an *unreviewed change* even if a finding asked for it, because `end-to-end-feature` requires a new round. That is why AIUE-46 `f5fee63` stays open. **r3:** `35974c9` is a requested fix (I3-m1, I3-m2, I3-m3; the reviewer's own reproduction gave "median 1 / p90 9 / max 83.6", "exactly a factor 2 low", and the commit records 2 / 18 / 167). `3bf736c` is a requested fix (I4-m1, I4-m2, per the r4 response). `01e2d8e` stays an unreviewed change: new results nobody asked for in review. The other post-APPROVE commits are reclassified the same way (47 `63370bd`, 49 `6ddbf70`/`c02dd42`, 50 `32ac1af`, 57 `8ee189d`: requested fixes). |
| C2-m1 Freshness: planning tip `55648d2`, `ai-consolidate`, scratchpad work | **Fixed in r3.** The snapshot is at planning tip `55648d2`. Section 9 cites the round-1 and round-2 close-epic review records. Section 10 lists `uedge-wt/ai-consolidate` and the scratchpad studies under "Not sources". The skill now says that agent work outside the repo is "in progress, not a source", and the stage says it may be named as in progress but never cited as evidence. |
| C2-m2 Open owner-item count | **Fixed in r3.** §1 now says "decision 9 and three other owner items", which matches §5. |
| C2-m3 Snapshot slips | **Fixed.** The cost-study figures are from `git diff --numstat`: `ppp/omp_parallel.F90` 70/12 and `ppp/ppp.v` 2/0. `jira-children.json` now has `resolution` and `created` for all 17 children (and the epic's `created`), from a re-read at 18:07:14Z. Read times are exact per file: Jira transitions and Confluence comments and descendants 18:07:28Z–18:07:54Z; a CQL check at 18:08:59Z confirms both pages' `lastModified` is unchanged. One exception: the breakdown's v3 version message comes from the round-1 page read, whose exact time was not recorded. The note in `confluence-pages.json` says so and relies on the unchanged `lastModified`. |
| C2-m4 Class for a criterion resting on branches never tested together | **Settled in the stage and the skill:** at best **Partly met**, with the combined check as the missing part. In r3, row 2 is now Partly met (met for AIUE-47 and AIUE-56 each, never together). |

## Consolidation note

The consolidated reviewer output heading is "Not independently verified (environment)". The close-out stage now uses
that exact name in its opening paragraph and in check 2. The output line on this branch now lists the same sections
in the same order as `feature/v9-ai-adversarial-ticket-review` and `feature/v9-ai-consolidate`: Verdict, Summary,
Findings, Status of previous findings, Not independently verified (environment), What was checked and how. That
removes one difference at merge time.

## Not fixed

- **Squash, rebase and shared-merge recipes are untested.** The repo has no such merges and `gh` is not installed.
  They are written from git semantics and stated as such.
- **Breakdown version message re-read.** I did not re-read the breakdown page body to give its version message an
  exact read time. The version is confirmed unchanged by `lastModified` (CQL, 18:08:59Z).
