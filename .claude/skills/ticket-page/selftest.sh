#!/usr/bin/env bash
# Test of ticket_page.py (the ticket-page skill's helper) in a throwaway git repo, with no Atlassian calls: one case per
# guarantee. (A) the page spec creates: Ticket section, skeleton, verified create, backfill; (B) one page per ticket:
# find on real read-only responses (fixtures/) and its evidence rules; (C) no silent loss of log entries: publish,
# --local, a Confluence round trip, the refusals, verify and one retry; (D) plan provenance: the mirror moves only on
# publish, the sha256, extract-plan in a fresh worktree, the RCA; (E) sanitising and secrets; (F) the outbox and the
# epic Progress page. The PostToolUse hook log and the other Atlassian responses are simulated.
# Usage: .claude/skills/ticket-page/selftest.sh [workdir]   (default: a new temporary directory). Exit 0 = all passed.
set -u
H="$(cd "$(dirname "$0")" && pwd)/ticket_page.py"; FX="$(dirname "$H")/fixtures"; W="${1:-$(mktemp -d)}"
mkdir -p "$W"; cd "$W" || exit 2; echo "workdir: $W"
T="uv run -q $H"; R="$W/repo"; ST="$W/store"; PASS=0; FAIL=0
ok(){ if [ "$1" = "$2" ]; then PASS=$((PASS+1)); echo "PASS $3"; else FAIL=$((FAIL+1)); echo "FAIL $3 (got $1, want $2)"; fi; }
git init -q "$R" && git -C "$R" checkout -q -b feature/v9-T-1-demo
printf '.claude/work/\n' > "$R/.gitignore"; echo demo > "$R/README"
git -C "$R" add -A && git -C "$R" -c user.email=t@t -c user.name=t commit -qm base
mkdir -p "$R/.claude/work/T-1" "$R/.claude/work/issue-7"
cat > "$R/.claude/work/T-1/plan.md" <<'EOF'
# Feature: T-1 demo

## Summary
**Branch / worktree**: `feature/v9-T-1-demo` @ /Users/someone/work/repo
Scratch in /scratch/someone/run1 and /p/lustre1/someone/x, see file:///Users/someone/r.html

### Detail
## Tasks
```
## not a heading inside a fence
```
EOF
printf '# RCA: issue 7\n\nRoot cause: x.\n' > "$R/.claude/work/issue-7/rca.md"
P=.claude/work/T-1/plan.md
hash(){ python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1]).read().rstrip().encode()).hexdigest()[:16])" "$1"; }
PH=$(hash "$R/$P")
meta(){ python3 - "$W/meta.json" "$@" <<'EOF'
import json,sys
d=dict(key="T-1",key_url="https://x/browse/T-1",summary="Demo",epic="T-0",epic_url="https://x/browse/T-0",
 prd_title="PRD: T-0 - Demo",prd_url="https://x/wiki/1",branch="feature/v9-T-1-demo",status="Planning",
 updated="2026-10-15",skill="test")
for kv in sys.argv[2:]:
    k,_,v=kv.partition("="); d[k]=v
json.dump(d,open(sys.argv[1],'w'))
EOF
}
# fakelog <create|update> <title or page id> <body file> <version>: a PostToolUse record of a successful call
fakelog(){ python3 - "$W/hook.jsonl" "$@" <<'EOF'
import json,sys
log,tool,ref,bodyf,ver=sys.argv[1:]
ti={"body":open(bodyf).read()}
ti.update({"title":ref,"parentId":"800"} if tool=="create" else {"pageId":ref})
pid="950" if tool=="create" else ref
rec={"tool_name":"mcp__atlassian__%sConfluencePage"%tool,"tool_input":ti,
     "tool_response":[{"type":"text","text":json.dumps({"id":pid,"version":{"number":int(ver)}})}]}
open(log,"a").write(json.dumps(rec)+"\n")
EOF
}
V(){ $T verify --log "$W/hook.jsonl" "$@" >/dev/null 2>&1; }

echo "== A. the page spec creates"
cat > "$W/breakdown.md" <<'EOF'
# Spec: T-0 - Demo

