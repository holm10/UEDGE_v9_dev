#!/usr/bin/env bash
# Test of ticket_page.py (the ticket-page skill's helper), offline: a bare repo stands in for the tracker's remote, a
# clone for its checkout, a throwaway repo for the UEDGE checkout (tracker.toml only in its main checkout), and a fake
# `gh` first on PATH logs every call with the tracker's commit count at that moment and answers the issue query from
# canned JSON. One case per guarantee: (A) one record per ticket, under its epic; (B) publish: provenance, masking,
# secrets, GitHub only after the commit; (C) append-only log, multi-line and hostile text; (D) status and the
# Project/issue side; (E) the epic progress log; (F) a failed push loses nothing; (G) concurrent writers, parallel
# calls, a rebase conflict, a dirty checkout, the wrong branch; (H) retired subcommands, Jira keys and sanitize;
# (K) a GitHub rate limit is waited out (K7-K9 and K11 tested jira_import.py, retired in T165); (I) the tracker is not
# hard-coded.
# Usage: .claude/skills/ticket-page/selftest.sh [workdir]   (default: a new temporary directory). Exit 0 = all passed.
set -u
H="$(cd "$(dirname "$0")" && pwd)/ticket_page.py"; W="${1:-$(mktemp -d)}"; mkdir -p "$W"; cd "$W" || exit 2
echo "workdir: $W"; PASS=0; FAIL=0
ok(){ if [ "$1" = "$2" ]; then PASS=$((PASS+1)); echo "PASS $3"; else FAIL=$((FAIL+1)); echo "FAIL $3 (got $1, want $2)"; fi; }
g(){ git -c user.email=t@t -c user.name=t "$@"; }
TR="$W/tracker"; U="$W/uedge"

# The fake gh: logs "<tracker commit count> <argv>", answers the issue query by number and the Project calls.
mkdir -p "$W/bin" "$W/gh"
cat > "$W/bin/gh" <<'EOF'
#!/usr/bin/env bash
echo "$(git -C "$GH_TRACKER" rev-list --count HEAD) $*" >> "$GH_LOG"
case "$1 $2" in
  "api graphql") for x in "$@"; do case "$x" in n=*) cat "$GH_DIR/issue-${x#n=}.json";; esac; done ;;
  "project field-list") # section K: $GH_DIR/fail holds one error to answer once (a rate limit or another failure)
    if [ -f "$GH_DIR/fail" ]; then cat "$GH_DIR/fail" >&2; rm -f "$GH_DIR/fail"; exit 1; fi
    if [ -f "$GH_DIR/failall" ]; then cat "$GH_DIR/failall" >&2; exit 1; fi   # answered on every call
    cat "$GH_DIR/fields.json" ;;
  "api rate_limit") # the answer after the caller's --jq: one "remaining reset" line each for graphql and core
    if [ -f "$GH_DIR/rl" ]; then cat "$GH_DIR/rl"; else echo "0 $(date +%s)"; echo "5000 $(date +%s)"; fi ;;
  "project view") echo '{"id":"PVT_test"}' ;;
esac
EOF
chmod +x "$W/bin/gh"
cat > "$W/gh/issue-2.json" <<'EOF'
{"data":{"repository":{"issue":{"title":"Port the thing","body":"## Scope\n\nDo it in /Users/someone/x.\n\n```sh\n# a comment, not a heading\n```\n","issueType":{"name":"Task"},"parent":{"number":1,"title":"Epic one"},"projectItems":{"nodes":[{"id":"ITEM2","project":{"number":7},"tier":{"name":"M"}}]}}}}}
EOF
cat > "$W/gh/issue-9.json" <<'EOF'
{"data":{"repository":{"issue":{"title":"Loose end in /Users/someone/y","body":"Small.","issueType":{"name":"Bug"},"parent":null,"projectItems":{"nodes":[]}}}}}
EOF
cat > "$W/gh/issue-3.json" <<'EOF'
{"data":{"repository":{"issue":{"title":"Quotes a record","body":"A pasted record:\n\n```\n## Progress\n- old\n```\n\nAnd an unclosed one:\n\n````md\n## Reviews\n","issueType":{"name":"Task"},"parent":{"number":1,"title":"Epic one"},"projectItems":{"nodes":[]}}}}}
EOF
echo '{"fields":[{"id":"F_STATUS","name":"Status","options":[{"id":"O_TODO","name":"To Do"},{"id":"O_PROG","name":"In Progress"},{"id":"O_REV","name":"In Review"},{"id":"O_DONE","name":"Done"}]},{"id":"F_TIER","name":"Tier","options":[{"id":"O_S","name":"S"},{"id":"O_M","name":"M"},{"id":"O_L","name":"L"}]},{"id":"F_JIRA","name":"Jira key"}]}' > "$W/gh/fields.json"
export GH_LOG="$W/gh.log" GH_DIR="$W/gh" GH_TRACKER="$TR" PATH="$W/bin:$PATH" TICKET_PAGE_MAX_WAIT=0

