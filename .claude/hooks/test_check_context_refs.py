#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Test of check_context_refs.py --fix: a block of a cited file shifts, --fix must rewrite the docs and leave the lock
exactly as --update would write it (AIUE-115), moving range ends and list members with their reference (AIUE-112).
Each case runs the script as a subprocess in a throwaway repo (the script finds its root from its own path).
Usage: uv run .claude/hooks/test_check_context_refs.py [script]   (exit 0 = all passed; default: the sibling script)."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent / "check_context_refs.py"
PASS = FAIL = 0


def ok(cond, name):
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(("PASS " if cond else "FAIL ") + name)


def lines(n, at=None):
    """n unique lines `v<k> = <k>`, with the text at[k] on line k instead."""
    at = at or {}
    return [at.get(k, f"v{k} = {k}") for k in range(1, n + 1)]


class Repo:
    def __init__(self, root, doc, body):
        self.root = root
        shutil.rmtree(root, ignore_errors=True)
        for d in (".claude/hooks", ".claude/context", "src"):
            (root / d).mkdir(parents=True)
        shutil.copy(SCRIPT, root / ".claude/hooks/check_context_refs.py")
        (root / "CLAUDE.md").write_text(doc)
        self.write(body)
        self.run("--update")

    def write(self, body):
        (self.root / "src/a.py").write_text("\n".join(body) + "\n")

    def run(self, *args):
        p = subprocess.run([sys.executable, str(self.root / ".claude/hooks/check_context_refs.py"), *args],
                           capture_output=True, text=True, cwd=self.root)
        return p.returncode, p.stdout

    def doc(self):
        return (self.root / "CLAUDE.md").read_text()

    def lock(self):
        return json.loads((self.root / ".claude/context/refs.lock.json").read_text())

    def lock_is_fresh(self):
        """True if the lock equals what --update writes now (--update rewrites it, so call this last)."""
        before = self.lock()
        self.run("--update")
        return before == self.lock()


