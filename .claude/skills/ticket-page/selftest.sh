#!/usr/bin/env bash
# Test of ticket_page.py (the ticket-page skill's helper), offline: a bare repo stands in for the tracker's remote, a
# clone for its checkout, a throwaway repo for the UEDGE checkout (tracker.toml only in its main checkout), and a fake
# `gh` first on PATH logs every call with the tracker's commit count at that moment and answers the issue query from
# canned JSON. One case per guarantee: (A) one record per ticket, under its epic; (B) publish: provenance, masking,
# secrets, GitHub only after the commit; (C) append-only log, multi-line and hostile text; (D) status and the
# Project/issue side; (E) the epic progress log; (F) a failed push loses nothing; (G) concurrent writers, parallel
# calls, a rebase conflict, a dirty checkout, the wrong branch; (H) compatibility no-ops, retired subcommands and
# sanitize; (I) the tracker is not hard-coded.
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
  "project field-list") cat "$GH_DIR/fields.json" ;;
  "project view") echo '{"id":"PVT_test"}' ;;
  "issue list") cat "$GH_DIR/list.json" 2>/dev/null || echo '[]' ;;
  "issue create") python3 -I "$GH_DIR/create.py" "$GH_DIR" "$@" ;;
  "project item-add") # issue 22 was added by the Project itself in the meantime (a race seen on the real import)
    case "$*" in *issues/22\ *) echo '{"items":[{"id":"ITEM-AUTO22","content":{"number":22,"repository":"acme/tracker"}}]}' > "$GH_DIR/items.json"
      echo "GraphQL: Content already exists in this project (addProjectV2ItemById)" >&2; exit 1 ;; esac
    echo "ITEM-ADDED" ;;
  "project item-list") cat "$GH_DIR/items.json" 2>/dev/null || echo '{"items":[]}' ;;
  "api repos/"*) echo '[]' ;;
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
# `gh issue create` (section J): the next number from 20, the issue's graphql answer and a `gh issue list` row.
cat > "$W/gh/create.py" <<'EOF'
import json, sys
from pathlib import Path
d, args = Path(sys.argv[1]), sys.argv[2:]
opt = lambda k: args[args.index(k) + 1] if k in args else None
n = int((d / "next").read_text()) if (d / "next").exists() else 20
(d / "next").write_text(str(n + 1))
body, par = Path(opt("--body-file")).read_text(), opt("--parent")
parent = {"number": int(par), "title": json.loads((d / f"issue-{par}.json").read_text())["data"]["repository"]["issue"]["title"]} if par else None
issue = {"title": opt("--title"), "body": body, "issueType": {"name": opt("--type")}, "parent": parent,
         "projectItems": {"nodes": [{"id": f"ITEM{n}", "project": {"number": 7}, "tier": None}]}}
(d / f"issue-{n}.json").write_text(json.dumps({"data": {"repository": {"issue": issue}}}))
url = f"https://github.com/acme/tracker/issues/{n}"
rows = json.loads((d / "list.json").read_text()) if (d / "list.json").exists() else []
(d / "list.json").write_text(json.dumps(rows + [{"number": n, "body": body, "url": url}]))
print(url)
EOF
export GH_LOG="$W/gh.log" GH_DIR="$W/gh" GH_TRACKER="$TR" PATH="$W/bin:$PATH"

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