# The tracker: a bare remote and a checkout with one epic directory. tracker.toml exists only in the main checkout.
git init -q --bare -b main "$W/remote.git"; git clone -q "$W/remote.git" "$TR" 2>/dev/null
mkdir -p "$TR/docs/T1-epic-one"; echo "# T1: progress" > "$TR/docs/T1-epic-one/progress.md"; echo r > "$TR/README.md"
g -C "$TR" add -A; g -C "$TR" commit -qm seed; git -C "$TR" push -q origin HEAD:main 2>/dev/null
git -C "$TR" branch -q -u origin/main 2>/dev/null
git init -q "$U"; echo x > "$U/x"; g -C "$U" add -A; g -C "$U" commit -qm base
mkdir -p "$U/.claude"; printf '[tracker]\nowner = "acme"\nrepo = "tracker"\nproject = 7\n' > "$U/.claude/tracker.toml"
git -C "$U" worktree add -q -b wt "$W/wt"; mkdir -p "$W/wt/.claude/work/T2"
T(){ uv run -q "$H" --repo "$W/wt" --tracker-dir "$TR" --date 2026-01-02 --caller selftest "$@"; }
REC="$TR/docs/T1-epic-one/T2-port-the-thing/record.md"
heads(){ git -C "$TR" rev-list --count HEAD; }
section(){ awk -v s="## $1" '$0==s{f=1;next} /^## /{f=0} f' "$REC"; }

echo "== A. create: one record per ticket"
[ ! -e "$W/wt/.claude/tracker.toml" ]; ok $? 0 "A0 setup: the worktree has no tracker.toml"
T create T2 >/dev/null; ok $? 0 "A1 create from a worktree (tracker.toml read through the main checkout)"
[ -f "$REC" ]; ok $? 0 "A1 the record sits under its epic's directory"
grep -q '^### Scope$' "$REC" && grep -q '^# a comment, not a heading$' "$REC" && ! grep -q '/Users/someone' "$REC"; ok $? 0 "A1 Ticket from the issue: headings demoted outside fences only, paths masked"
grep -q '^| Type / tier | Task / M |$' "$REC" && grep -q '^| Status | Planned |$' "$REC"; ok $? 0 "A1 header: type, tier, status"
n=$(heads); T create T2 | grep -q 'record exists'; ok $? 0 "A2 a second create reuses the record"
[ "$(heads)" = "$n" ]; ok $? 0 "A2 and commits nothing"
T create T9 >/dev/null; R9=$(ls "$TR"/docs/no-epic/T9-*/record.md); ok $? 0 "A3 no parent: docs/no-epic/"
! grep -q '/Users/someone' "$R9"; ok $? 0 "A3 the title is masked too"
mkdir -p "$TR/docs/T5-x/T9-dup"; cp "$R9" "$TR/docs/T5-x/T9-dup/"
T log T9 Progress x 2>"$W/err"; ok $? 2 "A4 two records for one key: refused"
grep -q 'has 2 records' "$W/err"; ok $? 0 "A4 the message names both"
rm -rf "$TR/docs/T5-x"
T create T3 >/dev/null && T log T3 Reviews "rv-3" >/dev/null; ok $? 0 "A5 an issue body quoting record headings in fences (one unclosed)"
R3=$(ls "$TR"/docs/T1-epic-one/T3-*/record.md); last(){ grep -n "^## $1\$" "$R3" | tail -1 | cut -d: -f1; }
[ "$(grep -n 'record created' "$R3" | cut -d: -f1)" -gt "$(last Progress)" ] && [ "$(grep -n 'rv-3' "$R3" | cut -d: -f1)" -gt "$(last Reviews)" ]; ok $? 0 "A5 entries land in the record's own sections, not in the quoted ones"
# T50: the epic's rules block. Epic T4's breakdown has one; T11's body lacks it, T12's carries it. Epic T6's breakdown
# has the heading only inside a code fence (T13).
mkdir -p "$TR/docs/T4-epic-four" "$TR/docs/T6-epic-six"
printf '# T4: breakdown\n\n## Epic summary\n\nx\n\n## Rules every ticket of T4 carries\n\n- Rule one: ask the owner.\n- Rule two: no tolerance edits.\n\n## T11: first\n\n- Issue: #11\n' > "$TR/docs/T4-epic-four/breakdown.md"
printf '# T6: breakdown\n\n```md\n## Rules every ticket of T6 carries\n\n- fenced, not a rule\n```\n\n## T13: x\n' > "$TR/docs/T6-epic-six/breakdown.md"
g -C "$TR" add -A; g -C "$TR" commit -qm rules; git -C "$TR" push -q 2>/dev/null
for i in 11 12 13; do case $i in
  11) p='{"number":4,"title":"Epic four"}'; b='## Scope\n\nA follow-up.\n' ;;
  12) p='{"number":4,"title":"Epic four"}'; b='## Scope\n\nFiled by spec.\n\n## Rules every ticket of T4 carries\n\n- Rule one: ask the owner.\n- Rule two: no tolerance edits.\n' ;;
  13) p='{"number":6,"title":"Epic six"}'; b='## Scope\n\nC.\n' ;; esac
  printf '{"data":{"repository":{"issue":{"title":"Rules %s","body":"%s","issueType":{"name":"Task"},"parent":%s,"projectItems":{"nodes":[]}}}}}\n' "$i" "$b" "$p" > "$W/gh/issue-$i.json"