## Tickets
### TICKET-1 — Demo · `T-1`
- Scope: add the demo in /Users/someone/x.
#### Acceptance
- it works
### TICKET-9 — Follow-up of T-1 · `T-9`
- Scope: later.
### Coordinate with T-3 · `T-4`
- Scope: x.
### T-5 one
### T-5 two
## Dependency graph
T-1 -> T-9
EOF
TK(){ $T ticket --repo "$R" --breakdown "$W/breakdown.md" --source "the epic breakdown page (Confluence page 700, version 3)" "$@"; }
TK --key T-1 --out "$W/tk1.md" >/dev/null; ok $? 0 "A1 Ticket section from the breakdown entry (by \`KEY\`)"
grep -q 'it works' "$W/tk1.md" && ! grep -qE 'TICKET-9|Dependency graph|/Users/someone' "$W/tk1.md" && grep -q '^_Scope as filed' "$W/tk1.md"; ok $? 0 "A1 entry ends at the next heading of its level or higher; paths masked; source line"
TK --key T-3 --out "$W/x.md" >/dev/null 2>&1; ok $? 3 "A2 a key only in another entry's heading is not matched (exit 3: use the Jira description)"
TK --key T-5 --out "$W/x.md" >/dev/null 2>&1; ok $? 2 "A3 two entries match: several (2)"
printf '# Goal\nDo x.\n## Acceptance\n- y\n' > "$W/desc.md"
$T ticket --repo "$R" --key T-1 --text "$W/desc.md" --source "the Jira description of T-1" --out "$W/tk2.md" >/dev/null && grep -q '^### Goal' "$W/tk2.md"; ok $? 0 "A4 Ticket section from a Jira description, headings below H2"
meta status=Planned
$T render --repo "$R" --meta "$W/meta.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "A5 skeleton without --ticket refused"
$T render --repo "$R" --meta "$W/meta.json" --ticket "$W/tk1.md" --outbox "$ST" --out "$W/sk.md" >/dev/null; ok $? 0 "A6 skeleton render"
[ "$(grep -cE '^## (Ticket|Progress|Validation|Reviews|Findings and decisions|Plan)$' "$W/sk.md")" = 6 ] && grep -q '_Not written yet' "$W/sk.md" && grep -q 'Status:\*\* Planned' "$W/sk.md" && [ ! -e "$ST" ]; ok $? 0 "A6 Ticket, four logs, Plan placeholder, status Planned; nothing written to the store"
meta status=Planned page_id=950
$T render --repo "$R" --meta "$W/meta.json" --ticket "$W/tk1.md" --current "$W/sk.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "A7 the skeleton never rewrites an existing page"
fakelog create "Plan: T-1 - Demo" "$W/sk.md" 1
$T verify --log "$W/hook.jsonl" --body "$W/sk.md" --created --title "Plan: T-1 - Demo" --parent-id 800 | grep -q 'page 950'; ok $? 0 "A8 verify the create, prints the new page id"
cp "$W/sk.md" "$W/skbad.md"; echo typo >> "$W/skbad.md"
V --body "$W/skbad.md" --created --title "Plan: T-1 - Demo"; ok $? 1 "A8 a mistyped create is detected"
TK --key T-1 --backfill --date 2026-10-16 --out "$W/tkb.md" >/dev/null
meta status=Backfilled backfilled=2026-10-16 jira_status="In Progress"
$T render --repo "$R" --meta "$W/meta.json" --ticket "$W/tkb.md" --outbox "$ST" --out "$W/bf.md" >/dev/null
grep -q '^> \*\*Backfilled:\*\* 2026-10-16' "$W/bf.md" && grep -q 'Jira status then: In Progress' "$W/bf.md" && grep -q '_Not mirrored here yet' "$W/bf.md" && grep -q 'Scope as read on 2026-10-16' "$W/bf.md" && ! grep -qiE 'Scope as filed|not written yet|created when the ticket was filed' "$W/bf.md"; ok $? 0 "A9 backfill: Backfilled field, 'not mirrored', 'as read on', no false claim"

