# ai-ticket-pages review round 2 — response

Verdict REVISE (1 BLOCKER / 0 MAJOR / 7 MINOR). All eight findings are fixed in `ec1b75b` on
`feature/v9-ai-ticket-pages` (history on `4faed39`: `525c9b2`, `88a6560`, `cbe4e7b`, `ec1b75b`). No Atlassian writes
this round.

Every helper path is now tested end to end in a throwaway repo by the new `.claude/skills/ticket-page/selftest.sh`
(Atlassian responses and the PostToolUse log simulated): **41 passed, 0 failed**. Covered paths: new page (stub →
`**Ticket page**` line committed → `--new-page` first fill → verify → record → `--local` → `--current` after a
simulated Confluence round trip), the refusals, verify after a failed update and one retry, a dry run, the RCA mirror,
and the Jira-fallback text checks. Also re-run on the reviewer's inputs in `/tmp/rev2tp` (fresh outbox):
- stub + `--new-page` → exit 0;
- `b1_partial.md` → exit 2, naming the missing headings;
- `h1_rt.md` → the `# ran: pytest -k D_only` line is kept.

On the live data, `render --local --page-version 4` for AIUE-61 rebuilds a body byte-identical to version 4. The new
sanitiser refuses none of the existing plans and RCAs in any worktree.

| Finding | Fixed where / how |
|---|---|
| **I2-B1** stub page can't be filled | `render --new-page --current <page as read>`. It accepts only a page whose content is exactly the stub (`ticket_page.py stub --key <KEY>`: "Plan page for <KEY>; content follows.", in any of the accepted forms), and only while the state file has no recorded version. Every other refusal is kept. SKILL "Page missing": create with the stub; `state --set page_id=<id>` (no version); commit the `**Ticket page**` line; read the one-line page; first fill with `--new-page`; update, verify (`--after-version 1`), record. A failed first fill leaves the stub and is repeated at the next flush. Selftest A2–A6: stub without `--new-page` → 2; non-stub with `--new-page` → 2; first fill → 0 (header cites the commit with the `**Ticket page**` line); `--new-page` after a recorded version → 2. |
| **I2-m1** partial headings; `#` lines | `render` refuses unless all four log headings are present (lists the missing ones). Only the four log headings and the mirror heading end a section on read-back; other heading-like lines stay in their entry. Entry lines starting with `#` (outside fences) are escaped as `\#`. Also refuses a page with fewer entries than the last body this worktree sent, counted after re-adding its own entries from the sent log; `--allow-fewer` is for a deliberate correction (SKILL "Corrections"). Selftest B5, B6, B9. |
| **I2-m2** `--local` unchecked | `render --local` requires `--page-version N` and refuses unless N equals `state.version`. SKILL step 3.1 passes the CQL number. Selftest B1–B3. |
| **I2-m3** cost; validate milestone | The Cost section now counts both sides: about 14k output plus about 14k input per flush for AIUE-61, so about 28k of context growth per flush and about 140k for a 5-flush `end-to-end-feature` session. The page read-back adds about 14k. It advises handing a flush to a fresh agent rather than skipping it. "Deliberate batching of `validate`" states the narrowing as a deviation for the main session to confirm: every validate result reaches the page (failures verbatim), but inside `execute` or a review round it rides on that step's closing flush. The milestone table row says the same. |
| **I2-m4** validate key; dry run | `validate` takes `--ticket <KEY>`, else the branch name, else the `**Ticket page**` line or H1 of the plan/RCA. `execute`, `implement-fix` (whose issue branches have no key) and `end-to-end-feature` pass `--ticket`. `validate` takes `--tracker-dry-run` (passed as `--dry-run`: nothing is queued). |
| **I2-m5** running-summary update | The skill checks that the returned comment id equals `state.fallback_summary_id`. On failure or a different id it posts once a comment starting "Supersedes comment <id>." with the summary (as `close-epic` does), records it, sets `fallback_superseded=1`; a second failure → nothing more, reported. That makes at most 9 `PIV record` comments (configuration row updated). The update path itself is still not exercised live (no Atlassian writes this round). |
| **I2-m6** verify after a failed update; retry | `verify --after-version V` counts only a logged update that returned a version above V. Otherwise exit 3 "the update just made was not logged as successful". Skill: verify only after an update that returned a version; exit 1 → **one** retry, then verify with `--after-version` = the first update's version; a second mismatch → record nothing, report, stop. "Another writer" compares with V + this flush's own successful updates, so a jump explained by its own retry is not a finding. Selftest C1–C3. |
| **I2-m7** cluster paths, `file://` | Roots added: `homes`, `scratch`, `gpfs`, `global`, `lustre`, `nfs`, `work`, `project(s)`, `data`, `p`, `g`, `usr/workspace`, `usr/WS<n>`. `file:///…` URLs are masked like any other path. Selftest A4 and F2: `/scratch/…`, `/p/lustre1/…`, `/gpfs/u/…`, `/global/homes/…`, `/g/g19/…`, `/usr/workspace/…`, `file:///Users/…` are all masked. The skill now names the covered roots and says other absolute paths are left as they are. |

Not changed and still for the main session:
- the `validate` batching (I2-m3) needs confirmation as a deviation;
- the `commentId` update has not been run live;
- the unquoted `[...]` argument hints follow the base's existing style.