done
T create T11 >/dev/null; R11=$(ls "$TR"/docs/T4-epic-four/T11-*/record.md)
[ "$(grep -c '^### Rules every ticket of T4 carries$' "$R11")" = 1 ] && grep -q "^_Added from the epic's breakdown.md on 2026-01-02; not part of the issue as filed._\$" "$R11" && grep -q '^- Rule two: no tolerance edits.$' "$R11"; ok $? 0 "A6 a body without the epic's rules gets them, marked as added"
[ "$(grep -n 'Rule two' "$R11" | cut -d: -f1)" -lt "$(grep -n '^Source: issue #11' "$R11" | cut -d: -f1)" ]; ok $? 0 "A6 inside the Ticket section, before its Source line"
T create T12 >/dev/null; R12=$(ls "$TR"/docs/T4-epic-four/T12-*/record.md)
[ "$(grep -c 'Rules every ticket of T4 carries' "$R12")" = 1 ] && ! grep -q '^_Added from' "$R12"; ok $? 0 "A7 a body that carries the rules: not added twice"
! grep -q '^_Added from' "$REC"; ok $? 0 "A8 an epic without a breakdown: nothing added"
T create T13 >/dev/null; R13=$(ls "$TR"/docs/T6-epic-six/T13-*/record.md)
! grep -q '^_Added from' "$R13" && ! grep -q 'fenced, not a rule' "$R13"; ok $? 0 "A9 a rules heading inside a code fence is not a section"

echo "== B. publish"
printf '# Plan\n\nRun in /Users/someone/work/repo.\n' > "$W/wt/.claude/work/T2/plan.md"
: > "$GH_LOG"; T publish T2 >/dev/null; ok $? 0 "B1 publish (default file .claude/work/T2/plan.md)"
P="$(dirname "$REC")/plan.md"; [ -f "$P" ] && ! grep -q '/Users/someone' "$P"; ok $? 0 "B1 plan.md written, local paths masked"
grep -q "^| Plan | \`plan.md\`, published 2026-01-02, sha256 $(shasum -a 256 "$P" | cut -c1-12) |$" "$REC"; ok $? 0 "B1 header cites the date and the published file's sha256"
grep -q " issue comment 2 -R acme/tracker" "$GH_LOG" && [ "$(grep -v ' api graphql' "$GH_LOG" | cut -d' ' -f1 | sort -u)" = "$(heads)" ]; ok $? 0 "B1 the issue comment, and every GitHub write, after the commit"
n=$(heads); echo 'token = abcdefghijkl123' > "$W/s.md"; : > "$GH_LOG"; T publish T2 --plan "$W/s.md" 2>/dev/null; ok $? 1 "B2 a secret-like string: refused"
[ "$(heads)" = "$n" ] && [ ! -s "$GH_LOG" ]; ok $? 0 "B2 nothing committed, nothing sent"
T publish T2 --plan "$W/missing.md" 2>"$W/err"; ok $? 2 "B3 a missing file: exit 2"
! grep -q Traceback "$W/err"; ok $? 0 "B3 with a message, not a traceback"

