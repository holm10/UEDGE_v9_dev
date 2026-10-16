# ai-ticket-pages review round 3 — response

Verdict APPROVE (0 BLOCKER / 0 MAJOR / 3 MINOR, optional). The coordinator asked for all three minors to be fixed as
requested text and code fixes. They are in `e52a44d` on `feature/v9-ai-ticket-pages`, and each is covered by new checks
in `.claude/skills/ticket-page/selftest.sh`: **61 passed, 0 failed** (was 41). On the live data, re-rendering AIUE-61
with `--local --page-version 4` differs from version 4 only in the header's branch tip, because the AIUE-61 branch has
moved on to `4c3d095`.

| Finding | Fixed where / how |
|---|---|
| **I3-m1** stub or recreated page not routed to `--new-page` | `render` given a page that still holds only the stub (without `--new-page`) exits 2 with "the page still holds only the stub …: render it with --new-page". When a version is recorded for that page, it adds "check the page history first, then reset with: state --set version=". The recorded version and last body now belong to the page id stored with them (`state.page_id`): for another `page_id` the helper notes "the state file's version N belongs to page X …; treating the page as new". There, `--new-page` works, `--local` is refused, and the fewer-entries check is skipped. SKILL step 3.1 adds the stub rule, the recreated-page rule and the documented reset. The step-3.3 render command shows all three modes (`--local --page-version <N>`, `--current`, `--new-page --current <stub>`). Selftest G1–G5. |
| **I3-m2** running-summary cap not enforced on a created comment | New helper `summary` keeps the bookkeeping. `--check` runs before any call (exit 1 = stopped: make no Jira call). `--returned-id`: the same id means updated in place; a different id is adopted as the running summary and counts as the one superseding comment (no extra post); a second different id stops it. `--failed`: the first time, post one "Supersedes comment <id>." comment and record it with `--superseded-by`; the second time, stop. SKILL "Cap" rewritten around it, so at most 9 `PIV record` comments are posted and no Jira call is made once stopped. Selftest H1–H8. |
| **I3-m3** short roots mask bare words | Short or common roots (`global`, `nfs`, `work`, `project(s)`, `data`, `p`, `g`, `usr/workspace`, `usr/WS<n>`) only count when a path segment follows. The long roots are unchanged. Selftest I1 ("the /p option, /g flag, /global setting, /data-set, /project-x, /p.value, /work and /nfs" is unchanged) and I2 (`/p/lustre1/…`, `/g/g19/…`, `/global/homes/…`, `/data/…`, `/work/…`, `/usr/WS1/…` are masked). SKILL wording updated. |
