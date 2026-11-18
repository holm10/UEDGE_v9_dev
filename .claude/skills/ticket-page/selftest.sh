#!/usr/bin/env bash
# Test of ticket_page.py (the ticket-page skill's helper), offline: a bare repo stands in for the tracker's remote, a
# clone for its checkout, a throwaway repo for the UEDGE checkout (with .claude/tracker.toml), and a fake `gh` first on
# PATH logs every call and answers the issue query from canned JSON. One case per guarantee: (A) one record per
# ticket, placed under its epic; (B) publish: provenance, sanitising, secrets refused; (C) append-only log; (D) status
# and the Project/issue side; (E) the epic progress log; (F) a failed push loses nothing; (G) concurrent writers;
# (H) compatibility no-ops and retired subcommands; (I) the tracker is not hard-coded.
# Usage: .claude/skills/ticket-page/selftest.sh [workdir]   (default: a new temporary directory). Exit 0 = all passed.
set -u
H="$(cd "$(dirname "$0")" && pwd)/ticket_page.py"; W="${1:-$(mktemp -d)}"; mkdir -p "$W"; cd "$W" || exit 2
echo "workdir: $W"; PASS=0; FAIL=0
ok(){ if [ "$1" = "$2" ]; then PASS=$((PASS+1)); echo "PASS $3"; else FAIL=$((FAIL+1)); echo "FAIL $3 (got $1, want $2)"; fi; }
g(){ git -c user.email=t@t -c user.name=t "$@"; }

# The fake gh: logs argv, answers the issue query by number and the Project calls with canned JSON.
mkdir -p "$W/bin" "$W/gh"
cat > "$W/bin/gh" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> "$GH_LOG"
case "$1 $2" in
  "api graphql") for x in "$@"; do case "$x" in n=*) cat "$GH_DIR/issue-${x#n=}.json";; esac; done ;;
  "project field-list") cat "$GH_DIR/fields.json" ;;
  "project view") echo '{"id":"PVT_test"}' ;;
esac
EOF
chmod +x "$W/bin/gh"
cat > "$W/gh/issue-2.json" <<'EOF'
{"data":{"repository":{"issue":{"title":"Port the thing","body":"## Scope\n\nDo it in /Users/someone/x.\n","issueType":{"name":"Task"},"parent":{"number":1,"title":"Epic one"},"projectItems":{"nodes":[{"id":"ITEM2","project":{"number":7},"tier":{"name":"M"}}]}}}}}
EOF
cat > "$W/gh/issue-9.json" <<'EOF'
{"data":{"repository":{"issue":{"title":"Loose end","body":"Small.","issueType":{"name":"Bug"},"parent":null,"projectItems":{"nodes":[]}}}}}
EOF
echo '{"fields":[{"id":"F_STATUS","name":"Status","options":[{"id":"O_TODO","name":"To Do"},{"id":"O_PROG","name":"In Progress"},{"id":"O_REV","name":"In Review"},{"id":"O_DONE","name":"Done"}]}]}' > "$W/gh/fields.json"
export GH_LOG="$W/gh.log" GH_DIR="$W/gh" PATH="$W/bin:$PATH"

# The tracker: a bare remote and a checkout with one epic directory; the UEDGE checkout names it in tracker.toml.
TR="$W/tracker"; U="$W/uedge"
git init -q --bare -b main "$W/remote.git"; git clone -q "$W/remote.git" "$TR" 2>/dev/null
mkdir -p "$TR/docs/T1-epic-one"; echo "# T1: progress" > "$TR/docs/T1-epic-one/progress.md"; echo r > "$TR/README.md"
g -C "$TR" add -A; g -C "$TR" commit -qm seed; git -C "$TR" push -q origin HEAD:main 2>/dev/null
git -C "$TR" branch -q -u origin/main 2>/dev/null
git init -q "$U"; mkdir -p "$U/.claude/work/T2"; printf '[tracker]\nowner = "acme"\nrepo = "tracker"\nproject = 7\n' > "$U/.claude/tracker.toml"
echo x > "$U/x"; g -C "$U" add -A; g -C "$U" commit -qm base; git -C "$U" worktree add -q -b wt "$W/wt"; mkdir -p "$W/wt/.claude/work/T2"
T(){ uv run -q "$H" --repo "$W/wt" --tracker-dir "$TR" --date 2026-01-02 --caller selftest "$@"; }
REC="$TR/docs/T1-epic-one/T2-port-the-thing/record.md"
heads(){ git -C "$TR" rev-list --count HEAD; }

echo "== A. create: one record per ticket"
T create T2 >/dev/null; ok $? 0 "A1 create exits 0 (from a worktree: tracker.toml read through the main checkout)"
[ -f "$REC" ]; ok $? 0 "A1 the record sits under its epic's directory"
grep -q '^### Scope$' "$REC" && grep -q '{home}/x\|{local}/x' "$REC" && ! grep -q '/Users/someone' "$REC"; ok $? 0 "A1 Ticket section from the issue, headings demoted, paths masked"
grep -q '^| Type / tier | Task / M |$' "$REC" && grep -q '^| Status | Planned |$' "$REC"; ok $? 0 "A1 header: type, tier, status"
n=$(heads); T create T2 | grep -q 'record exists'; ok $? 0 "A2 a second create reuses the record"
[ "$(heads)" = "$n" ]; ok $? 0 "A2 and commits nothing"
T create T9 >/dev/null; [ -f "$TR/docs/no-epic/T9-loose-end/record.md" ]; ok $? 0 "A3 no parent: docs/no-epic/"
mkdir -p "$TR/docs/T5-x/T9-dup"; cp "$TR/docs/no-epic/T9-loose-end/record.md" "$TR/docs/T5-x/T9-dup/"
T log T9 Progress x 2>"$W/err"; ok $? 2 "A4 two records for one key: refused"
grep -q 'has 2 records' "$W/err"; ok $? 0 "A4 the message names both"
rm -rf "$TR/docs/T5-x"