echo "== C. log"
T log T2 Reviews "round 1 APPROVE" >/dev/null; T log T2 Reviews "round 2 APPROVE" >/dev/null
[ "$(section Reviews | grep -c '^- 2026-01-02 (selftest): round')" = 2 ]; ok $? 0 "C1 both entries in Reviews, in order, earlier kept"
T log T2 Validation "fail log:"$'\n'"## Reviews"$'\n'"a \\d \\1 line" >/dev/null; ok $? 0 "C2 multi-line text with a heading and backslashes"
[ "$(grep -c '^## ' "$REC")" = 5 ] && section Validation | grep -q '^  ## Reviews$'; ok $? 0 "C2 fenced under the entry, no new section"
T log T2 Reviews "round 3" >/dev/null; section Reviews | grep -q 'round 3'; ok $? 0 "C2 the next Reviews entry still lands in Reviews"
T log T2 Progress "built in /Users/someone/b" >/dev/null; ! grep -q '/Users/someone/b' "$REC"; ok $? 0 "C3 log text is masked"
n=$(heads); T log T2 Progress 'password = hunter2hunter2' 2>/dev/null; ok $? 1 "C4 a secret in log text: refused"
[ "$(heads)" = "$n" ]; ok $? 0 "C4 nothing committed"
T log T2 Notes x 2>/dev/null; ok $? 2 "C5 an unknown section: refused"

echo "== D. status"
: > "$GH_LOG"; uv run -q "$H" --repo "$W/wt" --tracker-dir "$TR" --date 2026-01-03 status T2 Executing >/dev/null; ok $? 0 "D1 status Executing"
grep -q '^| Status | Executing |$' "$REC" && grep -q '^| Last update | 2026-01-03 |$' "$REC"; ok $? 0 "D1 header status and Last update"
grep -q "^$(heads) project item-edit --id ITEM2 --project-id PVT_test --field-id F_STATUS --single-select-option-id O_PROG" "$GH_LOG"; ok $? 0 "D1 Project Status In Progress, after the commit"
T status T2 Validating "a | b"$'\n'"c \\1" >/dev/null; ok $? 0 "D2 a note with a pipe, a newline and a backslash"
grep -q '^| Status | Validating (a \\| b c \\1) |$' "$REC"; ok $? 0 "D2 the header row stays one row"
T status T2 Committed abc1234 >/dev/null; grep -q " issue close 2 -R acme/tracker --reason completed" "$GH_LOG"; ok $? 0 "D3 Committed closes the issue"
grep -q 'O_DONE' "$GH_LOG"; ok $? 0 "D3 Project Status Done"
T status T2 Finished 2>/dev/null; ok $? 2 "D4 an unknown status: refused"

echo "== E. progress"
T progress T2 "merged" >/dev/null; grep -q '^- 2026-01-02 T2 (selftest): merged$' "$TR/docs/T1-epic-one/progress.md"; ok $? 0 "E1 a line in the epic's progress.md"
T progress T9 x | grep -q 'no epic'; ok $? 0 "E2 no epic: said, exit 0"

echo "== F. a failed push loses nothing"
git -C "$TR" remote set-url origin "$W/nowhere.git"
T log T2 Progress "offline entry" >"$W/out"; ok $? 0 "F1 remote unreachable: exit 0"
grep -q 'fetch failed' "$W/out" && grep -q 'push failed' "$W/out"; ok $? 0 "F1 both failures reported"
git -C "$TR" log -1 --format=%s | grep -q 'T2 log: Progress'; ok $? 0 "F1 the commit is in the tracker checkout"
git -C "$TR" remote set-url origin "$W/remote.git"
T log T2 Progress "back online" >/dev/null; git -C "$TR" fetch -q
[ "$(git -C "$TR" log origin/main --format=%s | grep -c 'T2 log: Progress')" -ge 2 ] && git -C "$TR" status -sb | grep -qv ahead; ok $? 0 "F2 the next call pushes both"

