#!/usr/bin/env bash
# Test of the branch policy (change_kind.py) and its PreToolUse hook (pre_tool_use.py) in throwaway git repos:
# working documents refused on every branch (deletions of tracked ones allowed), physics specs as product, renames,
# paths with spaces, in-command file creation, here-documents, three-dot ranges, and the unchanged process rules.
# Usage: .claude/hooks/test_change_kind.sh [workdir]   (default: a new temporary directory). Exit 0 = all passed.
set -u
HOOKS="$(cd "$(dirname "$0")" && pwd)"; SRC="$(cd "$HOOKS/../.." && pwd)"
CK="uv run -q $HOOKS/change_kind.py"; PRE="uv run -q $HOOKS/pre_tool_use.py"
W="${1:-$(mktemp -d)}"; mkdir -p "$W"; echo "workdir: $W"; PASS=0; FAIL=0
ok(){ if [ "$1" = "$2" ]; then PASS=$((PASS+1)); echo "PASS $3"; else FAIL=$((FAIL+1)); echo "FAIL $3 (exit $1, want $2)"; fi; }
ck(){ (cd "$R" && $CK "$@" >"$W/out.txt" 2>&1); }
pre(){ printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.stdin.read()}}))' "$R" | $PRE 2>"$W/err.txt"; }
stage(){ git -C "$R" reset -q; for f in "$@"; do mkdir -p "$R/$(dirname "$f")"; [ -e "$R/$f" ] || echo x > "$R/$f"; git -C "$R" add -f -- "$f"; done; }
clean(){ git -C "$R" reset -q --hard; git -C "$R" clean -qfdx -e .gitignore; }

R="$W/repo"; git init -q "$R"; git -C "$R" checkout -q -b v9-develop
git -C "$R" config user.email t@t; git -C "$R" config user.name t
cp "$SRC/.gitignore" "$R/.gitignore"; mkdir -p "$R/docs/prds" "$R/docs/reviews" "$R/.claude/plans" "$R/doc"
echo old > "$R/docs/prds/E-1-old.md"; echo plan > "$R/.claude/plans/T-1.md"; echo rev > "$R/docs/reviews/T-1 plan round1.md"
echo d > "$R/doc/x.txt"; (cd "$R" && git add -f . && git -c core.hooksPath=/dev/null commit -qm base)

echo "== A. change_kind.py --staged on a ticket branch"
git -C "$R" checkout -q -b feature/v9-T-1-demo
stage .claude/plans/x.md; ck --staged; ok $? 1 "A1 .claude/plans/x.md refused"
grep -q 'working documents are never committed' "$W/out.txt"; ok $? 0 "A1 the message points to the working folder and the ticket page"
stage docs/reviews/x.md; ck --staged; ok $? 1 "A2 docs/reviews/x.md refused"
stage .claude/work/T-1/plan.md; ck --staged; ok $? 1 "A3 .claude/work/T-1/plan.md refused"
stage .claude/execution-reports/r.md; ck --staged; ok $? 1 "A4 .claude/execution-reports/ refused"
stage bbb/pandf.m docs/physics_specs/x.md; ck --staged; ok $? 0 "A5 physics change + docs/physics_specs/x.md allowed"
grep -q 'product  docs/physics_specs/x.md' "$W/out.txt"; ok $? 0 "A5 the physics spec is product"
stage docs/physics_specs/x-review-round1.md; ck --staged; ok $? 0 "A6 a file under docs/physics_specs is product (no exception)"
stage bbb/pandf.m; ck --staged; ok $? 0 "A7 plain product commit"
stage .claude/context/testing.md; ck --staged; ok $? 1 "A8 context without the code-facts trailer refused (unchanged)"
ck --staged --message $'x\n\nAI-layer: code-facts'; ok $? 0 "A8 context with the trailer allowed (unchanged)"
stage .claude/skills/commit/SKILL.md; ck --staged; ok $? 1 "A9 a skill on a ticket branch refused (unchanged)"
stage docs/physics_specs/foo.md .claude/skills/a/SKILL.md; ck --staged; ok $? 1 "A9 physics spec + skill: the skill refused"
clean; git -C "$R" rm -q docs/prds/E-1-old.md; ck --staged; ok $? 0 "A10 deleting a tracked legacy PRD copy allowed"
clean; echo more >> "$R/.claude/plans/T-1.md"; git -C "$R" add -f .claude/plans/T-1.md; ck --staged; ok $? 1 "A11 modifying a tracked legacy plan refused"
clean; git -C "$R" mv .claude/plans/T-1.md doc/plan-T-1.md; ck --staged; ok $? 1 "A12 renaming a working document into a product path refused"
grep -q 'being moved into the repo' "$W/out.txt"; ok $? 0 "A12 the rename is named"
clean; git -C "$R" mv doc/x.txt docs/reviews/x.txt; ck --staged; ok $? 1 "A13 renaming a product file into a working path refused"
clean