echo "== B. one page per ticket: find"
CQL="$FX/AIUE-8-container-children-cql.json"; NONE="$W/c-none.json"
echo '{"fields":{"comment":{"comments":[],"total":0}}}' > "$NONE"
$T find --key AIUE-61 --comments "$FX/AIUE-61-issue-markdown.json" --search "$CQL" > "$W/f1.json" 2>/dev/null; ok $? 0 "B1 real issue + real listing: AIUE-61 found"
grep -q '"page_id": "2293761"' "$W/f1.json" && grep -q 'Jira link comment' "$W/f1.json" && grep -q '"missing_link_comment": false' "$W/f1.json"; ok $? 0 "B1 the legacy 'Plan page:' link comment is read; no link missing"
$T find --key AIUE-61 --comments "$FX/AIUE-61-issue-markdown-nodes-shape.json" --search "$CQL" 2>/dev/null | grep -q '"page_id": "2293761"'; ok $? 0 "B2 the issues.nodes response shape"
$T find --key AIUE-61 --comments "$FX/AIUE-61-issue-adf.json" --search "$CQL" 2>/dev/null | grep -q 'Jira link comment'; ok $? 0 "B3 ADF comment bodies are flattened"
$T find --key AIUE-8 --search "$FX/PRD-AIUE-8-cql-nodes-shape.json" --comments "$NONE" >/dev/null 2>&1; ok $? 3 "B4 content.nodes listing, complete, no page: none (3)"
$T find --key AIUE-46 --comments "$NONE" --search "$CQL" >/dev/null 2>&1; ok $? 3 "B4 a child with no page in the real listing: none"
$T find --key T-1 >/dev/null 2>&1; ok $? 2 "B5 no evidence: can't tell (2), never 'create'"
echo '{"results":[],"totalSize":0}' > "$W/c-empty.json"
$T find --key T-1 --search "$W/c-empty.json" >/dev/null 2>&1; ok $? 2 "B5 a listing without the comments: can't tell"
echo '{"fields":{"comment":{"comments":[{"id":"1","body":"x"}],"total":5}}}' > "$W/c-paged.json"
$T find --key T-1 --search "$W/c-empty.json" --comments "$W/c-paged.json" >/dev/null 2>&1; ok $? 2 "B6 a paged comment list (1 of 5): can't tell"
echo '{"results":[{"content":{"id":"7","title":"Plan: T-1 - Demo"}}],"_links":{"next":"/x?cursor=a"}}' > "$W/l-p1.json"
echo '{"results":[{"content":{"id":"8","title":"Plan: T-1 - Demo (copy)"}}],"_links":{}}' > "$W/l-p2.json"
$T find --key T-1 --search "$W/l-p1.json" --comments "$NONE" >/dev/null 2>&1; ok $? 2 "B7 a hit on page 1 of 2 is not trusted (a duplicate may be on page 2)"
$T find --key T-1 --search "$W/l-p1.json" --search "$W/l-p2.json" --comments "$NONE" >/dev/null 2>&1; ok $? 2 "B7 both pages given: two pages, stop and ask"
echo '{"results":[{"content":{"id":"7","title":"Plan: T-1 - Demo"}}],"totalSize":3}' > "$W/l-part.json"
$T find --key T-1 --search "$W/l-part.json" --comments "$NONE" >/dev/null 2>&1; ok $? 2 "B7 fewer results than totalSize: can't tell"
echo '{"results":[{"content":{"id":"200","title":"Plan: T-1 - Demo"}},{"content":{"id":"201","title":"Plan: T-10 - Other"}}],"totalSize":2}' > "$W/l-200.json"
$T find --key T-1 --search "$W/l-200.json" --comments "$NONE" 2>/dev/null | grep -q '"missing_link_comment": true'; ok $? 0 "B8 found by title (T-10 not matched); its link comment is missing"
echo '{"fields":{"comment":{"comments":[{"id":"1","body":"Ticket page: [x](https://x/100) (Confluence page id `100`)."}]}}}' > "$W/c-100.json"
$T find --key T-1 --comments "$W/c-100.json" --search "$W/l-200.json" > "$W/f8.json" 2>/dev/null; ok $? 0 "B9 recreated page: the listed id wins"
grep -q '"page_id": "200"' "$W/f8.json" && grep -q stale_records "$W/f8.json"; ok $? 0 "B9 the stale recorded id (100) is reported"
$T find --key T-1 --comments "$W/c-100.json" --search "$W/l-200.json" --gone 100 2>/dev/null | grep -q stale_records; ok $? 1 "B9 a stale id confirmed gone (--gone) is dropped"
$T find --key T-1 --comments "$W/c-100.json" --search "$W/c-empty.json" 2>/dev/null | grep -q '"not_listed": true'; ok $? 0 "B10 recorded but not under this container (moved ticket): flagged to confirm"
$T find --key T-1 --comments "$W/c-100.json" --search "$W/c-empty.json" --gone 100 >/dev/null 2>&1; ok $? 3 "B10 after CQL confirms it gone: none"
$T find --key T-1 --state-id 555 2>/dev/null | grep -q '"page_id": "555"'; ok $? 0 "B11 the state file's page id"
echo '{"fields":{"comment":{"comments":[{"id":"1","body":"**PIV record: ticket filed** (2026-10-16, spec)"}]}}}' > "$W/c-piv.json"
$T find --key T-1 --fallback --comments "$W/c-piv.json" >/dev/null 2>&1; ok $? 0 "B12 fallback: a PIV record comment exists, post nothing"
python3 -c "
import json;b={'type':'doc','content':[{'type':'paragraph','content':[{'type':'text','text':'PIV record: x','marks':[{'type':'strong'}]}]}]}
json.dump({'fields':{'comment':{'comments':[{'id':str(i),'body':b} for i in range(8)],'total':8}}},open('$W/c-cap.json','w'))"
$T find --key T-1 --fallback --comments "$W/c-cap.json" 2>/dev/null | grep -q '"piv_cap_reached": true'; ok $? 0 "B12 fallback: ADF PIV record comments counted, cap reached"
$T find --key T-1 --fallback --comments "$NONE" >/dev/null 2>&1; ok $? 3 "B12 fallback: none yet, post it (3)"

