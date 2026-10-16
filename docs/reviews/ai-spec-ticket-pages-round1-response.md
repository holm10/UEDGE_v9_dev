# ai-spec-ticket-pages review round 1 — response

The verdict was REVISE (0 BLOCKER, 2 MAJOR, 5 MINOR). Every finding is fixed in `cccb4b6` on
`feature/v9-ai-spec-ticket-pages`. The coordinator set the defaults for I1-M1, and the owner may change them.

The selftest (`.claude/skills/ticket-page/selftest.sh`) now gives **137 passed, 0 failed** (it was 104). Both hooks
report OK:
- `change_kind.py --staged`;
- `check_context_refs.py --changed origin/v9-develop`.

There were no Atlassian writes.

| Finding | Fixed where / how |
|---|---|
| **I1-M1** backfill writes false records | **Status rule.** `spec` Step 6b backfills only children in To Do or In Progress; the rest are listed as "skipped (status <s>)". This is the coordinator's default; the owner may change it. <br>**Backfill header.** A backfilled skeleton has a machine-readable `> **Backfilled:** <date> · page created by <skill> after the ticket was filed (Jira status then: …)` field, says `**Plan:** not mirrored here`, and carries a placeholder "Not mirrored here yet … the plan, if any, is on the ticket branch". `ticket --backfill` makes the source line read "Scope as read on <date>", not "as filed". <br>**Branch.** The branch is described only as checked (`branch_state`: "checked: not created yet", "exists", or "not checked"). <br>**Fallback.** It uses `PIV record: record started`. <br>**close-epic.** It never infers "never planned" from a placeholder: on a Backfilled page, or for a ticket beyond To Do, it looks for the plan on the ticket branch and writes "plan not mirrored". <br>Selftest K10 and K11. |
| **I1-M2** `find` answers "create" on missing evidence | Exit 3 now needs a complete container listing **and** a readable comment list (with `--fallback`: the comment list). Everything else is exit 2. <br>ADF comment bodies are flattened. Both MCP response shapes are read (REST, and `issues.nodes`/`content.nodes`). A paged comment list is refused. <br>`spec` 6b.2 and ticket-page 2.6 pin `responseContentFormat: "markdown"`. <br>Fixtures are read-only responses taken from the hook log, with author and session fields removed. Selftest K1–K6. |
| **I1-m1** Branch-line tier | The tier looks only at an entry's own lines, so a phase heading is no longer a false "several". It accepts plain and bold `Branch:` lines and `v9-ai-<KEY>-` branches. Both callers handle exit 2 (use the Jira description and report it). Selftest K8. |
| **I1-m2** stale link comment, moved tickets | A listed page wins and the stale ids are reported. `not_listed` means confirm with CQL `id = <id>`: if the page exists (a moved ticket keeps its page under the old epic), use it; if it is gone, rerun with `--gone`. `close-epic` follows a moved ticket's link comment to its page. Selftest K7. |
| **I1-m3** cost and batch side effects | Stated per ticket: two writes and two prompts. AIUE-8 example: 5 pages, 10 prompts. One container listing is taken before the batch and one after. `--pages-only` never republishes the breakdown page. A normal run checks the breakdown page's version before updating it. |
| **I1-m4** wording | The template line is bold. The search is described as a title search with a prefix filter. "Never a second page" is reworded to "a re-run never adds one; a concurrent run is detected". The J14 label is corrected. Step 2.8 also replaces a `none (…)` line. |
| **I1-m5** selftest gaps | Now covered: the legacy `Plan page:` comment (K1), the PIV-record count and the cap (K1, K6), the Branch tier (K8), an id that is recorded but not listed (K7), and `--parent-id` (K9). |