echo "== B. change_kind.py --staged on an AI-layer branch"
git -C "$R" checkout -q -b feature/v9-ai-demo v9-develop
stage .claude/plans/x.md; ck --staged; ok $? 1 "B1 .claude/plans/x.md refused"
stage docs/reviews/x.md; ck --staged; ok $? 1 "B2 docs/reviews/x.md refused"
stage .claude/skills/commit/SKILL.md CLAUDE.md .gitignore; ck --staged; ok $? 0 "B3 normal AI-layer commit allowed"
stage docs/physics_specs/x.md; ck --staged; ok $? 1 "B4 a physics spec (product) refused on an AI branch"
clean; git -C "$R" rm -q docs/prds/E-1-old.md; ck --staged; ok $? 0 "B5 deleting a tracked legacy PRD copy allowed"
clean
git -C "$R" checkout -q v9-develop; stage doc/y.txt; ck --staged; ok $? 1 "B6 protected branch refused"; clean

echo "== C. pre_tool_use.py on git commit commands (ticket branch)"
git -C "$R" checkout -q feature/v9-T-1-demo
mkdir -p "$R/docs/reviews"; echo y > "$R/docs/reviews/y.md"
pre 'git add -f docs/reviews/y.md && git commit -m x'; ok $? 2 "C1 git add -f of a review + commit blocked"
grep -q 'BLOCKED by branch policy' "$W/err.txt"; ok $? 0 "C1 reason given"
pre 'mkdir -p .claude/work/T-1 && echo x > .claude/work/T-1/new.md && git add -f .claude/work/T-1/new.md && git commit -m x'; ok $? 2 "C2 create + add -f + commit in one command blocked (a missing untracked path is not a deletion)"
pre 'cp doc/x.txt docs/reviews/copy.md && git add -f docs/reviews/copy.md && git commit -m x'; ok $? 2 "C3 cp into a legacy path + add -f + commit blocked"
clean; rm "$R/docs/reviews/T-1 plan round1.md"
pre 'git add "docs/reviews/T-1 plan round1.md" && git commit -m x'; ok $? 0 "C4 explicit git add of a deleted tracked path with a space (a deletion) allowed"
pre 'git add -A && git commit -m x'; ok $? 0 "C5 git add -A deleting a tracked file with a space allowed"
clean; echo z >> "$R/docs/reviews/T-1 plan round1.md"
pre 'git add -A && git commit -m x'; ok $? 2 "C6 git add -A modifying a tracked review with a space blocked (porcelain -z)"
pre 'git commit -am x'; ok $? 2 "C7 commit -a modifying a tracked review with a space blocked"
git -C "$R" add -A; pre 'git commit -m x'; ok $? 2 "C8 an already staged modification of a review with a space blocked"
clean; mkdir -p "$R/.claude/work/T-1"; echo p > "$R/.claude/work/T-1/plan.md"; echo y >> "$R/doc/x.txt"
pre 'git add -A && git commit -m x'; ok $? 0 "C9 git add -A with an ignored work folder + a product change allowed (git ignores the folder)"
pre 'git add . && git commit -m x'; ok $? 0 "C10 git add . likewise"
clean; git -C "$R" mv .claude/plans/T-1.md doc/plan-T-1.md
pre 'git commit -m x'; ok $? 2 "C11 a staged rename out of a working path blocked"
clean; mkdir -p "$R/.claude/skills/a"; echo k > "$R/.claude/skills/a/SKILL.md"
pre 'git add .claude/skills/a/SKILL.md && git commit -m x'; ok $? 2 "C12 a skill on a ticket branch blocked (unchanged)"
clean

echo "== D. here-documents are text, not commands"
pre $'cat > /dev/null <<EOF\nthen git commit -m x\nEOF'; ok $? 0 "D1 a here-document mentioning git commit (ticket branch) is not a commit"
pre $'cat > /dev/null <<\'EOF\'\nrun git add .claude/plans/x.md and git commit\nEOF'; ok $? 0 "D2 a quoted here-document mentioning git add of a working path is not a commit"
git -C "$R" checkout -q v9-develop
pre $'cat > /dev/null <<EOF\ngit commit\nEOF'; ok $? 0 "D3 a here-document mentioning git commit on a protected branch is not a commit"
pre $'git commit -F - <<\'EOF\'\nSubject\nEOF'; ok $? 2 "D4 a real commit with its message in a here-document is still checked (protected)"
pre $'cat <<EOF | git commit -F -\nSubject\nEOF'; ok $? 2 "D6 a command after <<EOF on the opening line is still checked (protected)"
pre $'cat <<\'EOF\' > m && git commit -F m\nSubject\nEOF'; ok $? 2 "D7 cat <<'EOF' > m && git commit -F m is still checked"
pre $'python3 - <<\'PY\' && git commit -am x\nprint(1)\nPY'; ok $? 2 "D8 python3 - <<'PY' && git commit -am x is still checked"
pre $'cat <<<EOF\ngit commit -m x\nEOF'; ok $? 2 "D9 a herestring (<<<) is not a here-document: the next line's commit is checked"
pre $'cat > /dev/null <<EOF\nEOF\ngit commit -m x\nEOF'; ok $? 2 "D10 an empty here-document doesn't swallow the commit after it"
pre $'bash <<EOF\ngit commit -m x\nEOF'; ok $? 0 "D11 documented limitation: commands fed to a shell through a here-document are not checked"
git -C "$R" checkout -q feature/v9-T-1-demo
stage .claude/context/testing.md
pre $'git commit -F - <<\'EOF\'\nSubject\n\nAI-layer: code-facts\nEOF'; ok $? 0 "D5 the code-facts trailer inside the here-document message still counts"
clean
mkdir -p "$R/.claude/work/T-1"
pre $'cat <<\'EOF\' > .claude/work/T-1/x.md && git add -f .claude/work/T-1/x.md && git commit -m x\nbody\nEOF'; ok $? 2 "D12 create a work doc from a here-document, force-add and commit on a ticket branch: blocked"
clean

