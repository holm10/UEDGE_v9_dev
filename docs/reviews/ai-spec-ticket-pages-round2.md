# Review: ai-spec-ticket-pages, implementation (AI-layer change), round 2

Branch `feature/v9-ai-spec-ticket-pages`, worktree `/Users/holma/Documents/uedge/src/uedge-wt/ai-spec-ticket-pages`,
base `origin/v9-develop` `e52a44d`, tip `cccb4b6`. Round 1 reviewed `21edb76`. This round reviews
`git diff 21edb76..cccb4b6`: 12 files, including 5 new fixtures.

## Verdict

**APPROVE**: 0 BLOCKER, 0 MAJOR, 5 MINOR.

## Summary

Both round-1 MAJORs are resolved, and I checked each fix myself.

- **Backfill (I1-M1).** Backfilled pages now carry a `Backfilled` status and header field. They say "as read on
  <date>" and "not mirrored here", and only To Do and In Progress children get one. I rendered a backfilled skeleton
  and read every sentence: each one is true for the ticket's state. `close-epic` no longer infers "never planned" from
  the placeholder.
- **`find` (I1-M2).** `find` now answers "none" (exit 3) only when it has a complete listing and a readable comment
  list. Every other uncertain input gives exit 2. It flattens ADF comment bodies, reads both MCP response shapes, and
  is tested on real responses.
- **Checks.** The selftest passes (137/137), and both hook checks are clean.
- **Fixtures.** They contain no personal data: no email, account id, avatar, display name, session id or token. They
  do add the Atlassian tenant's cloud id, which was not in the public repo before (I2-m3).

The remaining minors are about `find`'s handling of incomplete listings and stale records, the re-run repair of a
missing link comment, and one count.

## Findings

### BLOCKER

None.

**Personal-data check on the fixtures** (the prompt asked for a BLOCKER if any is found): **none found.**

- **Searches run.** I grepped `.claude/skills/ticket-page/fixtures/*` for `@`, `accountId`, `gravatar`, `avatar`,
  `70121:`, `holm`, `sessionId`, `invocationId`, `token`, `email`, `displayName`, `publicName`, `/Users`, `holma`,
  `andreas`, `Bearer`, `requestId` and `traceId`.
- **Every JSON key path.** I listed them for all 5 files. There are no `author`, `updateAuthor`, `createdBy` or
  `profilePicture` fields, and comments carry only `id`, `body`, `created` and `updated`.
- **ADF attributes.** The only node attributes in the ADF fixture are 4 `link` hrefs to Confluence pages. There are no
  `mention` nodes.
- **The two `base64EncodedAri` strings** decode to `ari:cloud:confluence:<cloudId>:content/<page id>`.
- **What the hits are.**
  - `avatar`: the `issuetype` icon (`universal_avatar/view/type/issuetype/avatar/10307`, plus `avatarId`). That is the
    Task type's icon, not a person's.
  - `holm`: only in the site host `holm10uedge.atlassian.net`. That host is already public on `origin/v9-develop`
    (`docs/prds/AIUE-8-investigate-non-deterministic-openmp-jacobian.md:3-4`), and `origin` is the public GitHub repo
    `holm10/UEDGE_v9_dev` (`gh repo view` → `PUBLIC`).
- **The author's raw copies are not committed.** The originals in `/tmp/dry2/children.json` do contain `createdBy`
  with an email, account id and avatar. The committed `AIUE-8-container-children-cql.json` has none of these.
- **No earlier commit leaked them either.** I ran `git show` on each of `6f457ac`, `21edb76` and `cccb4b6`, grepped for
  the same patterns, and found nothing.

### MAJOR

None.

### MINOR

**I2-m1. `find` ignores `_links.next`. An incomplete listing can hide a second page, or give "none".**
Location: `ticket_page.py` `_search_hits` / `cmd_find` (completeness check).

- Completeness is judged only from `totalSize`/`totalCount`. A REST result with `_links.next` but no `totalSize` counts
  as complete. My test (`nototal.json`) returned rc=3, "no page", for a key not on that page.