echo "== B. publish"
printf '# Plan\n\nRun in /Users/someone/work/repo.\n' > "$W/wt/.claude/work/T2/plan.md"
T publish T2 >/dev/null; ok $? 0 "B1 publish (default file .claude/work/T2/plan.md)"
P="$(dirname "$REC")/plan.md"; [ -f "$P" ] && ! grep -q '/Users/someone' "$P"; ok $? 0 "B1 plan.md written, local paths masked"
grep -q "^| Plan | \`plan.md\`, published 2026-01-02, sha256 $(shasum -a 256 "$W/wt/.claude/work/T2/plan.md" | cut -c1-12) |$" "$REC"; ok $? 0 "B1 header cites date and sha256"
grep -q '^issue comment 2 -R acme/tracker' "$GH_LOG"; ok $? 0 "B1 a comment on the issue"
n=$(heads); echo 'token = abcdefghijkl123' > "$W/s.md"; T publish T2 --plan "$W/s.md" 2>/dev/null; ok $? 1 "B2 a secret-like string: refused"
[ "$(heads)" = "$n" ]; ok $? 0 "B2 nothing committed"

echo "== C. log"
T log T2 Reviews "round 1 APPROVE" >/dev/null; T log T2 Reviews "round 2 APPROVE" >/dev/null
awk '/^## Reviews/{f=1;next} /^## /{f=0} f' "$REC" | grep -c '^- 2026-01-02 (selftest): round' | grep -qx 2; ok $? 0 "C1 both entries in Reviews, in order, earlier kept"
grep -q '^## Findings and decisions$' "$REC" && [ "$(grep -c '^## ' "$REC")" = 5 ]; ok $? 0 "C1 the five sections intact"
T log T2 Notes x 2>/dev/null; ok $? 2 "C2 an unknown section: refused"

echo "== D. status"
: > "$GH_LOG"; T status T2 Executing >/dev/null; ok $? 0 "D1 status Executing"
grep -q '^| Status | Executing |$' "$REC"; ok $? 0 "D1 header status"
grep -q 'project item-edit --id ITEM2 --project-id PVT_test --field-id F_STATUS --single-select-option-id O_PROG' "$GH_LOG"; ok $? 0 "D1 Project Status In Progress"
T status T2 Committed abc1234 >/dev/null; grep -q '^issue close 2 -R acme/tracker --reason completed' "$GH_LOG"; ok $? 0 "D2 Committed closes the issue"
grep -q 'O_DONE' "$GH_LOG"; ok $? 0 "D2 Project Status Done"
T status T2 Finished 2>/dev/null; ok $? 2 "D3 an unknown status: refused"

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
git -C "$TR" log origin/main --format=%s | grep -c 'T2 log: Progress' | grep -qx 2; ok $? 0 "F2 the next call pushes both"

echo "== G. concurrent writers"
git clone -q "$W/remote.git" "$W/other" 2>/dev/null
printf -- '- 2026-01-02 (other): from another session\n' >> "$W/other/docs/T1-epic-one/T2-port-the-thing/record.md"
g -C "$W/other" commit -qam other; git -C "$W/other" push -q 2>/dev/null
T log T2 Validation "mine" >/dev/null; ok $? 0 "G1 log after another session pushed"
grep -q 'from another session' "$REC" && grep -q '(selftest): mine' "$REC"; ok $? 0 "G1 both entries kept"

echo "== G2. a rebase conflict writes nothing"
git -C "$W/other" pull -q --rebase 2>/dev/null
printf 'conflict\n' > "$W/other/docs/T1-epic-one/progress.md"; g -C "$W/other" commit -qam c1; git -C "$W/other" push -q 2>/dev/null; ok $? 0 "G2 setup: the other session's change is on the remote"
printf 'mine\n' > "$TR/docs/T1-epic-one/progress.md"; g -C "$TR" commit -qam c2
n=$(heads); T log T2 Progress x 2>"$W/err"; ok $? 2 "G2 a conflicting rebase: refused"
grep -q 'nothing written' "$W/err" && [ "$(heads)" = "$n" ] && [ ! -d "$TR/.git/rebase-merge" ]; ok $? 0 "G2 no new commit, rebase aborted"
git -C "$TR" reset -q --hard origin/main

echo "== H. compatibility"
out=$(uv run -q "$H" flush; uv run -q "$H" queue --repo . --key T2 --list; uv run -q "$H" state --set x=1); ok "$?:$out" "0:" "H1 flush, queue --list, state: silent no-ops"
uv run -q "$H" find --key T2 2>"$W/err"; ok $? 2 "H2 a retired subcommand: exit 2"
grep -q retired "$W/err"; ok $? 0 "H2 says it was retired"
T log AIUE-1 Progress x 2>/dev/null; ok $? 2 "H3 a Jira key: refused"

echo "== I. no hard-coded tracker"
! grep -n 'uedge-sandbox\|uedge-tracker\|holm10' "$H"; ok $? 0 "I1 the helper names no owner or repo"

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