echo "== C. no silent loss of log entries"
meta page_id=950 page_url=https://x/wiki/950
$T queue --repo "$R" --key T-1 --outbox "$ST" --add Progress plan-feature "Plan published (sha256 $PH)." >/dev/null
$T render --repo "$R" --plan $P --date 2026-10-16 --meta "$W/meta.json" --current "$W/sk.md" --outbox "$ST" --out "$W/b1.md" >/dev/null; ok $? 0 "C1 first publish fills the spec-created page (--current)"
grep -q 'it works' "$W/b1.md" && ! grep -q '_Not written yet' "$W/b1.md" && grep -q "published 2026-10-16 (sha256 \`$PH\`)" "$W/b1.md"; ok $? 0 "C1 Ticket kept, placeholder replaced, header cites date and sha256"
! grep -qE '/Users/someone|/scratch/someone|/p/lustre1|file:///Users' "$W/b1.md" && grep -q '^## not a heading inside a fence' "$W/b1.md" && grep -q '^##### Detail' "$W/b1.md"; ok $? 0 "C1 paths masked (file:// too); headings demoted two levels, fenced line untouched"
fakelog update 950 "$W/b1.md" 2
V --body "$W/b1.md" --page-id 950 --after-version 1; ok $? 0 "C2 verify the update (v2)"
$T state --repo "$R" --key T-1 --outbox "$ST" --set version=2 modified=2026-10-16T10:00:00.000Z page_id=950 --save-body "$W/b1.md" --save-plan "$R/$P" --plan-title Plan --date 2026-10-16 >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$ST" --mark-sent >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$ST" --add Reviews loop $'Reviewer: plan round 1 APPROVE (0/0/1).\n# ran: pytest -k D_only\n```\nRESULT: AGREE\n```' >/dev/null
# The version check: the parent's getConfluencePageDescendants listing (lastModified, no version), saved as the tool result
lst(){ f=$1; shift; python3 -c "import json,sys;print(json.dumps([{'type':'text','text':json.dumps({'results':[{'id':i,'lastModified':m} for i,m in zip(sys.argv[2::2],sys.argv[3::2])]})}]))" x "$@" > "$f"; }
lst "$W/lst-other.json" 950 2026-10-16T10:05:00.000Z
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --listing "$W/lst-other.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "C3 --local refused: modified after this worktree's update (someone else wrote)"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "C3 an existing page without --current/--local refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "C3 --local without --listing refused"
lst "$W/lst2.json" 949 2026-10-17T00:00:00.000Z 950 2026-10-16T10:00:00.000Z
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --listing "$W/lst2.json" --outbox "$ST" --out "$W/b2.md" >/dev/null; ok $? 0 "C4 --local: the page's lastModified is this worktree's last update"
[ "$(grep -c 'Plan published' "$W/b2.md")" = 1 ] && grep -q '^  \\# ran: pytest' "$W/b2.md"; ok $? 0 "C4 earlier entry kept once; an entry's '#' line escaped"
lst "$W/lst-p1.json" 948 2026-10-16T10:00:00.000Z; lst "$W/lst-p2.json" 949 2026-10-16T10:00:00.000Z
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --listing "$W/lst-p1.json" --listing "$W/lst-p2.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "C3 --local refused: the page is not in the listing"
lst "$W/lst-p2.json" 949 2026-10-17T00:00:00.000Z 950 2026-10-16T10:00:00.000Z
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --listing "$W/lst-p1.json" --listing "$W/lst-p2.json" --outbox "$ST" --out "$W/b2p.md" >/dev/null && cmp -s "$W/b2.md" "$W/b2p.md"; ok $? 0 "C4 --local: the page found on the second page of results"
echo 'Error: the tool output is too large' > "$W/lst-err.json"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --listing "$W/lst-err.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "C3 --local refused: a listing that is not a tool result"
cp -r "$ST" "$W/st-nomod"; python3 -c "import json,sys;p=sys.argv[1];d=json.load(open(p));d.pop('modified');json.dump(d,open(p,'w'))" "$W/st-nomod/T-1.state.json"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --listing "$W/lst2.json" --outbox "$W/st-nomod" --out "$W/x.md" 2>/dev/null; ok $? 2 "C3 --local refused: a state file from before AIUE-143 (no modified)"
meta page_id=5308417; $T state --repo "$R" --key T-1 --outbox "$W/st-real" --set page_id=5308417 version=35 modified=2026-10-22T01:56:38.226Z --save-body "$W/b2.md" >/dev/null
$T render --repo "$R" --plan $P --meta "$W/meta.json" --local --listing "$FX/PRD-AIUE-9-descendants.json" --outbox "$W/st-real" --out "$W/x.md" >/dev/null; ok $? 0 "C4 --local --listing on a real response (fixture: Progress: AIUE-9 v35, lastModified = the update's version.createdAt)"
meta page_id=950 page_url=https://x/wiki/950
# The full read: fetch (text + metadata.version) and getConfluencePage (content.nodes[0].body), saved as tool results
python3 - "$W/b2.md" "$W/fetch.json" "$W/gcp.json" <<'EOF'
import json,sys
s=open(sys.argv[1]).read()
json.dump({"id":"ari:cloud:confluence:x:page/950","title":"Plan: T-1 - Demo","text":s,"metadata":{"spaceId":"1","version":3}},open(sys.argv[2],"w"))
json.dump([{"type":"text","text":json.dumps({"content":{"totalCount":1,"nodes":[{"id":"950","title":"Plan: T-1 - Demo","body":s}]}})}],open(sys.argv[3],"w"))
EOF
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b2.md" --outbox "$ST" --out "$W/cur-md.md" >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/fetch.json" --outbox "$ST" --out "$W/cur-f.md" >/dev/null && cmp -s "$W/cur-md.md" "$W/cur-f.md"; ok $? 0 "C4 --current reads a saved fetch result (text) like the markdown"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/gcp.json" --outbox "$ST" --out "$W/cur-g.md" >/dev/null && cmp -s "$W/cur-md.md" "$W/cur-g.md"; ok $? 0 "C4 --current reads a saved getConfluencePage result (content.nodes)"
fakelog update 950 "$W/b2.md" 3
$T state --repo "$R" --key T-1 --outbox "$ST" --set version=3 modified=2026-10-16T11:00:00.000Z --save-body "$W/b2.md" >/dev/null; lst "$W/lst3.json" 950 2026-10-16T11:00:00.000Z; $T queue --repo "$R" --key T-1 --outbox "$ST" --mark-sent >/dev/null
# Confluence round trip: continuation indents dropped, '\#' -> '#', '_x_' -> '*x*', bullets '-' -> '*'; saved as the tool result
python3 - "$W/b2.md" "$W/rt.md" "$W/rt.json" <<'EOF'
import json,re,sys
s=open(sys.argv[1]).read(); s=s[:s.index("\n## Plan\n")]
s=re.sub(r"^  ", "", s, flags=re.M).replace("\\#","#").replace("_No entries yet._","*No entries yet.*")
s=re.sub(r"^- \*\*", "* **", s, flags=re.M); open(sys.argv[2],"w").write(s)
json.dump([{"type":"text","text":json.dumps({"id":"950","body":s})}],open(sys.argv[3],"w"))
EOF
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/rt.json" --outbox "$ST" --out "$W/b3.md" > "$W/out.txt"; ok $? 0 "C5 --current after a round trip (MCP-wrapped tool result)"
grep -q '0 new, 0 restored' "$W/out.txt" && grep -q 'ran: pytest -k D_only' "$W/b3.md"; ok $? 0 "C5 no duplicates, nothing lost"
python3 -c "s=open('$W/rt.md').read(); open('$W/trunc.md','w').write(s[:s.index('## Reviews')])"
$T render --repo "$R" --plan $P --meta "$W/meta.json" --current "$W/trunc.md" --outbox "$W/st-trunc" --out "$W/x.md" 2>/dev/null; ok $? 2 "C6 a truncated page (log heading missing) refused, also with no local record"
python3 -c "
s=open('$W/rt.md').read(); i=s.index('* **2026'); j=s.index('\n', i); open('$W/lost.md','w').write(s[:i]+s[j+1:])"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/lost.md" --outbox "$ST" --out "$W/x.md" | grep -q '1 restored'; ok $? 0 "C7 an own entry the page lost is restored from the sent log"
python3 -c "
s=open('$W/rt.md').read(); s=s.replace('## Validation','## Validation\n\n* **2026-10-14** · other-wt · from another worktree\n'); open('$W/other.md','w').write(s)"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/other.md" --outbox "$ST" --out "$W/b5.md" >/dev/null && grep -q 'from another worktree' "$W/b5.md"; ok $? 0 "C8 another writer's entry is kept"
python3 - "$W/b5.md" "$W/b5cut.md" <<'EOF'
import sys
s=open(sys.argv[1]).read(); s=s[:s.index("\n## Plan\n")]; i=s.index("from another worktree"); i=s.rindex("\n",0,i); j=s.index("\n",i+1)
open(sys.argv[2],"w").write(s[:i]+s[j:])
EOF
$T state --repo "$R" --key T-1 --outbox "$ST" --save-body "$W/b5.md" >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b5cut.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "C9 a page with fewer entries than last sent refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b5cut.md" --allow-fewer --outbox "$ST" --out "$W/x.md" >/dev/null; ok $? 0 "C9 accepted with --allow-fewer (a deliberate correction)"
python3 -c "
s=open('$W/b5.md').read(); i=s.index('## Ticket'); j=s.index('## Progress'); s=s[:i]+s[j:]; open('$W/noticket.md','w').write(s[:s.index('\n## Plan\n')])"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/noticket.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "C10 a page that lost its Ticket section refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/noticket.md" --ticket "$W/tk1.md" --outbox "$ST" --out "$W/x.md" >/dev/null; ok $? 0 "C10 accepted with --ticket (rebuilt section)"
python3 -c "import json;json.dump({'body':{'storage':{'value':'<p/>'}}},open('$W/stor.json','w'))"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/stor.json" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "C11 storage (HTML) form refused"
before=$(ls -lR "$ST" | cksum)
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b5.md" --entry Progress test "dry entry" --outbox "$ST" --out "$W/dry.md" >/dev/null && grep -q 'dry entry' "$W/dry.md" && [ "$(ls -lR "$ST" | cksum)" = "$before" ]; ok $? 0 "C12 dry run: --entry rendered, the store unchanged"
V --body "$W/b5.md" --page-id 950 --after-version 3; ok $? 3 "C13 a failed update (not logged): unverified, not a mismatch"
cp "$W/b5.md" "$W/b5bad.md"; echo typo >> "$W/b5bad.md"; fakelog update 950 "$W/b5bad.md" 4
V --body "$W/b5.md" --page-id 950 --after-version 3; ok $? 1 "C13 a transcription error detected"
fakelog update 950 "$W/b5.md" 5
V --body "$W/b5.md" --page-id 950 --after-version 4; ok $? 0 "C13 one retry verified"