echo "== E. ranges"
git -C "$R" checkout -q -b feature/v9-T-2-inflight v9-develop
mkdir -p "$R/.claude/plans"; echo p > "$R/.claude/plans/T-2.md"; git -C "$R" add -f .claude/plans/T-2.md
git -C "$R" -c core.hooksPath=/dev/null commit -qm "plan (before the rule)"; echo c >> "$R/doc/x.txt"; git -C "$R" -c core.hooksPath=/dev/null commit -qam code
ck --range v9-develop...HEAD; ok $? 1 "E1 an in-flight branch that tracks its plan fails the range check"
git -C "$R" rm -q .claude/plans/T-2.md; git -C "$R" -c core.hooksPath=/dev/null commit -qm "drop plan"
ck --range v9-develop...HEAD; ok $? 0 "E2 after git rm the range is clean"
git -C "$R" checkout -q v9-develop; echo n > "$R/doc/new-on-base.txt"; mkdir -p "$R/docs/reviews"; git -C "$R" rm -q "docs/reviews/T-1 plan round1.md"
git -C "$R" add doc/new-on-base.txt; git -C "$R" -c core.hooksPath=/dev/null commit -qm "base moves"
git -C "$R" checkout -q feature/v9-T-2-inflight
ck --range v9-develop..HEAD; ok $? 1 "E3 a two-dot range after the base moved shows the base's changes (false violation)"
ck --range v9-develop...HEAD; ok $? 0 "E4 the three-dot range shows only the branch's own changes"

echo "== F. PR size budget (--range; warnings only)"
budget(){ git -C "$R" checkout -q -b "$1" v9-develop; shift; mkdir -p "$R/bud"; "$@"; git -C "$R" add -f bud
  git -C "$R" -c core.hooksPath=/dev/null commit -qm budget; ck --range v9-develop...HEAD; }
budget feature/v9-T-3-small sh -c "echo x > '$R/bud/a.txt'"; ok $? 0 "F1 a small branch passes"
grep -q 'WARNING: PR size budget' "$W/out.txt"; ok $? 1 "F1 no budget warning"
budget feature/v9-T-4-many sh -c "for i in \$(seq 1 41); do echo x > '$R/bud/r'\$i.md; done"; ok $? 0 "F2 41 added report files: still exit 0"
grep -q 'adds 41 files' "$W/out.txt" && grep -q 'not a failure' "$W/out.txt"; ok $? 0 "F2 warned: too many files, with the hint"
budget feature/v9-T-5-code sh -c "for i in \$(seq 1 41); do echo 'x=1' > '$R/bud/m'\$i.py; done"; ok $? 0 "F3 41 added source files"
grep -q 'WARNING: PR size budget' "$W/out.txt"; ok $? 1 "F3 source and test code is not counted"
budget feature/v9-T-6-lines sh -c "seq 1 3001 > '$R/bud/table.txt'"; grep -q '3001 lines' "$W/out.txt"; ok $? 0 "F4 3001 added lines in one file: warned"
budget feature/v9-T-7-big sh -c "head -c 1100000 /dev/zero | tr '\\0' x > '$R/bud/blob.bin'"; grep -q 'over 1 MB: bud/blob.bin' "$W/out.txt"; ok $? 0 "F5 a file over 1 MB: warned"
budget feature/v9-T-8-data sh -c "for f in r.npz s.hdf5 t.log u.json; do echo x > '$R/bud/'\$f; done"; ok $? 0 "F6 data-like files: still exit 0"
grep -q 'data-like files added (4)' "$W/out.txt"; ok $? 0 "F6 warned: npz, hdf5, log and json named"
git -C "$R" checkout -q feature/v9-T-8-data; stage .claude/work/T-8/plan.md; git -C "$R" -c core.hooksPath=/dev/null commit -qm plan
ck --range v9-develop...HEAD; ok $? 1 "F7 a violation still fails with budget warnings present"
clean

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