- When the given page of an incomplete listing already contains one hit for the key, `find` returns 0 without checking
  completeness. A duplicate on the next page is missed: `p1.json` (1 of 2) → rc=0, page 7. Adding `p2.json` → rc=2.
- **Low practical risk.** The real REST fixture carries `totalSize`, and the nodes fixture carries `totalCount`. The
  skill text says to follow `next`, and `spec`'s listing after the batch catches duplicates.
- **To resolve:** treat a present `_links.next` as incomplete. Optionally, report `listing_complete: false` on exit 0.

**I2-m2. Stale records: the skill text, the helper's note and step 2.7 disagree.**
Location: `ticket-page/SKILL.md` step 2.6 (first bullet) and step 2.7; `spec/SKILL.md` 6b.2; `ticket_page.py`
`stale_records` note.

- When a page is listed and a different id is recorded, the helper returns 0. Its note says to confirm the recorded id
  with `CQL id = <id>`, and that if it still exists there are two pages: stop and ask.
- The skills say `stale_records` are "reported, not acted on".
- Step 2.7 says "two ids from different records → stop and ask".
- So an agent following the skill text writes to the listed page without checking whether the recorded one still
  exists.
- **To resolve:** one rule in all three places. For example, confirm each stale id once: gone → `--gone`, exists →
  stop.

**I2-m3. The fixtures add the tenant cloud id and internal ticket text to a public repo. Owner awareness only.**
Location: `fixtures/*.json`.

- The cloud id `710f4b18-…` was not in the repo before (`git grep` on `origin/v9-develop`: 0 hits). It now appears in
  every `self` URL, in the `ari` fields and in `base64EncodedAri`.