def insert(body, after, count, tag):
    return body[:after] + [f"{tag}{k} = 0" for k in range(count)] + body[after:]


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # T1 chained moves: 10 -> 17 and 17 -> 24 (the AIUE-109 shape: setup.py:637,643,644,653 shifted by +7)
    body = lines(40)
    r = Repo(tmp / "t1", "See `src/a.py:10,17,18,27`.\n", body)
    r.write(insert(body, 9, 7, "ins"))
    rc, out = r.run("--fix")
    ok("`src/a.py:17,24,25,34`" in r.doc(), "T1 chained moves: the doc is rewritten")
    ok(r.lock().get("src/a.py:24") == "v17 = 17", "T1 chained moves: the lock holds line 17's text at 24")
    ok("src/a.py:10" not in r.lock(), "T1 chained moves: the moved-from key no one cites is dropped")
    ok(rc == 0 and out.strip().endswith("OK"), "T1 chained moves: --fix ends clean")
    ok(r.run() == (0, "OK\n"), "T1 chained moves: a plain re-run is clean")
    ok(r.lock_is_fresh(), "T1 chained moves: the lock equals what --update writes")

    # T2 range end with text that is not unique (`]` also on line 30): it moves with its start
    body = lines(40, {9: "]", 30: "]"})
    r = Repo(tmp / "t2", "See `src/a.py:5-9`.\n", body)
    r.write(insert(body, 4, 3, "ins"))
    rc, out = r.run("--fix")
    ok("`src/a.py:8-12`" in r.doc(), "T2 range end: moved with its start")
    ok(rc == 0 and "STALE" not in out, "T2 range end: not reported STALE")
    ok(r.lock_is_fresh(), "T2 range end: the lock equals what --update writes")

    # T3 list members with non-unique text and two different shifts: each borrows its nearest neighbour's
    body = lines(50, {22: "]", 42: "]"})
    r = Repo(tmp / "t3", "See `src/a.py:20,22,40,42`.\n", body)
    r.write(insert(insert(body, 30, 5, "mid"), 19, 1, "top"))
    rc, out = r.run("--fix")
    ok("`src/a.py:21,23,46,48`" in r.doc(), "T3 list, two shifts: every member moved by its neighbour's shift")
    ok(rc == 0 and r.lock_is_fresh(), "T3 list, two shifts: clean, and the lock equals what --update writes")

    # T4 a range end whose text really changed stays STALE (two other `]`, so the old text is still not unique)
    body = lines(40, {9: "]", 30: "]", 35: "]"})
    r = Repo(tmp / "t4", "See `src/a.py:5-9`.\n", body)
    shifted = insert(body, 4, 3, "ins")
    shifted[11] = "}"
    r.write(shifted)
    rc, out = r.run("--fix")
    ok("`src/a.py:8-9`" in r.doc(), "T4 changed end: only the start is rewritten")
    ok(rc == 1 and "STALE" in out, "T4 changed end: reported STALE")

    # T5 the same line cited by a range and on its own: only the range infers the move
    body = lines(40, {9: "]", 30: "]"})
    r = Repo(tmp / "t5", "See `src/a.py:5-9` and `src/a.py:9`.\n", body)
    r.write(insert(body, 4, 3, "ins"))
    rc, out = r.run("--fix")
    ok("`src/a.py:8-12` and `src/a.py:9`" in r.doc(), "T5 per reference: only the range is rewritten")
    lock = r.lock()
    ok(lock.get("src/a.py:9") == "]" and lock.get("src/a.py:12") == "]",
       "T5 per reference: the still-cited key keeps its text, the new key gets it")
    ok("src/a.py:5" not in lock and rc == 1 and "STALE" in out,
       "T5 per reference: the uncited old start is dropped, the lone citation is STALE")

    # T6 a chain across two doc lines: 10 -> 17 on one line, 17 -> 24 on the next
    body = lines(40)
    r = Repo(tmp / "t6", "See `src/a.py:10`.\nAnd `src/a.py:17`.\n", body)
    r.write(insert(body, 9, 7, "ins"))
    rc, out = r.run("--fix")
    ok(r.doc() == "See `src/a.py:17`.\nAnd `src/a.py:24`.\n", "T6 chain across lines: both lines rewritten")
    ok(rc == 0 and r.lock_is_fresh(), "T6 chain across lines: clean, and the lock equals what --update writes")

    # T7 a move onto a line another reference cites as STALE is held back (it would overwrite that lock entry)
    body = lines(6)
    r = Repo(tmp / "t7", "See `src/a.py:2`.\nAnd `src/a.py:3`.\n", body)
    r.write(["v1 = 1", "new = 0", "v2 = 2", "zz = 0", "v4 = 4", "v5 = 5", "v6 = 6"])
    rc, out = r.run("--fix")
    ok(rc == 1 and "STALE" in out and "held back" in out, "T7 masking: held back, STALE kept, exit 1")
    ok(r.doc() == "See `src/a.py:2`.\nAnd `src/a.py:3`.\n", "T7 masking: both doc lines unchanged")
    ok(r.lock().get("src/a.py:3") == "v3 = 3", "T7 masking: the STALE citation keeps its locked text")
    ok(r.run()[0] == 1, "T7 masking: a plain re-run still fails")

    # T8 the hold-back cascades along a chain: 10 -> 17 lands on a cited line whose own move 17 -> 24 is held
    body = lines(40)
    doc8 = "See `src/a.py:10`.\nAnd `src/a.py:17`.\nAnd `src/a.py:24`.\n"
    r = Repo(tmp / "t8", doc8, body)
    before = r.lock()
    shifted = insert(body, 9, 7, "ins")
    shifted[30] = "gone = 0"
    r.write(shifted)
    rc, out = r.run("--fix")
    ok(rc == 1 and "held back" in out, "T8 cascade: held back, exit 1")
    ok(r.doc() == doc8, "T8 cascade: all doc lines unchanged")
    ok(r.lock() == before, "T8 cascade: the lock is unchanged")

print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
