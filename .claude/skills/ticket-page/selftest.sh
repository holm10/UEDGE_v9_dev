#!/usr/bin/env bash
# End-to-end test of ticket_page.py (the ticket-page skill's helper) in a throwaway git repo, with no Atlassian calls:
# new page (stub -> Ticket page line -> --new-page first fill -> verify -> --local -> --current after a simulated
# Confluence round trip), the refusals, verify after a failed update and one retry, a dry run, the RCA mirror and the
# Jira-fallback text checks. Atlassian responses and the PostToolUse hook log are simulated.
# Usage: .claude/skills/ticket-page/selftest.sh [workdir]   (default: a new temporary directory)
set -u
H="$(cd "$(dirname "$0")" && pwd)/ticket_page.py"; W="${1:-$(mktemp -d)}"; mkdir -p "$W"; cd "$W" || exit 2
echo "workdir: $W"
T="uv run -q $H"; R="$W/repo"; ST="$W/store"; PASS=0; FAIL=0
ok(){ if [ "$1" = "$2" ]; then PASS=$((PASS+1)); echo "PASS $3"; else FAIL=$((FAIL+1)); echo "FAIL $3 (exit $1, want $2)"; fi; }
git init -q "$R" && git -C "$R" checkout -q -b feature/v9-T-1-demo
mkdir -p "$R/.claude/plans" "$R/docs/rca"
cat > "$R/.claude/plans/T-1-demo.md" <<'EOF'
# Feature: T-1 demo

## Summary
**Branch / worktree**: `feature/v9-T-1-demo` @ /Users/someone/work/repo
Scratch in /scratch/someone/run1 and /p/lustre1/someone/x, see file:///Users/someone/r.html