echo "== D. plan provenance"
printf '\n## Added later\nnot yet published\n' >> "$R/$P"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --listing "$W/lst3.json" --outbox "$ST" --out "$W/m1.md" >/dev/null && ! grep -q 'Added later' "$W/m1.md" && grep -q "sha256 \`$PH\`" "$W/m1.md"; ok $? 0 "D1 a flush repeats the published copy: an unpublished edit is not sent"
PH2=$(hash "$R/$P")
$T render --repo "$R" --plan $P --meta "$W/meta.json" --local --listing "$W/lst3.json" --outbox "$ST" --out "$W/m2.md" >/dev/null && grep -q 'Added later' "$W/m2.md" && grep -q "sha256 \`$PH2\`" "$W/m2.md" && [ "$PH" != "$PH2" ]; ok $? 0 "D2 publish carries the edit and its new sha256"
cp -r "$ST" "$W/st-tamper"; echo tampered >> "$W/st-tamper/T-1.plan.md"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --local --listing "$W/lst3.json" --outbox "$W/st-tamper" --out "$W/x.md" 2>/dev/null; ok $? 2 "D3 a store copy that doesn't match the published sha256 refused"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b5.md" --outbox "$W/st-empty" --out "$W/x.md" 2>/dev/null; ok $? 2 "D4 --mirrored with no published copy (fresh worktree) refused"
$T render --repo "$R" --plan .claude/work/T-1/nope.md --meta "$W/meta.json" --current "$W/b5.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "D5 --plan naming a missing working copy refused"
$T extract-plan --current "$W/b1.md" --out "$W/rebuilt.md" >/dev/null; ok $? 0 "D6 extract-plan rebuilds the working copy from the page"
grep -q '^# Feature: T-1 demo' "$W/rebuilt.md" && grep -q '^### Detail' "$W/rebuilt.md" && grep -q '^## not a heading inside a fence' "$W/rebuilt.md"; ok $? 0 "D6 headings promoted back, fenced line untouched"
$T extract-plan --current "$W/sk.md" --out "$W/x.md" 2>/dev/null; ok $? 3 "D7 a page with only the placeholder: nothing to rebuild (3)"
$T state --repo "$R" --key T-1 --outbox "$W/st-fresh" --save-plan "$W/rebuilt.md" --plan-title Plan >/dev/null
$T state --repo "$R" --key T-1 --outbox "$W/st-fresh" --set page_id=950 plan_source="page version 5" >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b5.md" --outbox "$W/st-fresh" --out "$W/fr.md" >/dev/null && grep -q 'rebuilt from page version 5' "$W/fr.md" && grep -q 'from another worktree' "$W/fr.md"; ok $? 0 "D8 a fresh worktree flushes with the rebuilt copy; header says so; entries kept"
$T render --repo "$R" --plan .claude/work/issue-7/rca.md --plan-title RCA --meta "$W/meta.json" --current "$W/b5.md" --outbox "$W/st-rca" --out "$W/rca.md" >/dev/null && grep -q '^## RCA$' "$W/rca.md"; ok $? 0 "D9 RCA mirrored under '## RCA'"
$T state --repo "$R" --key T-1 --outbox "$W/st-rca" --set page_id=950 --save-plan "$R/.claude/work/issue-7/rca.md" --plan-title RCA >/dev/null
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/rca.md" --outbox "$W/st-rca" --out "$W/rca2.md" >/dev/null && grep -q '^## RCA$' "$W/rca2.md" && ! grep -q '^## Plan$' "$W/rca2.md"; ok $? 0 "D9 a later flush keeps the recorded title (RCA)"
[ -z "$(git -C "$R" status --porcelain --untracked-files=all)" ]; ok $? 0 "D10 after the lifecycle git status is clean (working copies and store untracked)"
$T render --repo "$R" --mirrored --meta "$W/meta.json" --current "$W/b5.md" --outbox "$W/st-fresh" --out "$W/x.md" >/dev/null 2>"$W/err.txt"; ! grep -q 'WARNING' "$W/err.txt"; ok $? 0 "D11 a small body: no size warning"
python3 -c "print('# Big plan\n\n' + 'filler line for the size warning test\n' * 900)" > "$R/.claude/work/T-1/big.md"
$T render --repo "$R" --plan .claude/work/T-1/big.md --meta "$W/meta.json" --current "$W/b5.md" --outbox "$W/st-big" --out "$W/big.md" >/dev/null 2>"$W/err.txt"; ok $? 0 "D11 a body over 25 KB still renders"
grep -q 'WARNING: the body is [0-9]* KB (over 25 KB)' "$W/err.txt"; ok $? 0 "D11 ... with a size warning on stderr"