echo "== H. compatibility"
uv run -q "$H" flush >"$W/o1"; e1=$?; uv run -q "$H" queue --repo . --key T2 --list >"$W/o2"; e2=$?; uv run -q "$H" state --set x=1 >"$W/o3"; e3=$?
ok "$e1$e2$e3:$(cat "$W/o1" "$W/o2" "$W/o3")" "000:" "H1 flush, queue --list, state: each a silent no-op"
uv run -q "$H" find --key T2 2>"$W/err"; ok $? 2 "H2 a retired subcommand: exit 2"
grep -q retired "$W/err"; ok $? 0 "H2 says it was retired"
uv run -q "$H" progress --new --meta m.json 2>"$W/err"; grep -q retired "$W/err"; ok $? 0 "H2 progress --new: retired too"
T log AIUE-1 Progress x 2>/dev/null; ok $? 2 "H3 a Jira key: refused"
printf 'see /Users/someone/z\n' | uv run -q "$H" sanitize --repo "$W/wt" --max-chars 100 | grep -q '{local}/z'; ok $? 0 "H4 sanitize --repo --max-chars (rca's call)"
printf '%0200d\n' 0 | uv run -q "$H" sanitize --repo "$W/wt" --max-chars 100 >/dev/null 2>&1; ok $? 1 "H4 over the cap: refused"

echo "== J. jira_import.py: a Jira epic's To Do tickets into the tracker"
J="$(dirname "$H")/jira_import.py"; mkdir -p "$W/j"
st(){ echo "{\"name\":\"$1\",\"statusCategory\":{\"key\":\"$2\"}}"; }
cm(){ echo "{\"id\":\"$1\",\"created\":\"2026-01-01T00:00:00.000-0800\",\"body\":\"$2\"}"; }
iss(){ # key type status-json parent description comments-json-list total links-json
  echo "{\"key\":\"$1\",\"fields\":{\"summary\":\"Summary of $1\",\"issuetype\":{\"name\":\"$2\"},\"status\":$3,\"parent\":$4,\"labels\":[],\"created\":\"2026-01-01T00:00:00.000-0800\",\"description\":\"$5\",\"comment\":{\"total\":$7,\"comments\":[$6]},\"issuelinks\":[$8]}}"; }
BLK='{"type":{"inward":"is blocked by","outward":"blocks"},"inwardIssue":{"key":"J-3","fields":{"status":{"name":"To Do"}}}}'
snap(){ echo "{\"isLast\":true,\"issues\":[$(iss J-1 Epic "$(st 'To Do' new)" null 'The epic.' "$(cm 11 '**Owner decision: go.**')" 1 ''),
$(iss J-2 Story "$(st 'To Do' new)" '{"key":"J-1"}' 'Second.' '' 0 "$BLK"),
$(iss J-3 Task "$(st 'To Do' new)" '{"key":"J-1"}' "$1" "$(cm 31 '**Owner, 2026-01-01: do option 1.**\n\nMore.'),$(cm 32 'A note.')" "$2" ''),
$(iss J-4 Story "$(st Done done)" '{"key":"J-1"}' 'Done one.' '' 0 '')]}"; }
snap 'Third. Tier S (small).' 2 > "$W/j/snap.json"
JI(){ uv run -q "$J" --repo "$W/wt" --tracker-dir "$TR" --date 2026-01-02 --epic J-1 --first J-3 "$@"; }
n=$(heads); c=$(grep -c 'issue create' "$GH_LOG")
JI --snapshot "$W/j/snap.json" --out "$W/j/dry/m.json" --dry-run >"$W/j/o1" 2>&1; e=$?
ok "$e:$(heads):$(grep -c 'issue create' "$GH_LOG"):$(ls "$W/j/dry/bodies" | wc -l | tr -d ' ')" "0:$n:$c:3" "J1 dry run: exit 0, no commit, no create, 3 bodies rendered"
JI --snapshot "$W/j/snap.json" --out "$W/j/m.json" >"$W/j/o2" 2>&1; ok $? 0 "J2 import: exit 0"
grep 'issue create' "$GH_LOG" | sed -n '1p' | grep -q -- '--type Epic' \
  && grep 'issue create' "$GH_LOG" | sed -n '2p' | grep -q -- '--type Task --title Summary of J-3 .*--label from-jira --parent 20' \
  && grep 'issue create' "$GH_LOG" | sed -n '3p' | grep -q -- '--type Feature --title Summary of J-2'; ok $? 0 "J2 epic first, --first next, types mapped, label and parent"