echo "== G. concurrent writers"
git clone -q "$W/remote.git" "$W/other" 2>/dev/null
printf -- '- 2026-01-02 (other): from another session\n' >> "$W/other/docs/T1-epic-one/T2-port-the-thing/record.md"
g -C "$W/other" commit -qam other; git -C "$W/other" push -q 2>/dev/null
T log T2 Validation "mine" >/dev/null; ok $? 0 "G1 log after another session pushed"
grep -q 'from another session' "$REC" && grep -q '(selftest): mine' "$REC"; ok $? 0 "G1 both entries kept"
n=$(heads); for i in 1 2 3 4; do T log T2 Progress "par-$i" >"$W/par$i" 2>&1 & done; wait
[ "$(heads)" = $((n + 4)) ] && [ "$(grep -c '(selftest): par-' "$REC")" = 4 ]; ok $? 0 "G2 four parallel calls: four commits, four entries"
[ "$(git -C "$TR" log -4 --format=%H | while read c; do git -C "$TR" show "$c" | grep -c '^+- .*par-'; done | sort -u)" = 1 ]; ok $? 0 "G2 one entry per commit"
git -C "$W/other" pull -q --rebase 2>/dev/null
printf 'conflict\n' > "$W/other/docs/T1-epic-one/progress.md"; g -C "$W/other" commit -qam c1; git -C "$W/other" push -q 2>/dev/null; ok $? 0 "G3 setup: the other session's change is on the remote"
printf 'mine\n' > "$TR/docs/T1-epic-one/progress.md"; g -C "$TR" commit -qam c2
n=$(heads); T log T2 Progress x 2>"$W/err"; ok $? 2 "G3 a conflicting rebase: refused"
grep -q 'nothing written' "$W/err" && [ "$(heads)" = "$n" ] && [ ! -d "$TR/.git/rebase-merge" ]; ok $? 0 "G3 no new commit, rebase aborted"
git -C "$TR" reset -q --hard origin/main
echo x >> "$TR/README.md"; git -C "$TR" add README.md; n=$(heads)
T log T2 Progress x 2>"$W/err"; ok $? 2 "G4 a dirty tracker checkout: refused"
grep -q 'uncommitted changes' "$W/err" && [ "$(heads)" = "$n" ]; ok $? 0 "G4 says so, nothing committed (the staged file not swept in)"
git -C "$TR" reset -q --hard origin/main; git -C "$TR" checkout -q -b side
T log T2 Progress x 2>"$W/err"; ok $? 2 "G5 the checkout on another branch: refused"
grep -q "is on 'side', not 'main'" "$W/err"; ok $? 0 "G5 the message names both branches"
git -C "$TR" checkout -q main

echo "== H. retired subcommands, Jira keys, sanitize"
for v in flush queue state; do uv run -q "$H" $v 2>/dev/null; ok $? 2 "H1 $v (a retired no-op, T165): exit 2"; done
uv run -q "$H" find --key T2 2>"$W/err"; ok $? 2 "H2 a retired subcommand: exit 2"
grep -q retired "$W/err"; ok $? 0 "H2 says it was retired"
uv run -q "$H" progress --new --meta m.json 2>"$W/err"; grep -q retired "$W/err"; ok $? 0 "H2 progress --new: retired too"
T log AIUE-1 Progress x 2>/dev/null; ok $? 2 "H3 a Jira key: refused"
printf 'see /Users/someone/z\n' | uv run -q "$H" sanitize --repo "$W/wt" --max-chars 100 | grep -q '{local}/z'; ok $? 0 "H4 sanitize --repo --max-chars (rca's call)"
printf '%0200d\n' 0 | uv run -q "$H" sanitize --repo "$W/wt" --max-chars 100 >/dev/null 2>&1; ok $? 1 "H4 over the cap: refused"

