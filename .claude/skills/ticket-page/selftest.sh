#!/usr/bin/env bash
# End-to-end test of ticket_page.py (the ticket-page skill's helper) in a throwaway git repo, with no Atlassian calls.
# The plan and the RCA are local, untracked working copies (.claude/work/, gitignored), never committed; the page
# cites them by publish date and sha256. Cases: new page (stub -> page id in the state file -> --new-page first fill
# -> verify -> --local -> --current after a simulated
# Confluence round trip), the refusals, verify after a failed update and one retry, a dry run, the RCA mirror and the
# Jira-fallback text checks; then (J) the page `spec` creates when it files a ticket: Ticket section from the
# breakdown, skeleton, verified create, lookup by plan-feature, plan publish, execute / validate / review flushes, and
# the Ticket-section safety checks; (K) find on real read-only Jira/Confluence responses (fixtures/), its evidence
# rules, stale and moved records, the breakdown Branch-line match and the backfill header; (L) paged listings,
# the stale-record rule and the missing link comment; (M) the local plan: the mirror moves only on publish, the
# published copy's checks, extract-plan in a fresh worktree, --state-id, and git status staying clean. Other
# Atlassian responses
# and the PostToolUse hook log are simulated.
# Usage: .claude/skills/ticket-page/selftest.sh [workdir]   (default: a new temporary directory)
set -u
H="$(cd "$(dirname "$0")" && pwd)/ticket_page.py"; W="${1:-$(mktemp -d)}"; mkdir -p "$W"; cd "$W" || exit 2
echo "workdir: $W"
T="uv run -q $H"; R="$W/repo"; ST="$W/store"; PASS=0; FAIL=0
ok(){ if [ "$1" = "$2" ]; then PASS=$((PASS+1)); echo "PASS $3"; else FAIL=$((FAIL+1)); echo "FAIL $3 (exit $1, want $2)"; fi; }
git init -q "$R" && git -C "$R" checkout -q -b feature/v9-T-1-demo
printf '.claude/work/\n' > "$R/.gitignore"; echo demo > "$R/README"
git -C "$R" add -A && git -C "$R" -c user.email=t@t -c user.name=t commit -qm base
mkdir -p "$R/.claude/work/T-1" "$R/.claude/work/issue-7"
cat > "$R/.claude/work/T-1/plan.md" <<'EOF'
# Feature: T-1 demo

## Summary
**Branch / worktree**: `feature/v9-T-1-demo` @ /Users/someone/work/repo
Scratch in /scratch/someone/run1 and /p/lustre1/someone/x, see file:///Users/someone/r.html