[ "$(grep -c 'issue create' "$GH_LOG")" = 3 ]; ok $? 0 "J2 the Done child is not imported"
B="$W/j/bodies/J-3.md"
head -1 "$B" | grep -q '^_Imported from Jira J-3 (Task, To Do, created 2026-01-01) on 2026-01-02' && grep -q '^Third. Tier S' "$B" \
  && grep -q '^#### Comment 31 (2026-01-01)$' "$B" && grep -q '^Tier: S (stated in the Jira text)$' "$B" && grep -q '^Jira links: none$' "$B"; ok $? 0 "J3 body: key line, description and comments verbatim, Tier and links lines"
grep -q 'F_TIER --single-select-option-id O_S' "$GH_LOG" && grep -q 'F_JIRA --text J-3' "$GH_LOG"; ok $? 0 "J3 Project: Tier S and the Jira key set"
ED=$(ls -d "$TR"/docs/T20-*/ 2>/dev/null | head -1)
grep -q 'Owner: Owner decision: go. (Jira J-1 comment 11)' "$ED/epic.md" && grep -q 'J-4 (Done)' "$ED/epic.md" \
  && grep -q '^| J-3 | T21 | Task | S | none |$' "$ED/breakdown.md" && grep -q '^| J-2 | T22 | Feature | not stated | T21 |$' "$ED/breakdown.md" \
  && grep -q '^## T22: Summary of J-2$' "$ED/breakdown.md"; ok $? 0 "J4 epic.md (owner decision, Done child) and breakdown.md (mapping, entries)"
R21=$(ls "$ED"/T21-*/record.md 2>/dev/null)
grep -q '^| Status | Backfilled (Ticket section: imported from Jira J-3' "$R21" && grep -q 'Owner (Jira J-3 comment 31, 2026-01-01; quoted in the Ticket section): Owner, 2026-01-01: do option 1.' "$R21" \
  && ls "$ED"/T22-*/record.md >/dev/null 2>&1; ok $? 0 "J5 records under the epic: Backfilled, the owner comment in Findings"
[ "$(grep -c 'issue edit 22 -R acme/tracker --add-blocked-by 21' "$GH_LOG")" = 1 ]; ok $? 0 "J6 blocked-by between imported tickets, set once"
grep -q 'item-edit --id ITEM-AUTO22 .*F_JIRA --text J-2' "$GH_LOG"; ok $? 0 "J6 an item the Project added itself: found by the item list, fields set on it"
n=$(heads); JI --snapshot "$W/j/snap.json" --out "$W/j/m.json" >"$W/j/o3" 2>&1; e=$?
ok "$e:$(heads):$(grep -c 'issue create' "$GH_LOG")" "0:$n:3" "J7 a re-run: no create, no commit"
snap 'Third.' 3 > "$W/j/bad.json"; n=$(heads)
JI --snapshot "$W/j/bad.json" --out "$W/j/x.json" 2>"$W/err"; e=$?
ok "$e:$(heads)" "2:$n" "J8 a snapshot missing comments: refused, nothing written"
grep -q 'J-3: 2 of 3 comments' "$W/err"; ok $? 0 "J8 says which ticket and how many"
snap 'Third. token = abcdefghijkl' 2 > "$W/j/sec.json"
JI --snapshot "$W/j/sec.json" --out "$W/j/y.json" 2>"$W/err"; e=$?
ok "$e:$(grep -c 'Jira J-3 contains' "$W/err")" "1:1" "J9 secret-like text: refused, names the ticket"

