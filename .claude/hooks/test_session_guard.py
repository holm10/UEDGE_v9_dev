#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Test of session_guard.py: its pure functions and the hook end to end (JSON in, JSON out, always exit 0).
Usage: uv run .claude/hooks/test_session_guard.py   (exit 0 = all passed)."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_guard as g  # noqa: E402

PASS = FAIL = 0


def ok(cond, name):
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(("PASS " if cond else "FAIL ") + name)


def run_hook(event, project):
    p = subprocess.run([sys.executable, str(Path(g.__file__))], input=json.dumps(event) if isinstance(event, dict)
                       else event, capture_output=True, text=True, env={"CLAUDE_PROJECT_DIR": str(project), "PATH": ""})
    return p.returncode, p.stdout.strip()


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    now = 10_000.0
    recs = [{"kind": "agent", "session_id": "S", "t": now - 60 * i} for i in (1, 2)]
    ok(g.agent_warning(recs, "S", now) is None, "A1 two agents in the window: silent")
    recs.append({"kind": "agent", "session_id": "S", "t": now - 600})
    ok("already launched 3 agents" in (g.agent_warning(recs, "S", now) or ""), "A2 three in the window: warn")
    ok(g.agent_warning(recs, "OTHER", now) is None, "A3 another session's launches don't count")
    old = [dict(r, t=now - g.AGENT_WINDOW_S - 1) for r in recs]
    ok(g.agent_warning(old, "S", now) is None, "A4 launches older than the window don't count")

    sess = tmp / "proj" / "sid-1.jsonl"
    sub = tmp / "proj" / "sid-1" / "subagents"
    sub.mkdir(parents=True)
    sess.write_text("{}\n")
    (sub / "agent-a1b2c3.jsonl").write_bytes(b"x" * (g.RESUME_WARN_BYTES + 1))
    (sub / "agent-small.jsonl").write_text("{}\n")
    ok(g.subagent_transcript(str(sess), "a1b2c3") == sub / "agent-a1b2c3.jsonl", "B1 subagent transcript located")
    ok(g.subagent_transcript(str(sess), "agent-a1b2c3") is not None, "B2 an 'agent-' prefixed id works")
    ok(g.subagent_transcript(str(sess), "../../etc") is None, "B3 an id with path characters is ignored")
    ok(g.subagent_transcript(str(sess), "nope") is None and g.subagent_transcript(None, "x") is None,
       "B4 unknown agent or no transcript path: None")
    ok("fresh small agent" in (g.resume_warning(g.RESUME_WARN_BYTES, "a1") or ""), "B5 large transcript: warn")
    ok(g.resume_warning(10, "a1") is None and g.resume_warning(None, "a1") is None, "B6 small or unknown size: silent")

    big = tmp / "big.jsonl"
    with open(big, "wb") as f:
        f.write(b"x" * ((1 << 22) - 5) + g.COMPACT_MARKER + b"y" * 100 + g.COMPACT_MARKER + b"\n")  # 1st straddles
    ok(g.count_compactions(big, big.stat().st_size) == 2, "C1 compaction markers counted, also across chunk ends")
    ok(g.count_compactions(big, 10) == 0, "C2 small transcripts are not scanned")
    w = g.session_warnings(g.SESSION_WARN_BYTES, g.SESSION_WARN_COMPACTIONS, set())
    ok([k for k, _ in w] == ["session-size", "session-compactions"], "C3 both session warnings")
    ok(g.session_warnings(g.SESSION_WARN_BYTES, 5, {"session-size", "session-compactions"}) == [],
       "C4 each session warning is given once")
    ok(g.session_warnings(g.SESSION_WARN_BYTES - 1, g.SESSION_WARN_COMPACTIONS - 1, set()) == [],
       "C5 below both thresholds: silent")

    proj = tmp / "repo"
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "S2", "tool_input": {"prompt": "x"}}
    outs = [run_hook(ev, proj) for _ in range(4)]
    ok(all(c == 0 for c, _ in outs) and [bool(o) for _, o in outs] == [False, False, False, True],
       "D1 hook: the 4th agent launch (3 already in the window) warns, exit 0 every time")
    msg = json.loads(outs[3][1])
    ok(set(msg) == {"systemMessage"}, "D2 the output is only a systemMessage (no permission decision)")
    ev = {"hook_event_name": "PreToolUse", "tool_name": "SendMessage", "session_id": "S2",
          "transcript_path": str(sess), "tool_input": {"to": "a1b2c3", "message": "fix it"}}
    ok("handoff.md" in run_hook(ev, proj)[1], "D3 hook: resuming a large agent warns")
    ev["tool_input"]["to"] = "small"
    ok(run_hook(ev, proj) == (0, ""), "D4 hook: resuming a small agent is silent")
    ev = {"hook_event_name": "UserPromptSubmit", "session_id": "S3", "transcript_path": str(big), "prompt": "hi"}
    first, second = run_hook(ev, proj), run_hook(ev, proj)
    ok("compacted 2 times" in first[1] and second == (0, ""), "D5 hook: compaction warning once per session")
    ok(run_hook("not json", proj) == (0, ""), "D6 hook: bad input fails open (exit 0, no output)")
    ok(run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, proj) == (0, ""), "D7 other tools: silent")

print(f"RESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