- It is a site identifier, not a credential or personal data. `find` never reads those fields.
- The AIUE-61 comment bodies (the cost study, the owner's decisions Q2-Q6, "not pushed", scratch-tree names) become
  public with the branch.
- **To resolve (optional):** the owner confirms this is acceptable, or the `self`/`ari`/`base64EncodedAri` values are
  replaced with a placeholder host. K1-K4 don't depend on them.

**I2-m4. A re-run does not repair a missing link comment.**
Location: `spec/SKILL.md` 6b.2 (exit 0 → "leave it as it is and report it") and 6b.4.

- Suppose a run created the page but failed before the `Ticket page:` comment or the breakdown commit.
- The re-run (or `--pages-only`) finds the page by the listing and leaves it. The link comment and the breakdown's
  `**Ticket page:**` line are never written.
- Later skills still find the page by the listing, so nothing breaks. But the "record the id where later skills find
  it" step stays incomplete, and `prime` (which reads link comments) misses it.
- **To resolve:** on exit 0 with an empty `recorded`, post the link comment and fill the breakdown line.

**I2-m5. The cost example miscounts the skipped children.**
Location: `spec/SKILL.md` "Cost and prompts".

- The example says "the 12 In Review children are skipped". The re-run dry run skips 14 In Review children.
- 12 of those 14 have no page. AIUE-57 and AIUE-61 have one.
- **To resolve:** "the 14 In Review children are skipped (12 of them have no page)".

## Status of previous findings

**I1-M1 (backfill truthfulness and `close-epic`'s inference): resolved.**

- **Status rule.** `spec` 6b now backfills only To Do and In Progress children. It skips the rest and lists them. The
  rule is attributed truthfully: "Default set by the coordinator … the owner may change it". The owner's own decision
  is still open; see "Not independently verified".
- **Skeleton header.**
  - With `backfilled` set it says "Plan: not mirrored here".
  - It adds a `**Backfilled:**` field: date, skill, Jira status then, scope as read then, plan not mirrored, earlier
    history in the Jira comments.
  - It says "This page is the ticket's PIV record from now on" instead of "created when the ticket was filed".
  - The Plan placeholder is `PLAN_BACKFILLED`.
- **Branch claim.** It is now `branch_state`-driven: absent → "checked: not created yet", exists → "exists…", missing
  → "not checked". Nothing is assumed.
- **Ticket source line.** `ticket --backfill` says "Scope as read on <date>, when this page was created after the
  ticket was filed".
- **What I checked.**
  - I re-ran `/tmp/dry2/run.sh` and read the AIUE-51 backfill body (To Do, branch checked absent) sentence by
    sentence. Each is true.
  - The In Progress / branch-exists variant (K10) renders "exists; its plan, if any, is not mirrored here yet".
  - K10 greps that none of `not created yet`, `created when the ticket was filed`, `Scope as filed`, `not written yet`
    or `(planned` appear. K11 covers the unchecked-branch case.
- **`close-epic`.**
  - It now says a placeholder means only "plan not mirrored", and never "never planned".
  - With a `**Backfilled:**` field, or with a Jira status beyond To Do, it looks for the plan on the ticket branch.
  - Only a To Do ticket with no plan anywhere counts as not planned.
  - The header field it keys on is the one the helper writes (`> **Backfilled:** …`).
- **Fallback.** A backfill posts `PIV record: record started` with no "planned" claim. The `ticket filed` template's
  branch state is now "as checked". In `/tmp/dry2`, AIUE-58 (In Review) is skipped.

**I1-M2 (`find` exit 3 without evidence; ADF bodies): resolved.**

- **The rule in the code.** `cmd_find` returns 3 only after:
  - a non-empty, complete `--search` (totals checked), and
  - `--comments` parsed by `_jira_comments`.
  With `--fallback`, it needs a parsed comment list.
- **Everything else gives 2.** I reproduced these, and K5 covers them:
  - no inputs;
  - comments only;
  - a listing only;
  - a body of unknown form (`42`, `null`);
  - a paged comment list (1 of 5);
  - an incomplete listing (1 of 3);
  - a comments file that is a string, or an issue without `fields.comment`;
  - `--fallback` without comments.
- **ADF.** `adf_text` flattens bodies with strong → `**`, code → `` ` ``, and inline cards → URL.
  - K3 finds the link comment in the **real** ADF fixture.
  - I flattened all 4 real ADF comments: the legacy `Plan page:` comment yields page id `2293761`.
  - My own ADF with a bold `Ticket page:`, an `inlineCard` and a code-marked id → rc 0, page 300.
- **Format pinned.** `spec` 6b.2 and ticket-page step 2.6 now pin `responseContentFormat: "markdown"` and ask for all
  comments.
- **Fallback.** `find --fallback` makes the `ticket filed` post conditional: exit 0 → post nothing, 2 → report, 3 →
  post. K6 covers markdown, ADF, none, no comments and the cap.
- **Real response shapes.** Both are exercised: REST `results[].content`/`totalSize` and `content.nodes`/`totalCount`
  (K1, K4), and the issue as `fields.comment` or as `issues.nodes` (K1, K2).
- **Remaining gap.** The paged-comment check depends on `total`. The real markdown fixture has no `total` (its
  comment block holds only `comments`), so paging can't be detected in that shape. With tickets of a few dozen
  comments this is theoretical. I note it, not a finding.

**I1-m1 (Branch-line tier): resolved.**

- The tier now looks only at an entry's own lines (up to the next heading of any level). It accepts the plain and the
  bold `Branch:` forms, and `v9-ai-<KEY>-`.
- Exit 2 is documented in both callers ("→ the Jira description, and report it").
- K8 covers all five cases:
  - a plain line under a phase heading → one entry;
  - an `ai` branch;
  - `T-4` against `T-46`/`T-47`/`T-48`;
  - two entries → 2.
- K8 checks that T1's text is extracted alone.

**I1-m2 (stale and moved records): resolved.** I2-m2 is a wording follow-up.

- A listed page wins, and stale ids are reported (K7). A recorded-but-unlisted id → `not_listed`, with a confirm step
  and `--gone` (K7).
- A moved ticket keeps its page under the old epic. `close-epic` now picks it up through the link comment and
  `CQL id`.

**I1-m3 (cost and batch side effects): resolved.**

- The per-ticket reads, writes and prompts are stated in `spec` "Cost and prompts" and in ticket-page "Cost".
- There is one container listing before the batch and one after it.
- `--pages-only` skips 6.6. 6.6 now also checks the breakdown page's version before overwriting it.
- The count in the example is slightly off (I2-m5).

**I1-m4 (wording): resolved.**

- The template line is `- **Ticket page:**`.
- `plan-feature` says "title search … filtered on the prefix".
- The race wording now says "two runs at the same time can still create two pages … detected and reported".
- J14 is relabelled.
- Step 2.8 covers a `none (no epic PRD page)` line.

**I1-m5 (selftest gaps): resolved.**

| Round-1 gap | Now covered by |
|---|---|
| Legacy `Plan page:` link comment | K1, on the real fixture |
| `piv_record_comments` | K1, K6 |
| Branch-line tier | K8 |
| Recorded but unlisted id | K7 |
| `verify --created` with the wrong parent | K9 → 3 |
| The 8-comment cap | K6, `piv_cap_reached` |

## Not independently verified (environment)

- **Live Atlassian behaviour.** I have no Atlassian access. These are untested against the live MCP server:
  - whether `getJiraIssue` markdown responses ever page comments;
  - whether CQL search results always carry `totalSize`;
  - the exact ADF shapes of future comments.
  The fixtures are real responses, with author and session fields removed; the author says so, and the key-path
  listing is consistent with that. They show the shapes as of 2026-10-16.
- **The owner's decision on the backfill status rule.** To Do and In Progress only is the coordinator's default, and
  the skill records it as such. The owner has not confirmed it. That is a decision for the owner, not a defect in the
  work.
- **Whether the cloud id and the AIUE-61 comment text may be public.** This is for the owner (I2-m3).

## What was checked and how

- **The diff, read in full** (`git diff 21edb76..cccb4b6`): helper, selftest, ticket-page, spec, close-epic,
  plan-feature, CLAUDE.md. The fixtures were inspected by key path and by flattening the ADF.
- **Selftest:** `bash .claude/skills/ticket-page/selftest.sh /tmp/rv2-st/w` → `RESULT: 137 passed, 0 failed` (24 s).
  I read K1-K11 line by line.
- **Hook checks:**
  - `uv run .claude/hooks/change_kind.py --range e52a44d..HEAD`: all 16 files are `process` on an `ai` branch → `OK`.
  - `uv run .claude/hooks/check_context_refs.py --changed origin/v9-develop` → `OK` (advisory list only).
  - `origin/v9-develop` = `e52a44d`.
- **Adversarial `find` runs** (`/tmp/rv2-find/`, run under bash with `uv run`):
  - no `totalSize` with `_links.next` → 3 (I2-m1);
  - page 1 of 2 with one hit → 0, both pages → 2;
  - an ADF `inlineCard` link comment → 0, `not_listed`;
  - a quoted link comment → 3 (not a real form);
  - a `mention` before "PIV record" → 3 (not a real form);
  - a `null` body → 2;
  - a comments value that is a string → 2;
  - an issue without comments → 2;
  - a plan with no line and a listing but no comments → 2.
- **Dry run:** `/tmp/dry2/run.sh`.
  - 5 To Do children would be backfilled. AIUE-48 and AIUE-51 come from the breakdown; AIUE-67, 69 and 71 come from
    the Jira description (exit 3).
  - 14 In Review children are skipped.
  - AIUE-61 through `find` on the real responses → page `2293761`.
  - AIUE-70 fallback: AIUE-58 skipped, AIUE-59 and AIUE-74 → `record started`.
- **Personal data:** see the BLOCKER section (the grep list, key paths, decoded ARIs, a per-commit `git show` grep,
  public exposure of the host checked with `git grep origin/v9-develop` and `gh repo view`).