## Tasks
```
## not a heading inside a fence
```
EOF
printf '# RCA: issue 7\n\nRoot cause: x.\n' > "$R/.claude/work/issue-7/rca.md"
meta(){ python3 - "$W/meta.json" "$1" <<'EOF'
import json,sys
d=dict(key="T-1",key_url="https://x/browse/T-1",summary="Demo",epic="T-0",epic_url="https://x/browse/T-0",
 prd_title="PRD: T-0 - Demo",prd_url="https://x/wiki/1",branch="feature/v9-T-1-demo",status="Planning",
 updated="2026-10-15",skill="test")
if sys.argv[2]: d.update(page_id=sys.argv[2], page_url="https://x/wiki/"+sys.argv[2])
json.dump(d,open(sys.argv[1],'w'))
EOF
}
fakelog(){ python3 - "$W/hook.jsonl" "$1" "$2" "$3" <<'EOF'
import json,sys
log,pid,bodyf,ver=sys.argv[1:]
rec={"hook_event_name":"PostToolUse","tool_name":"mcp__atlassian__updateConfluencePage",
     "tool_input":{"pageId":pid,"body":open(bodyf).read()},
     "tool_response":[{"type":"text","text":json.dumps({"id":pid,"version":{"number":int(ver)}})}]}
open(log,"a").write(json.dumps(rec)+"\n")
EOF
}
P=.claude/work/T-1/plan.md
PH=$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1]).read().rstrip().encode()).hexdigest()[:16])" "$R/$P")
echo "== A. new page"
meta ""; $T render --repo "$R" --plan $P --meta "$W/meta.json" --outbox "$ST" --out "$W/dry0.md" >/dev/null; ok $? 0 "A0 render before the page exists (dry-run shape)"
[ ! -e "$ST" ]; ok $? 0 "A0 render wrote nothing to the store"
$T stub --key T-1 > "$W/stub.md"; ok "$(cat "$W/stub.md")" "Plan page for T-1; content follows." "A1 stub text"
python3 -c "import json;b=open('$W/stub.md').read();json.dump([{'type':'text','text':json.dumps({'id':'900','body':b})}],open('$W/stub.json','w'))"
meta 900
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stub.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "A2 stub without --new-page refused"
echo "something else" > "$W/notstub.md"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/notstub.md" --new-page --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "A3 --new-page with a non-stub page refused"
[ -z "$(git -C "$R" status --porcelain --untracked-files=all)" ]; ok $? 0 "A4 the plan and RCA are untracked working copies: git status is clean"
$T state --repo "$R" --key T-1 --outbox "$ST" --set page_id=900 >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$ST" --add Progress plan-feature "Plan published (sha256 $PH)." >/dev/null
$T render --repo "$R" --plan $P --date 2026-10-16 --meta "$W/meta.json" --current "$W/stub.json" --new-page --outbox "$ST" --out "$W/b1.md" >/dev/null; ok $? 0 "A4 first fill with --new-page (wrapped stub), from the untracked plan"
grep -q "published 2026-10-16 (sha256 \`$PH\`)" "$W/b1.md"; ok $? 0 "A4 header cites the publish date and the plan's sha256"
grep -qE 'as of `|in the repo is the source of truth' "$W/b1.md"; ok $? 1 "A4 no commit cited, no repo file claimed"
grep -qE '/Users/someone|/scratch/someone|/p/lustre1|file:///Users' "$W/b1.md"; ok $? 1 "A4 no local or cluster paths, file:// URL masked"
grep -q '^#### not a heading inside a fence' "$W/b1.md"; ok $? 1 "A4 fenced '##' line not demoted"
fakelog 900 "$W/b1.md" 2
$T verify --body "$W/b1.md" --page-id 900 --after-version 1 --log "$W/hook.jsonl" >/dev/null; ok $? 0 "A5 verify the first update (v2)"
$T state --repo "$R" --key T-1 --outbox "$ST" --set version=2 page_id=900 --save-body "$W/b1.md" --save-plan "$R/$P" --date 2026-10-16 >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$ST" --mark-sent >/dev/null
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stub.md" --new-page --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "A6 --new-page refused once a version is written"
echo "== B. later flushes"
$T queue --repo "$R" --key T-1 --outbox "$ST" --add Reviews loop $'Reviewer: plan round 1 APPROVE (0/0/1).\n# ran: pytest -k D_only\n```\nRESULT: AGREE\n```' >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "B1 --local without --page-version refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --page-version 3 --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "B2 --local with a moved version refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --page-version 2 --outbox "$ST" --out "$W/b2.md" >/dev/null; ok $? 0 "B3 --local with the matching version"
grep -c 'Plan published' "$W/b2.md" | grep -qx 1; ok $? 0 "B3 earlier entry kept once"
grep -q '^  \\# ran: pytest' "$W/b2.md"; ok $? 0 "B3 '#' line of an entry escaped"
fakelog 900 "$W/b2.md" 3
$T verify --body "$W/b2.md" --page-id 900 --after-version 2 --log "$W/hook.jsonl" >/dev/null; ok $? 0 "B4 verify v3"
$T state --repo "$R" --key T-1 --outbox "$ST" --set version=3 --save-body "$W/b2.md" >/dev/null; $T queue --repo "$R" --key T-1 --outbox "$ST" --mark-sent >/dev/null
# Confluence round trip: drop continuation indents, '\#' -> '#', '_x_' -> '*x*', bullets '-' -> '*' for log entries
python3 - "$W/b2.md" "$W/rt.md" <<'EOF'
import re,sys
s=open(sys.argv[1]).read(); s=s[:s.index("\n## Plan\n")]
s=re.sub(r"^  ", "", s, flags=re.M).replace("\\#","#").replace("_No entries yet._","*No entries yet.*")
s=re.sub(r"^- \*\*", "* **", s, flags=re.M)
open(sys.argv[2],"w").write(s)
EOF
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/rt.md" --outbox "$ST" --out "$W/b3.md" > "$W/out.txt"; ok $? 0 "B5 --current after a round trip"
grep -q '0 new, 0 restored' "$W/out.txt"; ok $? 0 "B5 no duplicates, nothing lost"
grep -q 'ran: pytest -k D_only' "$W/b3.md"; ok $? 0 "B5 the '#' line survives the round trip"
python3 -c "s=open('$W/rt.md').read(); open('$W/trunc.md','w').write(s[:s.index('## Reviews')])"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/trunc.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "B6 truncated --current refused"
python3 -c "
s=open('$W/rt.md').read(); i=s.index('* **2026'); j=s.index('\n', i); open('$W/lost.md','w').write(s[:i]+s[j+1:])"
$T queue --repo "$R" --key T-1 --outbox "$W/store-other" --add Progress x y >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/lost.md" --outbox "$ST" --out "$W/b4.md" | grep -q '1 restored'; ok $? 0 "B7 an own entry the page lost is restored from the sent log"
python3 -c "
s=open('$W/rt.md').read(); s=s.replace('## Validation','## Validation\n\n* **2026-10-14** · other-wt · from another worktree\n'); open('$W/other.md','w').write(s)"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/other.md" --outbox "$ST" --out "$W/b5.md" >/dev/null; ok $? 0 "B8 page with another worktree's entry"
python3 - "$W/b5.md" "$W/b5cut.md" <<'EOF'
import sys
s=open(sys.argv[1]).read(); s=s[:s.index("\n## Plan\n")]; i=s.index("from another worktree"); i=s.rindex("\n",0,i); j=s.index("\n",i+1)
open(sys.argv[2],"w").write(s[:i]+s[j:])
EOF
$T state --repo "$R" --key T-1 --outbox "$ST" --save-body "$W/b5.md" >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b5cut.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "B9 a page with fewer entries than last sent refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b5cut.md" --allow-fewer --outbox "$ST" --out "$W/x.md" >/dev/null; ok $? 0 "B9 accepted with --allow-fewer"
echo "== C. verify after a failed update / retry"
$T verify --body "$W/b5.md" --page-id 900 --after-version 3 --log "$W/hook.jsonl" 2>/dev/null; ok $? 3 "C1 failed update (not logged): verify says not logged, no mismatch"
cp "$W/b5.md" "$W/b5bad.md"; echo "typo" >> "$W/b5bad.md"; fakelog 900 "$W/b5bad.md" 4
$T verify --body "$W/b5.md" --page-id 900 --after-version 3 --log "$W/hook.jsonl" 2>/dev/null; ok $? 1 "C2 transcription error detected"
fakelog 900 "$W/b5.md" 5
$T verify --body "$W/b5.md" --page-id 900 --after-version 4 --log "$W/hook.jsonl" >/dev/null; ok $? 0 "C3 one retry verified (v5 = checked 3 + 2 own updates)"
echo "== D. other refusals and dry run"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "D1 existing page without --current/--local refused"
python3 -c "import json;json.dump({'body':{'storage':{'value':'<p/>'}}},open('$W/stor.json','w'))"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/stor.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "D2 storage form refused"
python3 -c "import json;d=json.load(open('$W/meta.json'));d.pop('branch');json.dump(d,open('$W/m2.json','w'))"
$T render --repo "$R" --mirrored --meta "$W/m2.json" --local --page-version 3 --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "D3 missing meta key exits 2"
before=$(ls -l "$ST" | md5sum 2>/dev/null || ls -l "$ST" | md5)
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/rt.md" --entry Progress test "dry entry" --outbox "$ST" --allow-fewer --out "$W/dry.md" >/dev/null; ok $? 0 "D4 dry-run render with --entry"
after=$(ls -l "$ST" | md5sum 2>/dev/null || ls -l "$ST" | md5); ok "$before" "$after" "D4 dry run left the store unchanged"
echo "== E. RCA mirror"
$T render --repo "$R" --plan .claude/work/issue-7/rca.md --plan-title RCA --meta "$W/meta.json" --current "$W/rt.md" --allow-fewer --outbox "$W/st-rca" --out "$W/rca.md" >/dev/null; ok $? 0 "E1 RCA render"
grep -q '^## RCA$' "$W/rca.md" && grep -q 'The RCA is a working document kept outside the repo' "$W/rca.md"; ok $? 0 "E1 RCA heading and header"
echo "== F. Jira fallback text"
printf 'x%.0s' $(seq 1 1600) | $T sanitize --repo "$R" >/dev/null 2>&1; ok $? 1 "F1 1500-char cap"
printf '**PIV record: Reviews** (2026-10-15, loop) · _posted by an agent_\nreport /gpfs/u/someone/r.md, /global/homes/s/someone/x, /g/g19/someone/y, /usr/workspace/someone/z\n' | $T sanitize --repo "$R" > "$W/fb.txt"; ok $? 0 "F2 fallback comment sanitised"
grep -qE 'someone' "$W/fb.txt"; ok $? 1 "F2 cluster paths masked"
printf 'see https://user:hunter22@host/x\n' | $T sanitize --repo "$R" >/dev/null 2>&1; ok $? 1 "F3 credentials refused"
$T state --repo "$R" --key T-1 --outbox "$W/st-fb" --set fallback_count=8 fallback_summary_id=10050 >/dev/null; ok $? 0 "F4 fallback state"
echo "== G. stub retry, recreated page, reset (review I3-m1)"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stub.md" --outbox "$ST" --out "$W/x.md" 2>"$W/err.txt"; ok $? 2 "G1 stub as --current without --new-page refused"
grep -q -- '--new-page' "$W/err.txt"; ok $? 0 "G1 the refusal points to --new-page"
meta 901
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stub.md" --new-page --outbox "$ST" --out "$W/g2.md" >/dev/null 2>"$W/err.txt"; ok $? 0 "G2 recreated page (new id) fills with --new-page"
grep -q 'belongs to page 900' "$W/err.txt"; ok $? 0 "G2 note that the recorded version belongs to the old page"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --page-version 3 --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "G3 --local refused for the new page id"
meta 900
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stub.md" --new-page --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "G4 --new-page refused on the same page while a version is recorded"
$T state --repo "$R" --key T-1 --outbox "$ST" --set version= >/dev/null
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stub.md" --new-page --outbox "$ST" --out "$W/x.md" >/dev/null; ok $? 0 "G5 after the documented reset (state --set version=) --new-page works"
echo "== H. running-summary cap (review I3-m2)"
S2="$W/st-sum"; SUM="$T summary --repo $R --key T-1 --outbox $S2"
$SUM --check >/dev/null; ok $? 0 "H1 check before the first summary"
$SUM --returned-id 100 >/dev/null; ok $? 0 "H2 first summary recorded"
$SUM --returned-id 100 >/dev/null; ok $? 0 "H3 updated in place"
$SUM --returned-id 101 >/dev/null; ok $? 0 "H4 an update that created a comment is adopted (no extra post)"
$SUM --check | grep -q 'update comment 101'; ok $? 0 "H4 the adopted comment is the summary now"
$SUM --returned-id 102 >/dev/null; ok $? 1 "H5 a second created comment stops the summary"
$SUM --check >/dev/null; ok $? 1 "H6 no further Jira calls once stopped"
S3="$W/st-sum2"; SUM2="$T summary --repo $R --key T-1 --outbox $S3"
$SUM2 --returned-id 200 >/dev/null; $SUM2 --failed | grep -q 'Supersedes comment 200'; ok $? 0 "H7 first failure: post one superseding comment"
$SUM2 --superseded-by 201 >/dev/null; ok $? 0 "H7 superseding comment recorded"
$SUM2 --failed >/dev/null; ok $? 1 "H8 second failure stops"
$SUM2 --check >/dev/null; ok $? 1 "H8 stopped: no further calls"
echo "== I. short roots only as path prefixes (review I3-m3)"
printf 'the /p option, /g flag, /global setting, /data-set, /project-x, /p.value, /work and /nfs\n' > "$W/words.txt"
$T sanitize --repo "$R" --max-chars 0 < "$W/words.txt" > "$W/words.out"; cmp -s "$W/words.txt" "$W/words.out"; ok $? 0 "I1 lone short roots left alone"
printf '/p/lustre1/someone/a /g/g19/someone/b /global/homes/s/someone/c /data/someone/d /work/someone/e /usr/WS1/someone/f\n' | $T sanitize --repo "$R" --max-chars 0 | grep -q someone; ok $? 1 "I2 short roots with a path segment masked"
echo "== J. page created by spec, then the whole lifecycle on it"
PL="$W/main"; git init -q "$PL"   # the checkout spec runs in; the breakdown is a local file (the page as read)
cat > "$W/T-0-demo.md" <<'EOF'
# Spec: T-0 - Demo