echo "== E. sanitising and secrets"
printf 'x%.0s' $(seq 1 1600) | $T sanitize --repo "$R" >/dev/null 2>&1; ok $? 1 "E1 the 1500-char cap (Jira fallback)"
printf 'report /gpfs/u/someone/r.md, /global/homes/s/someone/x, /g/g19/someone/y, /usr/workspace/someone/z, %s/a\n' "$HOME" | $T sanitize --repo "$R" > "$W/fb.txt" && ! grep -qE "someone|$HOME" "$W/fb.txt" && grep -q '{home}/a' "$W/fb.txt"; ok $? 0 "E2 cluster and home paths masked"
printf 'the /p option and /data are words\n' | $T sanitize --repo "$R" | grep -q 'the /p option and /data are words'; ok $? 0 "E3 lone short roots are left as text"
$T queue --repo "$R" --key T-1 --outbox "$ST" --add Progress x "token=ghp_abcdefghijklmnopqrstuvwxyz0123456789" 2>"$W/err.txt"; ok $?,$(grep -c ghp_abc "$W/err.txt"),$(grep -c github-token "$W/err.txt") 1,0,1 "E4 a secret-like entry refused, naming the kind, never the secret"

echo "== F. outbox and the epic Progress page"
$T queue --repo "$R" --key T-1 --outbox "$ST" --add Validation validate "Overall: READY" >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$ST" --list | grep -q 'Overall: READY' && $T queue --repo "$R" --key T-1 --outbox "$ST" --mark-sent >/dev/null && [ -z "$($T queue --repo "$R" --key T-1 --outbox "$ST" --list)" ]; ok $? 0 "F1 queued entries are listed; mark-sent empties the queue"
grep -q 'Overall: READY' "$ST/T-1.sent.jsonl"; ok $? 0 "F1 the sent log keeps the entry"
meta
$T progress --new --meta "$W/meta.json" --repo "$R" --out "$W/pg.md" >/dev/null && grep -q '^## Entries$' "$W/pg.md"; ok $? 0 "F2 Progress page skeleton"
$T queue --repo "$R" --key T-1 --outbox "$ST" --epic --add - execute "execute done: tasks 1-3" >/dev/null
$T queue --repo "$R" --key T-1 --outbox "$ST" --epic --add - loop "implementation approved, round 1" >/dev/null
[ -z "$($T queue --repo "$R" --key T-1 --outbox "$ST" --list)" ]; ok $? 0 "F3 epic lines are kept apart from the ticket queue"
$T progress --repo "$R" --key T-1 --current "$W/pg.md" --outbox "$ST" --out "$W/pg2.md" >/dev/null && grep -q 'T-1 execute · execute done' "$W/pg2.md" && grep -q 'T-1 loop · implementation approved' "$W/pg2.md"; ok $? 0 "F3 two lines appended, each naming the ticket and the caller"
$T queue --repo "$R" --key T-1 --outbox "$ST" --epic --mark-sent >/dev/null
sed -e 's/^- /* /' "$W/pg2.md" > "$W/pg-rt.md"
$T progress --repo "$R" --key T-1 --current "$W/pg-rt.md" --outbox "$ST" --out "$W/pg3.md" | grep -q ' 0 added'; ok $? 0 "F4 after a round trip: no duplicates"
grep -v 'execute done' "$W/pg-rt.md" > "$W/pg-lost.md"
$T progress --repo "$R" --key T-1 --current "$W/pg-lost.md" --outbox "$ST" --out "$W/pg4.md" | grep -q ' 1 added'; ok $? 0 "F4 an own line the page lost is restored from the epic sent log"
grep -v '^## Entries' "$W/pg2.md" > "$W/pg-bad.md"
$T progress --repo "$R" --key T-1 --current "$W/pg-bad.md" --outbox "$ST" --out "$W/x.md" 2>/dev/null; ok $? 2 "F5 a page without its Entries heading refused"

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