## Tasks
```
## not a heading inside a fence
```
EOF
printf '# RCA: issue 7\n\nRoot cause: x.\n' > "$R/docs/rca/issue-7.md"
git -C "$R" add -A && git -C "$R" -c user.email=t@t -c user.name=t commit -qm "plan"
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
P=.claude/plans/T-1-demo.md
echo "== A. new page"
meta ""; $T render --repo "$R" --plan $P --meta "$W/meta.json" --outbox "$ST" --out "$W/dry0.md" >/dev/null; ok $? 0 "A0 render before the page exists (dry-run shape)"
[ ! -e "$ST" ]; ok $? 0 "A0 render wrote nothing to the store"
$T stub --key T-1 > "$W/stub.md"; ok "$(cat "$W/stub.md")" "Plan page for T-1; content follows." "A1 stub text"
python3 -c "import json;b=open('$W/stub.md').read();json.dump([{'type':'text','text':json.dumps({'id':'900','body':b})}],open('$W/stub.json','w'))"
meta 900
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stub.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "A2 stub without --new-page refused"
echo "something else" > "$W/notstub.md"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/notstub.md" --new-page --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "A3 --new-page with a non-stub page refused"
printf '\n**Ticket page**: Confluence page 900 (https://x/wiki/900)\n' >> "$R/$P"; git -C "$R" -c user.email=t@t -c user.name=t commit -qam "Records the T-1 ticket page"
REV=$(git -C "$R" rev-parse --short HEAD)
$T queue --repo "$R" --key T-1 --outbox "$ST" --add Progress plan-feature "Plan published ($REV)." >/dev/null
$T render --repo "$R" --plan $P --plan-rev $REV --meta "$W/meta.json" --current "$W/stub.json" --new-page --outbox "$ST" --out "$W/b1.md" >/dev/null; ok $? 0 "A4 first fill with --new-page (wrapped stub)"
grep -q "as of \`$REV\`" "$W/b1.md"; ok $? 0 "A4 header cites the commit with the Ticket page line"
grep -q 'Ticket page\*\*: Confluence page 900' "$W/b1.md"; ok $? 0 "A4 mirror contains the Ticket page line"
grep -qE '/Users/someone|/scratch/someone|/p/lustre1|file:///Users' "$W/b1.md"; ok $? 1 "A4 no local or cluster paths, file:// URL masked"
grep -q '^#### not a heading inside a fence' "$W/b1.md"; ok $? 1 "A4 fenced '##' line not demoted"
fakelog 900 "$W/b1.md" 2
$T verify --body "$W/b1.md" --page-id 900 --after-version 1 --log "$W/hook.jsonl" >/dev/null; ok $? 0 "A5 verify the first update (v2)"
$T state --repo "$R" --key T-1 --outbox "$ST" --set version=2 plan_rev=$REV page_id=900 --save-body "$W/b1.md" >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$ST" --mark-sent >/dev/null
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stub.md" --new-page --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "A6 --new-page refused once a version is written"
echo "== B. later flushes"
$T queue --repo "$R" --key T-1 --outbox "$ST" --add Reviews loop $'Reviewer: plan round 1 APPROVE (0/0/1).\n# ran: pytest -k D_only\n```\nRESULT: AGREE\n```' >/dev/null
$T render --repo "$R" --plan $P --plan-rev $REV --meta "$W/meta.json" --local --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "B1 --local without --page-version refused"
$T render --repo "$R" --plan $P --plan-rev $REV --meta "$W/meta.json" --local --page-version 3 --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "B2 --local with a moved version refused"
$T render --repo "$R" --plan $P --plan-rev $REV --meta "$W/meta.json" --local --page-version 2 --outbox "$ST" --out "$W/b2.md" >/dev/null; ok $? 0 "B3 --local with the matching version"
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
$T render --repo "$R" --plan $P --plan-rev $REV --meta "$W/meta.json" --current "$W/rt.md" --outbox "$ST" --out "$W/b3.md" > "$W/out.txt"; ok $? 0 "B5 --current after a round trip"
grep -q '0 new, 0 restored' "$W/out.txt"; ok $? 0 "B5 no duplicates, nothing lost"
grep -q 'ran: pytest -k D_only' "$W/b3.md"; ok $? 0 "B5 the '#' line survives the round trip"
python3 -c "s=open('$W/rt.md').read(); open('$W/trunc.md','w').write(s[:s.index('## Reviews')])"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/trunc.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "B6 truncated --current refused"
python3 -c "
s=open('$W/rt.md').read(); i=s.index('* **2026'); j=s.index('\n', i); open('$W/lost.md','w').write(s[:i]+s[j+1:])"
$T queue --repo "$R" --key T-1 --outbox "$W/store-other" --add Progress x y >/dev/null
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/lost.md" --outbox "$ST" --out "$W/b4.md" | grep -q '1 restored'; ok $? 0 "B7 an own entry the page lost is restored from the sent log"
python3 -c "
s=open('$W/rt.md').read(); s=s.replace('## Validation','## Validation\n\n* **2026-10-14** · other-wt · from another worktree\n'); open('$W/other.md','w').write(s)"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/other.md" --outbox "$ST" --out "$W/b5.md" >/dev/null; ok $? 0 "B8 page with another worktree's entry"
python3 - "$W/b5.md" "$W/b5cut.md" <<'EOF'
import sys
s=open(sys.argv[1]).read(); s=s[:s.index("\n## Plan\n")]; i=s.index("from another worktree"); i=s.rindex("\n",0,i); j=s.index("\n",i+1)
open(sys.argv[2],"w").write(s[:i]+s[j:])
EOF
$T state --repo "$R" --key T-1 --outbox "$ST" --save-body "$W/b5.md" >/dev/null
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/b5cut.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "B9 a page with fewer entries than last sent refused"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/b5cut.md" --allow-fewer --outbox "$ST" --out "$W/x.md" >/dev/null; ok $? 0 "B9 accepted with --allow-fewer"
echo "== C. verify after a failed update / retry"
$T verify --body "$W/b5.md" --page-id 900 --after-version 3 --log "$W/hook.jsonl" 2>/dev/null; ok $? 3 "C1 failed update (not logged): verify says not logged, no mismatch"
cp "$W/b5.md" "$W/b5bad.md"; echo "typo" >> "$W/b5bad.md"; fakelog 900 "$W/b5bad.md" 4
$T verify --body "$W/b5.md" --page-id 900 --after-version 3 --log "$W/hook.jsonl" 2>/dev/null; ok $? 1 "C2 transcription error detected"
fakelog 900 "$W/b5.md" 5
$T verify --body "$W/b5.md" --page-id 900 --after-version 4 --log "$W/hook.jsonl" >/dev/null; ok $? 0 "C3 one retry verified (v5 = checked 3 + 2 own updates)"
echo "== D. other refusals and dry run"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "D1 existing page without --current/--local refused"
python3 -c "import json;json.dump({'body':{'storage':{'value':'<p/>'}}},open('$W/stor.json','w'))"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/stor.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "D2 storage form refused"
python3 -c "import json;d=json.load(open('$W/meta.json'));d.pop('branch');json.dump(d,open('$W/m2.json','w'))"
$T render --repo "$R" --plan $P --meta "$W/m2.json" --local --page-version 3 --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "D3 missing meta key exits 2"
before=$(ls -l "$ST" | md5sum 2>/dev/null || ls -l "$ST" | md5)
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/rt.md" --entry Progress test "dry entry" --outbox "$ST" --allow-fewer --out "$W/dry.md" >/dev/null; ok $? 0 "D4 dry-run render with --entry"
after=$(ls -l "$ST" | md5sum 2>/dev/null || ls -l "$ST" | md5); ok "$before" "$after" "D4 dry run left the store unchanged"
echo "== E. RCA mirror"
$T render --repo "$R" --plan docs/rca/issue-7.md --plan-title RCA --meta "$W/meta.json" --current "$W/rt.md" --allow-fewer --outbox "$W/st-rca" --out "$W/rca.md" >/dev/null; ok $? 0 "E1 RCA render"
grep -q '^## RCA$' "$W/rca.md" && grep -q 'The RCA file in the repo' "$W/rca.md"; ok $? 0 "E1 RCA heading and header"
echo "== F. Jira fallback text"
printf 'x%.0s' $(seq 1 1600) | $T sanitize --repo "$R" >/dev/null 2>&1; ok $? 1 "F1 1500-char cap"
printf '**PIV record: Reviews** (2026-10-15, loop) · _posted by an agent_\nreport /gpfs/u/someone/r.md, /global/homes/s/someone/x, /g/g19/someone/y, /usr/workspace/someone/z\n' | $T sanitize --repo "$R" > "$W/fb.txt"; ok $? 0 "F2 fallback comment sanitised"
grep -qE 'someone' "$W/fb.txt"; ok $? 1 "F2 cluster paths masked"
printf 'see https://user:hunter22@host/x\n' | $T sanitize --repo "$R" >/dev/null 2>&1; ok $? 1 "F3 credentials refused"
$T state --repo "$R" --key T-1 --outbox "$W/st-fb" --set fallback_count=8 fallback_summary_id=10050 >/dev/null; ok $? 0 "F4 fallback state"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