## Tickets
### Phase 1

#### T1 — Coordinate with T-9 · `T-2`
- **Scope:** talk to T-9.
- **Branch:** none.

#### T2 — Demo feature · `T-1`
- **Scope:** add the demo, see /Users/someone/x.
- **Acceptance:**
  - it works;
  - it is documented.
## Not a ticket
- **Depends on:** none.

#### T3 — Other · `T-10`
- **Branch:** `feature/v9-T-10-other`.
EOF
BSRC='the epic breakdown page `Spec: T-0 - Demo - Ticket Breakdown` (Confluence page 700, version 3)'
TK(){ $T ticket --repo "$PL" --breakdown "$W/T-0-demo.md" --source "$BSRC" "$@"; }
TK --key T-1 --out "$W/tk1.md" >/dev/null; ok $? 0 "J1 Ticket section from the breakdown entry (by key)"
grep -q 'it is documented' "$W/tk1.md" && ! grep -q 'Not a ticket' "$W/tk1.md" && ! grep -q 'Other' "$W/tk1.md"; ok $? 0 "J1 the entry ends at the next heading of its level or higher"
grep -q 'Confluence page 700, version 3' "$W/tk1.md" && ! grep -q '/Users/someone' "$W/tk1.md"; ok $? 0 "J1 source line cites the breakdown page and version; paths masked"
TK --key T-9 --out "$W/x.md" 2>/dev/null; ok $? 3 "J2 a key that only appears in another entry's title text is not matched (T-9)"
TK --key T-3 --out "$W/x.md" 2>/dev/null; ok $? 3 "J2 no entry: exit 3 (use the Jira description)"
printf 'Fix the thing.\n\n## Acceptance\n- done\n' > "$W/desc.md"
$T ticket --repo "$PL" --key T-3 --text "$W/desc.md" --source "the Jira description of T-3" --out "$W/tk3.md" >/dev/null; ok $? 0 "J2 Ticket section from a Jira description"
grep -q '^### Acceptance' "$W/tk3.md"; ok $? 0 "J2 headings in the text demoted below H2"
SM(){ python3 - "$W/smeta.json" "$1" <<'EOF'
import json,sys
d=dict(key="T-1",key_url="https://x/browse/T-1",summary="Demo",epic="T-0",epic_url="https://x/browse/T-0",
 prd_title="PRD: T-0 - Demo",prd_url="https://x/wiki/1",branch="feature/v9-T-1-demo",status="Planned",
 updated="2026-10-16",skill="spec",branch_state="absent")
if sys.argv[2]: d.update(page_id=sys.argv[2], page_url="https://x/wiki/"+sys.argv[2])
json.dump(d,open(sys.argv[1],'w'))
EOF
}
SM ""; SS="$W/st-spec"
$T render --repo "$PL" --meta "$W/smeta.json" --outbox "$SS" --out "$W/x.md" 2>/dev/null; ok $? 2 "J3 skeleton without --ticket refused"
$T render --repo "$PL" --meta "$W/smeta.json" --ticket "$W/tk1.md" --outbox "$SS" --out "$W/sk.md" >/dev/null; ok $? 0 "J3 skeleton render (spec, before the create)"
for h in '## Ticket' '## Progress' '## Validation' '## Reviews' '## Findings and decisions' '## Plan'; do grep -qx "$h" "$W/sk.md" || echo "missing $h"; done | grep -q missing; ok $? 1 "J3 skeleton has Ticket, the four logs and Plan"
grep -q 'Not written yet' "$W/sk.md" && grep -q 'Status:\*\* Planned' "$W/sk.md" && grep -q 'checked: not created yet' "$W/sk.md" && ! grep -q 'Backfilled' "$W/sk.md"; ok $? 0 "J3 Plan placeholder, status Planned, branch checked absent, not backfilled"
[ ! -e "$SS" ]; ok $? 0 "J3 the skeleton render wrote nothing to the store"
SM 950
$T render --repo "$PL" --meta "$W/smeta.json" --ticket "$W/tk1.md" --current "$W/sk.md" --outbox "$SS" --out "$W/x.md" 2>/dev/null; ok $? 2 "J4 the skeleton never rewrites an existing page"
fakecreate(){ python3 - "$W/hook.jsonl" "$1" "$2" "$3" <<'EOF'
import json,sys
log,title,bodyf,pid=sys.argv[1:]
rec={"hook_event_name":"PostToolUse","tool_name":"mcp__atlassian__createConfluencePage",
     "tool_input":{"parentId":"800","title":title,"body":open(bodyf).read()},
     "tool_response":[{"type":"text","text":json.dumps({"id":pid,"version":{"number":1},"body":{"storage":{"value":"<p/>"}}})}]}
open(log,"a").write(json.dumps(rec)+"\n")
EOF
}
fakecreate "Plan: T-1 - Demo" "$W/sk.md" 950
$T verify --body "$W/sk.md" --created --title "Plan: T-1 - Demo" --parent-id 800 --log "$W/hook.jsonl" | grep -q 'page id 950'; ok $? 0 "J5 verify the create (body and new page id)"
cp "$W/sk.md" "$W/skbad.md"; echo typo >> "$W/skbad.md"; fakecreate "Plan: T-1 - Demo" "$W/skbad.md" 951
$T verify --body "$W/sk.md" --created --title "Plan: T-1 - Demo" --log "$W/hook.jsonl" 2>/dev/null; ok $? 1 "J5 a mistyped create is detected"
$T verify --body "$W/sk.md" --created --title "Plan: T-2 - Other" --log "$W/hook.jsonl" 2>/dev/null; ok $? 3 "J5 no logged create with that title: unverified"
# The page as Confluence returns it (markdown round trip), and the lookups plan-feature makes.
python3 - "$W/sk.md" "$W/spage.json" <<'EOF'
import json,re,sys
s=open(sys.argv[1]).read(); s=re.sub(r"^  ", "", s, flags=re.M).replace("_No entries yet._","*No entries yet.*")
s=re.sub(r"^- ", "* ", s, flags=re.M)
json.dump([{"type":"text","text":json.dumps({"id":"950","title":"Plan: T-1 - Demo","body":s})}],open(sys.argv[2],"w"))
EOF
cat > "$W/cql.json" <<'EOF'
{"results":[{"content":{"id":"950","title":"Plan: T-1 - Demo"}},{"content":{"id":"960","title":"Plan: T-10 - Other"}},
 {"content":{"id":"970","title":"Plan: T-1x - near miss"}}],"size":3}