# A second epic (J-5): which comments count as owner decisions, which Tier wins, a PIV record comment, a resume.
snap2(){ echo "{\"isLast\":true,\"issues\":[$(iss J-5 Epic "$(st 'To Do' new)" null 'Epic two.' '' 0 ''),
$(iss J-6 Story "$(st 'To Do' new)" '{"key":"J-5"}' 'Tier S first. Later Tier M.' "$(cm 61 "Owner's note: x"),$(cm 62 'Owner question: y'),$(cm 63 '**PIV record: plan** (done).'),$(cm 64 '**Owner decision, 2026-01-01: go.**')" 4 ''),
$(iss J-7 Task "$(st 'To Do' new)" '{"key":"J-5"}' 'Tier M or L: new paths.' '' 0 '')]}"; }
snap2 > "$W/j/snap2.json"
JI2(){ uv run -q "$J" --repo "$W/wt" --tracker-dir "$TR" --date 2026-01-02 --epic J-5 --snapshot "$W/j/snap2.json" --out "$W/j/m2.json"; }
JI2 >"$W/j/o4" 2>&1; ok $? 0 "J10 second epic imported"
E2=$(ls -d "$TR"/docs/T23-*/ 2>/dev/null | head -1); R24=$(ls "$E2"/T24-*/record.md 2>/dev/null)
fnd(){ awk '$0=="## Findings and decisions"{f=1;next} /^## /{f=0} f' "$R24"; }
[ "$(fnd | grep -c 'Owner (Jira')" = 1 ] && fnd | grep -q 'comment 64' && ! grep -q "Owner (Jira J-6 comment 6[123]" "$R24"; ok $? 0 "J10 only 'Owner decision' counts: \"Owner's note\", \"Owner question\" are not decisions"
grep -q '^| J-6 | T24 | Feature | M | none |$' "$E2/breakdown.md" && grep -q '^| J-7 | T25 | Task | not stated | none |$' "$E2/breakdown.md" \
  && grep -q '^Tier: not stated' "$W/j/bodies/J-7.md"; ok $? 0 "J11 the last unambiguous Tier wins (S then M: M); \"Tier M or L\" states none"
grep -q '^- 2026-01-02 (jira-import): Jira PIV record comment 63 (2026-01-01): PIV record: plan' "$R24"; ok $? 0 "J12 a 'PIV record' comment becomes a Progress entry"
grep -v 'status Backfilled' "$R24" | grep -v 'comment 64' | sed 's/^| Status | .*/| Status | Planned |/' > "$W/j/rec.new"; cp "$W/j/rec.new" "$R24"
g -C "$TR" commit -qam "break T24"; git -C "$TR" push -q 2>/dev/null; n=$(heads)
JI2 >"$W/j/o5" 2>&1; e=$?
ok "$e:$(heads)" "0:$((n + 2))" "J13 resume: the lost Status call and the lost Findings entry are made again, one commit each"
grep -q '^| Status | Backfilled' "$R24" && fnd | grep -q 'comment 64' && [ "$(grep -c 'comment 63' "$R24")" = 1 ]; ok $? 0 "J13 the row and the entry are back, what was there is not doubled"
n=$(heads); JI2 >"$W/j/o6" 2>&1; ok "$(heads)" "$n" "J13 and a complete import makes no commit"
# the body's first line was edited away: the Project's Jira key field still identifies the issue
python3 - "$GH_DIR" <<'EOF'
import json, sys
d = sys.argv[1] + "/"
rows = [r for r in json.load(open(d + "list.json")) if "J-3" not in r["body"][:40]]
json.dump(rows, open(d + "list.json", "w"))
json.dump({"items": [{"id": "ITEM21", "jira key": "J-3", "content": {"number": 21, "repository": "acme/tracker",
           "url": "https://github.com/acme/tracker/issues/21"}}]}, open(d + "items.json", "w"))
EOF
c=$(grep -c 'issue create' "$GH_LOG"); JI --snapshot "$W/j/snap.json" --out "$W/j/m.json" >"$W/j/o7" 2>&1
ok "$?:$(grep -c 'issue create' "$GH_LOG")" "0:$c" "J14 a lost body marker: the Jira key field prevents a duplicate"

echo "== I. no hard-coded tracker"
! grep -n 'uedge-sandbox\|uedge-tracker\|holm10\|atlassian.net' "$H" "$J"; ok $? 0 "I1 the helpers name no owner, repo or Jira site"

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