echo "== K. a GitHub rate limit is waited out (tracker #28)"
KS(){ : > "$GH_LOG"; T status T2 Executing 2>"$W/err" >/dev/null; }  # T2 is on the Project (ITEM2)
echo "GraphQL: API rate limit already exceeded for user ID 1." > "$GH_DIR/fail"; KS; e=$?
ok "$e:$(grep -c 'project field-list' "$GH_LOG"):$(grep -c 'api rate_limit' "$GH_LOG"):$(grep -c 'GitHub rate limit; waiting 0 s (computed' "$W/err")" "0:2:1:1" "K1 a primary rate limit: reset read, waited, retried once"
echo "You have exceeded a secondary rate limit. Please wait." > "$GH_DIR/fail"; KS; e=$?
ok "$e:$(grep -c 'project field-list' "$GH_LOG"):$(grep -c 'api rate_limit' "$GH_LOG")" "0:2:0" "K2 a secondary rate limit: waited and retried, no reset query"
echo "HTTP 404: Not Found (https://api.github.com/graphql)" > "$GH_DIR/fail"; KS; e=$?
ok "$e:$(grep -c 'project field-list' "$GH_LOG"):$(grep -c 'api rate_limit' "$GH_LOG")" "2:1:0" "K3 any other failure: no retry, exit 2"
grep -q 'gh project field-list failed: HTTP 404' "$W/err"; ok $? 0 "K3 the message names the call and the error"
# the bound: a limit on every call is retried 4 times, the 5th failure is fatal and names the call
echo "GraphQL: API rate limit already exceeded for user ID 1." > "$GH_DIR/failall"; KS; e=$?
ok "$e:$(grep -c 'project field-list' "$GH_LOG"):$(grep -c 'GitHub rate limit; waiting' "$W/err")" "2:5:4" "K4 a persistent rate limit: 5 attempts, 4 waits, exit 2"
grep -q 'gh project field-list failed: GraphQL: API rate limit' "$W/err"; ok $? 0 "K4 the final message names the call"
# a secondary limit waits 60 s x retry (the line shows the wait before TICKET_PAGE_MAX_WAIT caps it)
echo "You have exceeded a secondary rate limit. Please wait." > "$GH_DIR/failall"; KS
ok "$(grep -o 'computed [0-9]* s, retry [0-9]/4' "$W/err" | sed 's/ s, retry / \//; s/computed //' | tr '\n' ' ')" "60 /1/4 120 /2/4 180 /3/4 240 /4/4 " "K5 a secondary limit: 60 s per retry"
# a primary limit waits until the reset (+5 s) of the exhausted resource: graphql, core, the later of both, or 120 s x retry with neither at zero
echo "GraphQL: API rate limit already exceeded for user ID 1." > "$GH_DIR/failall"
w1(){ now=$(date +%s); printf '%s %s\n%s %s\n' "$1" $((now + $2)) "$3" $((now + $4)) > "$GH_DIR/rl"; KS  # remaining, reset offset: graphql, core
  grep -o 'computed [0-9]* s, retry 1/4' "$W/err" | sed 's/computed \([0-9]*\) s.*/\1/'; }
w=$(w1 0 100 5000 500); [ "$w" -ge 104 ] && [ "$w" -le 105 ]; ok $? 0 "K6 graphql exhausted: its reset + 5 s ($w s)"
w=$(w1 5000 500 0 100); [ "$w" -ge 104 ] && [ "$w" -le 105 ]; ok $? 0 "K6 only core exhausted: the core reset, not the later graphql one ($w s)"
w=$(w1 0 100 0 200); [ "$w" -ge 204 ] && [ "$w" -le 205 ]; ok $? 0 "K6 both exhausted: the later reset ($w s)"
w=$(w1 10 100 10 200); ok "$w" 120 "K6 neither exhausted (a burst limit rate_limit does not show): 120 s on retry 1"
grep -o 'computed [0-9]* s, retry [0-9]/4' "$W/err" | tr '\n' ' ' | grep -q 'computed 120 s, retry 1/4 computed 240 s, retry 2/4 computed 360 s, retry 3/4 computed 480 s, retry 4/4'; ok $? 0 "K6 and 120 s more on each retry"
rm -f "$GH_DIR/failall" "$GH_DIR/rl"
# `gh project` reports a rate-limited owner lookup as "unknown owner type": waited out like a rate limit
echo "unknown owner type" > "$GH_DIR/fail"; KS; e=$?
ok "$e:$(grep -c 'project field-list' "$GH_LOG"):$(grep -c 'GitHub rate limit; waiting' "$W/err")" "0:2:1" "K10 'unknown owner type': waited and retried"

echo "== I. no hard-coded tracker"
! grep -n 'uedge-sandbox\|uedge-tracker\|holm10\|atlassian.net' "$H"; ok $? 0 "I1 the helper names no owner, repo or Jira site"

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