EOF
cat > "$W/issue.json" <<'EOF'
{"key":"T-1","fields":{"comment":{"comments":[{"id":"1","body":"Ticket page: [Plan: T-1 - Demo](https://x/wiki/950) (Confluence page id `950`), under [Ticket plans: T-0](https://x/wiki/800)."}]}}}
EOF
$T find --key T-1 --search "$W/cql.json" > "$W/f1.json"; ok $? 0 "J6 lookup by CQL title finds the spec-created page"
grep -q '"950"' "$W/f1.json" && ! grep -q '"960"\|"970"' "$W/f1.json"; ok $? 0 "J6 only page 950 (not T-10, not T-1x)"
$T find --key T-1 --comments "$W/issue.json" | grep -q 'Jira link comment'; ok $? 0 "J6 lookup by the Jira link comment (no worktree record yet)"
echo '{"key":"T-2","fields":{"comment":{"comments":[],"total":0}}}' > "$W/issue-none.json"
$T find --key T-2 --search "$W/cql.json" --comments "$W/issue-none.json" >/dev/null 2>&1; ok $? 3 "J6 no page (complete listing and comments): exit 3, create it"
sed 's/"970","title":"Plan: T-1x - near miss"/"971","title":"Plan: T-1 - Demo (copy)"/' "$W/cql.json" > "$W/cql2.json"
$T find --key T-1 --search "$W/cql2.json" >/dev/null 2>&1; ok $? 2 "J6 two pages for one ticket: stop and ask"
# plan-feature in the ticket worktree: fresh store, the page read back, the plan's Ticket page line committed.
TS="$W/st-ticket"; meta 950
$T state --repo "$R" --key T-1 --outbox "$TS" --set page_id=950 >/dev/null
$T find --key T-1 --state-id 950 --comments "$W/issue.json" --search "$W/cql.json" >/dev/null; ok $? 0 "J7 state file, comment and CQL agree"
$T queue --repo "$R" --key T-1 --outbox "$TS" --add Progress plan-feature "Plan published (sha256 $PH)." >/dev/null
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/spage.json" --outbox "$TS" --out "$W/p1.md" > "$W/out.txt"; ok $? 0 "J7 plan-feature fills the spec-created page with --current (no --new-page)"
grep -q 'Ticket section carried over' "$W/out.txt" && grep -q 'it is documented' "$W/p1.md"; ok $? 0 "J7 Ticket section kept"
grep -q 'Not written yet' "$W/p1.md"; ok $? 1 "J7 the Plan placeholder is replaced by the mirror"
grep -q '^#### Tasks' "$W/p1.md" && grep -q 'Plan published' "$W/p1.md"; ok $? 0 "J7 plan mirrored, Progress entry added"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/spage.json" --new-page --outbox "$TS" --out "$W/x.md" 2>/dev/null; ok $? 2 "J7 --new-page refused on a spec-created page (not a stub)"
fakelog 950 "$W/p1.md" 2
$T verify --body "$W/p1.md" --page-id 950 --after-version 1 --log "$W/hook.jsonl" >/dev/null; ok $? 0 "J8 verify the plan publish (v2)"
$T state --repo "$R" --key T-1 --outbox "$TS" --set version=2 page_id=950 --save-body "$W/p1.md" --save-plan "$R/$P" >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$TS" --mark-sent >/dev/null
# execute (with validate queued inside it): --local flush
$T queue --repo "$R" --key T-1 --outbox "$TS" --add Validation validate "build ok, smoke test ok at abc1234" >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$TS" --add Progress execute "execute: tasks 1-3 done, commits a..b; no deviations" >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --page-version 2 --outbox "$TS" --out "$W/p2.md" >/dev/null; ok $? 0 "J9 end-of-execute flush (--local)"
grep -q 'it is documented' "$W/p2.md" && grep -q 'tasks 1-3 done' "$W/p2.md" && grep -q 'smoke test ok at abc1234' "$W/p2.md"; ok $? 0 "J9 Ticket section, Progress and Validation present"
fakelog 950 "$W/p2.md" 3; $T verify --body "$W/p2.md" --page-id 950 --after-version 2 --log "$W/hook.jsonl" >/dev/null; ok $? 0 "J9 verify v3"
$T state --repo "$R" --key T-1 --outbox "$TS" --set version=3 --save-body "$W/p2.md" >/dev/null; $T queue --repo "$R" --key T-1 --outbox "$TS" --mark-sent >/dev/null
# a standalone validate flush after someone else edited the page: --current round trip
python3 - "$W/p2.md" "$W/p2rt.md" <<'EOF'
import re,sys
s=open(sys.argv[1]).read(); s=re.sub(r"^  ", "", s, flags=re.M); s=re.sub(r"^- ", "* ", s, flags=re.M)
open(sys.argv[2],"w").write(s)
EOF
$T queue --repo "$R" --key T-1 --outbox "$TS" --add Validation validate "FAIL D_only: fnrm 1.2e-3 vs 1.1e-3" >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/p2rt.md" --outbox "$TS" --out "$W/p3.md" > "$W/out.txt"; ok $? 0 "J10 standalone validate flush (--current after a round trip)"
grep -q '1 new, 0 restored' "$W/out.txt" && grep -q 'it is documented' "$W/p3.md"; ok $? 0 "J10 one new entry, nothing duplicated, Ticket kept"
fakelog 950 "$W/p3.md" 4; $T state --repo "$R" --key T-1 --outbox "$TS" --set version=4 --save-body "$W/p3.md" >/dev/null; $T queue --repo "$R" --key T-1 --outbox "$TS" --mark-sent >/dev/null
# review flush; then the Ticket-section safety check
$T queue --repo "$R" --key T-1 --outbox "$TS" --add Reviews loop "Reviewer: implementation round 1 APPROVE (0/0/2)." >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --page-version 4 --outbox "$TS" --out "$W/p4.md" >/dev/null; ok $? 0 "J11 review flush (--local)"
python3 - "$W/p4.md" <<'EOF'
import sys
s=open(sys.argv[1]).read(); c=s.count
assert c("## Ticket\n")==1 and c("## Plan\n")==1 and c("Plan published")==1 and c("tasks 1-3 done")==1 and c("fnrm 1.2e-3")==1 and c("APPROVE (0/0/2)")==1, "counts"
assert s.index("## Ticket")<s.index("## Progress")<s.index("## Validation")<s.index("## Reviews")<s.index("## Findings and decisions")<s.index("## Plan")
EOF
ok $? 0 "J11 one page: every section once, in order, every entry once"
$T state --repo "$R" --key T-1 --outbox "$TS" --save-body "$W/p4.md" >/dev/null
python3 - "$W/p4.md" "$W/noticket.md" <<'EOF'
import sys
s=open(sys.argv[1]).read(); i=s.index("## Ticket"); j=s.index("## Progress"); s=s[:i]+s[j:]; s=s[:s.index("\n## Plan\n")]
open(sys.argv[2],"w").write(s)
EOF
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/noticket.md" --outbox "$TS" --out "$W/x.md" 2>/dev/null; ok $? 2 "J12 a page that lost its Ticket section is refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/noticket.md" --ticket "$W/tk1.md" --outbox "$TS" --out "$W/x.md" >/dev/null; ok $? 0 "J12 accepted with --ticket (rebuilt section)"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/noticket.md" --allow-fewer --outbox "$TS" --out "$W/x.md" >/dev/null; ok $? 0 "J12 accepted with --allow-fewer (deliberate removal)"
# legacy page (created by plan-feature before spec made pages): no Ticket section, nothing refused
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/rt.md" --allow-fewer --outbox "$W/st-legacy" --out "$W/lg.md" >/dev/null; ok $? 0 "J13 legacy page without a Ticket section renders"
grep -q '^## Ticket' "$W/lg.md"; ok $? 1 "J13 no Ticket section invented"
# a legacy stub found by spec: filled with the skeleton via --new-page
SM 990; $T render --repo "$PL" --meta "$W/smeta.json" --ticket "$W/tk1.md" --current "$W/stub.md" --new-page --outbox "$W/st-stub" --out "$W/x.md" >/dev/null; ok $? 0 "J14 the helper accepts the skeleton on a legacy stub with --new-page (no skill relies on it)"
# Jira fallback: the 'ticket filed' comment
printf '**PIV record: ticket filed** (2026-10-16, spec) · _posted by an agent through the owner account_\nScope: add the demo, see /Users/someone/x.\nAcceptance: it works; it is documented.\nBranch `feature/v9-T-1-demo` (planned); breakdown page `Spec: T-0 - Demo - Ticket Breakdown` (700, v3).\nNo epic PRD page, so the record is kept in these comments (at most 8).\n' | $T sanitize --repo "$PL" > "$W/fb2.txt"; ok $? 0 "J15 fallback 'ticket filed' comment within the cap"
grep -q '/Users/someone' "$W/fb2.txt"; ok $? 1 "J15 paths masked"
echo "== K. find on real responses, evidence rules, stale records, Branch tier, backfill (review round 1)"
FX="$(cd "$(dirname "$H")" && pwd)/fixtures"   # real read-only responses, author/session fields removed
REALCQL="$FX/AIUE-8-container-children-cql.json"
$T find --key AIUE-61 --comments "$FX/AIUE-61-issue-markdown.json" --search "$REALCQL" > "$W/k1.json"; ok $? 0 "K1 real markdown issue + real listing: AIUE-61 found"
grep -q '"page_id": "2293761"' "$W/k1.json" && grep -q 'Jira link comment' "$W/k1.json"; ok $? 0 "K1 the legacy 'Plan page:' link comment is read (page 2293761)"
grep -q '"piv_record_comments": 0' "$W/k1.json"; ok $? 0 "K1 PIV record comments counted (0)"
$T find --key AIUE-61 --comments "$FX/AIUE-61-issue-markdown-nodes-shape.json" --search "$REALCQL" | grep -q '"piv_record_comments": 0'; ok $? 0 "K2 the issues.nodes response shape is read (an older read, before the link comment: found by the listing)"
$T find --key AIUE-61 --comments "$FX/AIUE-61-issue-adf.json" --search "$REALCQL" | grep -q 'Jira link comment'; ok $? 0 "K3 real ADF comment bodies are flattened (link comment found)"
echo '{"fields":{"comment":{"comments":[],"total":0}}}' > "$W/k-none.json"
$T find --key AIUE-8 --search "$FX/PRD-AIUE-8-cql-nodes-shape.json" --comments "$W/k-none.json" >/dev/null 2>&1; ok $? 3 "K4 the content.nodes CQL shape is read (complete, no Plan page: none)"
$T find --key AIUE-46 --comments "$W/k-none.json" --search "$REALCQL" >/dev/null 2>&1; ok $? 3 "K4 a child with no page in the real listing: none"
$T find --key T-1 >/dev/null 2>&1; ok $? 2 "K5 no inputs: can't tell (2), never 'create'"
$T find --key T-1 --comments "$W/k-none.json" >/dev/null 2>&1; ok $? 2 "K5 comments without a listing: can't tell"
$T find --key T-2 --search "$W/cql.json" >/dev/null 2>&1; ok $? 2 "K5 a listing without the comments: can't tell"
echo '{"fields":{"comment":{"comments":[{"id":"1","body":42}]}}}' > "$W/k-bad.json"
$T find --key T-2 --search "$W/cql.json" --comments "$W/k-bad.json" >/dev/null 2>&1; ok $? 2 "K5 a comment body in an unknown form: can't tell"
echo '{"fields":{"comment":{"comments":[{"id":"1","body":"x"}],"total":5,"maxResults":1}}}' > "$W/k-paged.json"
$T find --key T-2 --search "$W/cql.json" --comments "$W/k-paged.json" >/dev/null 2>&1; ok $? 2 "K5 a paged comment list (1 of 5): can't tell"
echo '{"results":[{"content":{"id":"950","title":"Plan: T-1 - Demo"}}],"size":1,"totalSize":3}' > "$W/k-part.json"
$T find --key T-2 --search "$W/k-part.json" --comments "$W/k-none.json" >/dev/null 2>&1; ok $? 2 "K5 an incomplete listing (1 of 3): can't tell"
echo '{"fields":{"comment":{"comments":[{"id":"1","body":"**PIV record: ticket filed** (2026-10-16, spec)"}]}}}' > "$W/k-piv.json"
$T find --key T-1 --fallback --comments "$W/k-piv.json" | grep -q '"piv_record_comments": 1'; ok $? 0 "K6 fallback: a markdown PIV record comment counted"
$T find --key T-1 --fallback --comments "$W/k-piv.json" >/dev/null 2>&1; ok $? 0 "K6 fallback: record exists, post nothing (exit 0)"
python3 - "$W/k-piv-adf.json" <<'EOF'
import json,sys
b={"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"PIV record: ticket filed","marks":[{"type":"strong"}]},{"type":"text","text":" (2026-10-16, spec)"}]}]}
json.dump({"fields":{"comment":{"comments":[{"id":"1","body":b}],"total":1}}},open(sys.argv[1],"w"))
EOF
$T find --key T-1 --fallback --comments "$W/k-piv-adf.json" | grep -q '"piv_record_comments": 1'; ok $? 0 "K6 fallback: an ADF PIV record comment counted"
$T find --key T-1 --fallback --comments "$W/k-none.json" >/dev/null 2>&1; ok $? 3 "K6 fallback: no PIV record comment: post it (3)"
$T find --key T-1 --fallback >/dev/null 2>&1; ok $? 2 "K6 fallback without comments: can't tell"
python3 -c "
import json;json.dump({'fields':{'comment':{'comments':[{'id':str(i),'body':'**PIV record: m%d** x'%i} for i in range(8)],'total':8}}},open('$W/k-cap.json','w'))"
$T find --key T-1 --fallback --comments "$W/k-cap.json" | grep -q '"piv_cap_reached": true'; ok $? 0 "K6 8 PIV record comments: cap reached reported"
cat > "$W/k-two.json" <<'EOF'
{"fields":{"comment":{"comments":[{"id":"1","body":"Ticket page: [Plan: T-1 - Demo](https://x/100) (Confluence page id `100`)."},{"id":"2","body":"Ticket page: [Plan: T-1 - Demo](https://x/200) (Confluence page id `200`)."}]}}}
EOF
echo '{"results":[{"content":{"id":"200","title":"Plan: T-1 - Demo"}}],"totalSize":1}' > "$W/k-200.json"
$T find --key T-1 --comments "$W/k-two.json" --search "$W/k-200.json" > "$W/k7.json" 2>/dev/null; ok $? 0 "K7 recreated page: the listed id wins (no endless stop)"
grep -q '"page_id": "200"' "$W/k7.json" && grep -q '"100"' "$W/k7.json" && grep -q stale_records "$W/k7.json"; ok $? 0 "K7 the stale link comment (100) is reported"
echo '{"fields":{"comment":{"comments":[{"id":"1","body":"Ticket page: [x](https://x/100) (Confluence page id `100`)."}]}}}' > "$W/k-100.json"
echo '{"results":[],"totalSize":0}' > "$W/k-empty.json"
$T find --key T-1 --comments "$W/k-100.json" --search "$W/k-empty.json" | grep -q '"not_listed": true'; ok $? 0 "K7 recorded but not under this container (moved ticket): found, flagged to confirm"
$T find --key T-1 --comments "$W/k-100.json" --search "$W/k-empty.json" --gone 100 >/dev/null 2>&1; ok $? 3 "K7 after CQL confirms it gone (--gone): none"
cat > "$W/T-5-branch.md" <<'EOF'
# Spec: T-5

### Phase 1

#### T1 — First thing
- Scope: a.
- Branch: `feature/v9-T-46-first` · base `v9-develop`

#### T2 — Process change
- **Branch:** `feature/v9-ai-T-47-skills`

#### T3 — Twin
- **Branch**: `feature/v9-T-48-x`

#### T4 — Twin again
- **Branch**: `feature/v9-T-48-y`
EOF
TB(){ $T ticket --repo "$PL" --breakdown "$W/T-5-branch.md" --source "the breakdown page (Confluence page 701, version 1)" "$@"; }
TB --key T-46 --out "$W/kb.md" >/dev/null 2>&1; ok $? 0 "K8 plain '- Branch:' line under a phase heading: one entry, not 'several'"
grep -q 'First thing' "$W/kb.md" && ! grep -q 'Process change' "$W/kb.md"; ok $? 0 "K8 the entry is T1 alone"
TB --key T-47 --out "$W/kb.md" >/dev/null 2>&1 && grep -q 'Process change' "$W/kb.md"; ok $? 0 "K8 a feature/v9-ai-<KEY> branch matches"
TB --key T-4 --out "$W/kb.md" >/dev/null 2>&1; ok $? 3 "K8 T-4 does not match T-46/T-47/T-48"
TB --key T-48 --out "$W/kb.md" >/dev/null 2>&1; ok $? 2 "K8 two entries with the key: several (2)"
$T verify --body "$W/sk.md" --created --title "Plan: T-1 - Demo" --parent-id 999 --log "$W/hook.jsonl" >/dev/null 2>&1; ok $? 3 "K9 verify --created with another --parent-id: no match"
# backfill: a page created after the ticket was filed, ticket In Progress, branch exists
TK --key T-1 --backfill --date 2026-10-16 --out "$W/kbt.md" >/dev/null
python3 - "$W/kbm.json" <<'EOF'
import json,sys
json.dump(dict(key="T-1",key_url="https://x/browse/T-1",summary="Demo",epic="T-0",epic_url="https://x/browse/T-0",
 prd_title="PRD: T-0 - Demo",prd_url="https://x/wiki/1",branch="feature/v9-T-1-demo",status="Backfilled",
 updated="2026-10-16",skill="spec --pages-only",backfilled="2026-10-16",branch_state="exists",jira_status="In Progress"),
 open(sys.argv[1],"w"))
EOF
$T render --repo "$PL" --meta "$W/kbm.json" --ticket "$W/kbt.md" --outbox "$W/st-bf" --out "$W/kbf.md" >/dev/null; ok $? 0 "K10 backfill skeleton render"
grep -q '^> \*\*Backfilled:\*\* 2026-10-16' "$W/kbf.md" && grep -q 'Jira status then: In Progress' "$W/kbf.md" && grep -q 'Not mirrored here yet' "$W/kbf.md" && grep -q 'Scope as read on 2026-10-16' "$W/kbf.md"; ok $? 0 "K10 Backfilled field, Jira status, 'not mirrored' placeholder, 'as read on'"
grep -qiE 'not created yet|created when the ticket was filed|Scope as filed|not written yet|\(planned' "$W/kbf.md"; ok $? 1 "K10 no false claim (planned / not created / as filed / not written)"
python3 -c "import json;d=json.load(open('$W/kbm.json'));d.pop('branch_state');d.pop('backfilled');d['status']='Planned';json.dump(d,open('$W/kbm2.json','w'))"
$T render --repo "$PL" --meta "$W/kbm2.json" --ticket "$W/tk1.md" --outbox "$W/st-bf" --out "$W/knc.md" >/dev/null; grep -q '(not checked)' "$W/knc.md" && ! grep -q 'not created yet' "$W/knc.md"; ok $? 0 "K11 branch not checked: no 'not created yet' claim"
echo "== L. review round 2: paged listings, stale rule, missing link comment"
echo '{"results":[{"content":{"id":"7","title":"Plan: T-1 - Demo"}}],"size":1,"_links":{"next":"/rest/api/search?cursor=abc"}}' > "$W/l-p1.json"
echo '{"results":[{"content":{"id":"8","title":"Plan: T-1 - Demo (copy)"}}],"size":1,"_links":{}}' > "$W/l-p2.json"
echo '{"results":[{"content":{"id":"9","title":"Plan: T-3 - Other"}}],"size":1,"_links":{"next":"/rest/api/search?cursor=x"}}' > "$W/l-p3.json"
$T find --key T-2 --search "$W/l-p3.json" --comments "$W/k-none.json" >/dev/null 2>&1; ok $? 2 "L1 a page linking 'next' (no totalSize): incomplete, can't tell (not 'none')"
$T find --key T-1 --search "$W/l-p1.json" --comments "$W/k-none.json" >/dev/null 2>&1; ok $? 2 "L1 a hit on page 1 of 2 is not trusted: a duplicate may be on page 2"
$T find --key T-1 --search "$W/l-p1.json" --search "$W/l-p2.json" --comments "$W/k-none.json" >/dev/null 2>&1; ok $? 2 "L1 both pages given: the duplicate is found (several)"
echo '{"content":{"totalCount":1,"nodes":[{"id":"7","title":"Plan: T-1 - Demo"}],"pageInfo":{"hasNextPage":true}}}' > "$W/l-n1.json"
$T find --key T-1 --search "$W/l-n1.json" --comments "$W/k-none.json" >/dev/null 2>&1; ok $? 2 "L1 nodes shape with hasNextPage: incomplete"
$T find --key T-1 --comments "$W/k-two.json" --search "$W/k-200.json" | grep -q 'listed page 200 wins'; ok $? 0 "L2 stale record: the note says the listed page wins and how to confirm the stale id"
$T find --key T-1 --comments "$W/k-two.json" --search "$W/k-200.json" --gone 100 | grep -q stale_records; ok $? 1 "L2 a stale id confirmed gone (--gone) is dropped"
$T find --key T-1 --comments "$W/k-none.json" --search "$W/k-200.json" | grep -q '"missing_link_comment": true'; ok $? 0 "L3 page found without its link comment: flagged for the re-run to post it"
$T find --key AIUE-61 --comments "$FX/AIUE-61-issue-markdown.json" --search "$REALCQL" | grep -q '"missing_link_comment": false'; ok $? 0 "L3 page with its link comment: nothing missing"
$T find --key T-1 --comments "$W/k-100.json" --search "$W/k-200.json" | grep -q '"missing_link_comment": true'; ok $? 0 "L3 a link comment naming only a stale page: the current page's link is missing"
echo "== M. the plan is a local working copy: publish, mirror, rebuild"
cp "$R/$P" "$W/plan-orig.md"; printf '\n## Added later\nnot yet published\n' >> "$R/$P"
V=$(python3 -c "import json;print(json.load(open('$TS/T-1.state.json'))['version'])")
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --page-version $V --outbox "$TS" --out "$W/m1.md" >/dev/null; ok $? 0 "M1 a flush after a local edit (--mirrored)"
! grep -q 'Added later' "$W/m1.md" && grep -q "sha256 \`$PH\`" "$W/m1.md"; ok $? 0 "M1 the mirror only moves on publish (unpublished edit not sent, hash unchanged)"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --local --page-version $V --outbox "$TS" --out "$W/m2.md" >/dev/null; ok $? 0 "M2 publish the edited plan"
PH2=$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1]).read().rstrip().encode()).hexdigest()[:16])" "$R/$P")
grep -q 'Added later' "$W/m2.md" && grep -q "sha256 \`$PH2\`" "$W/m2.md" && [ "$PH" != "$PH2" ]; ok $? 0 "M2 the published plan carries the edit and its new sha256"
cp -r "$TS" "$W/st-tamper"; echo tampered >> "$W/st-tamper/T-1.plan.md"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --page-version $V --outbox "$W/st-tamper" --out "$W/x.md" 2>/dev/null; ok $? 2 "M3 a store copy that doesn't match the published sha256 is refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/spage.json" --outbox "$W/st-fresh" --out "$W/x.md" 2>/dev/null; ok $? 2 "M4 --mirrored with no published plan in the store (fresh worktree) is refused"
python3 - "$W/m1.md" "$W/m1page.json" <<'EOF'
import json,re,sys
s=open(sys.argv[1]).read(); s=re.sub(r"^  ", "", s, flags=re.M); s=re.sub(r"^- ", "* ", s, flags=re.M)
json.dump([{"type":"text","text":json.dumps({"id":"950","body":s})}],open(sys.argv[2],"w"))
EOF
$T extract-plan --current "$W/m1page.json" --out "$W/rebuilt.md" >/dev/null; ok $? 0 "M5 extract-plan rebuilds the working copy from the page"
grep -qx '# Feature: T-1 demo' "$W/rebuilt.md" && grep -qx '## Tasks' "$W/rebuilt.md" && grep -qx '## not a heading inside a fence' "$W/rebuilt.md" && ! grep -q 'Added later' "$W/rebuilt.md"; ok $? 0 "M5 headings promoted back two levels, fenced lines untouched, the published version"
$T extract-plan --current "$W/spage.json" --out "$W/x.md" 2>/dev/null; ok $? 3 "M6 a page with only the Plan placeholder: nothing to rebuild (3)"
$T state --repo "$R" --key T-1 --outbox "$W/st-fresh" --set page_id=950 >/dev/null
$T state --repo "$R" --key T-1 --outbox "$W/st-fresh" --save-plan "$W/rebuilt.md" --set plan_source="page version 4" >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/m1page.json" --outbox "$W/st-fresh" --out "$W/m7.md" >/dev/null; ok $? 0 "M7 a fresh worktree flushes with the rebuilt copy"
grep -q 'rebuilt from page version 4' "$W/m7.md" && grep -q 'tasks 1-3 done' "$W/m7.md"; ok $? 0 "M7 header says the copy was rebuilt from the page; log entries kept"
$T render --repo "$R" --plan .claude/work/T-1/nope.md --meta "$W/meta.json" --current "$W/spage.json" --outbox "$W/st-fresh" --out "$W/x.md" 2>/dev/null; ok $? 2 "M8 --plan naming a missing working copy is refused"
$T ticket --repo "$PL" --key T-1 --breakdown "$W/T-0-demo.md" --out "$W/x.md" 2>/dev/null; ok $? 2 "M9 ticket without --source is refused"
$T find --key T-1 --state-id 950 --comments "$W/issue.json" --search "$W/cql.json" | grep -q '"state file"'; ok $? 0 "M10 find reads the state file's page id"
$T render --repo "$R" --plan $P --mirrored --meta "$W/meta.json" --current "$W/spage.json" --outbox "$TS" --out "$W/x.md" 2>/dev/null; ok $? 2 "M11 --plan and --mirrored together are refused"
[ -z "$(git -C "$R" status --porcelain --untracked-files=all)" ]; ok $? 0 "M12 after the whole lifecycle git status is still clean (working copies untracked)"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
