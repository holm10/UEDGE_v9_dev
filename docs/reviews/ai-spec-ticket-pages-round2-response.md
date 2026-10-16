# ai-spec-ticket-pages review round 2 — response

The verdict was APPROVE (0 BLOCKER, 0 MAJOR, 5 MINOR). The coordinator asked for all five minors to be fixed before
the branch is pushed. They are in `c373f7f` on `feature/v9-ai-spec-ticket-pages`.

The selftest gives **146 passed, 0 failed** (it was 137). Both hooks report OK:
- `change_kind.py --staged`;
- `check_context_refs.py --changed origin/v9-develop`.

I grepped the branch diff (`e52a44d..c373f7f`) for the cloud id, account ids, email, the site host, the user name and
local paths. The only hits are the synthetic `/Users/someone` paths that the masking tests use.

**History still holds the old data.** Commit `cccb4b6` still contains the original fixtures: the real cloud id and
the AIUE-61 comment text. Pushing the branch as it is publishes them. Squash `cccb4b6` with `c373f7f` before pushing
(see the report to the coordinator).

| Finding | Fixed where / how |
|---|---|
| **I2-m1** `_links.next` ignored | The listing counts as complete only when one of the files given links no further page (REST `_links.next`, nodes `pageInfo.hasNextPage`) and the files hold at least the stated total. Otherwise exit 2, even when the first page has a hit. Selftest L1. |
| **I2-m2** stale-record rule disagrees | There is now one rule, used in the helper's note, ticket-page steps 2.6 and 2.7, and spec 6b.2: the listed page wins, and each stale id is confirmed once with CQL. If the stale page is gone, that's fine (`--gone` drops it); if it still exists, there are two existing pages, so stop. Selftest L2. |
| **I2-m3** tenant id and internal text in the fixtures | The fixtures keep their real shapes with synthetic content: the cloud id `00000000-…` (also inside the ARIs and their base64), `example.atlassian.net`, neutral comment, description, summary and excerpt text, and the same `Plan page:` link line and page ids. The K tests pass unchanged. |
| **I2-m4** a re-run doesn't repair a missing link | `find` reports `missing_link_comment`, which is also true when the only link comment names a stale page. On exit 0, spec 6b.2 posts the missing link comment and adds a missing breakdown `**Ticket page:**` line. In the fallback it adds the missing `none (…)` line. The status rule applies to these repairs. Selftest L3. |
| **I2-m5** cost example count | Now reads "the 14 In Review children are skipped (12 of them have no page)". |
