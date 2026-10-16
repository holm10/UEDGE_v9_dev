#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
Session guard: non-blocking warnings to the owner when a session drifts into the expensive patterns of epic AIUE-8
(`.claude/context/process-tiers.md` -> Session SOP). It never blocks and never changes a permission decision: it prints
a `{"systemMessage": ...}` JSON object (shown to the user) or nothing, and always exits 0 (fail-open).

  PreToolUse Agent/Task   warn when this session already launched AGENT_WARN_AT agents in the last AGENT_WINDOW_S.
  PreToolUse SendMessage  warn when the agent being resumed has a transcript of RESUME_WARN_BYTES or more (a resume
                          re-reads all of it); silent when the transcript can't be found.
  UserPromptSubmit        warn once per session when the session transcript reaches SESSION_WARN_BYTES, and once
                          when it has SESSION_WARN_COMPACTIONS compactions.

State: one JSON line per agent launch and per warning given, in <project>/logs/session_guard.jsonl (gitignored).
Transcripts are only stat-ed or scanned for compaction markers, never written. Messages carry only counts, sizes and
agent ids. Test: `uv run .claude/hooks/test_session_guard.py`.
"""
import json
import os
import sys
import time
from pathlib import Path

AGENT_WINDOW_S = 45 * 60            # look-back window for agent launches
AGENT_WARN_AT = 3                   # launches already made in the window that trigger the warning
RESUME_WARN_BYTES = 2_000_000       # subagent transcript size that makes a resume expensive (~hundreds of k tokens)
SESSION_WARN_BYTES = 15_000_000     # coordinating session transcript size
SESSION_WARN_COMPACTIONS = 2        # compactions in the coordinating session
SCAN_MIN_BYTES = 1_000_000          # don't scan smaller transcripts for compactions (they can't have many)
COMPACT_MARKER = b'"compact_boundary"'


def read_log(log_path):
    try:
        with open(log_path) as f:
            return [json.loads(ln) for ln in f if ln.strip()]
    except (OSError, ValueError):
        return []


def append_log(log_path, rec):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def agent_warning(records, session_id, now):
    """The warning for launching one more agent, given earlier launch records, or None."""
    recent = [r for r in records if r.get("kind") == "agent" and r.get("session_id") == session_id
              and now - r.get("t", 0) <= AGENT_WINDOW_S]
    if len(recent) < AGENT_WARN_AT:
        return None
    return (f"session_guard: this session already launched {len(recent)} agents in the last "
            f"{AGENT_WINDOW_S // 60} min. Run agents in parallel only when it shortens the critical path (about 3 at "
            "once at most); consider waiting for one to finish and serialising (process-tiers.md, Session SOP).")


def subagent_transcript(transcript_path, agent_id):
    """<session dir>/subagents/agent-<id>.jsonl next to the session transcript <session dir>.jsonl, or None."""
    if not transcript_path or not agent_id:
        return None
    agent_id = str(agent_id)
    agent_id = agent_id[len("agent-"):] if agent_id.startswith("agent-") else agent_id
    if not agent_id.replace("-", "").replace("_", "").isalnum():
        return None
    tp = Path(transcript_path)
    for cand in [tp.with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl",
                 tp.parent / f"agent-{agent_id}.jsonl"]:
        if cand.is_file():
            return cand
    return None


def resume_warning(size, agent_id):
    if size is None or size < RESUME_WARN_BYTES:
        return None
    return (f"session_guard: resuming agent {agent_id}, whose transcript is {size / 1e6:.1f} MB: a resume re-reads all "
            "of it. For a fix round, start a fresh small agent with the findings, the diff range and the ticket's "
            ".claude/work/<KEY>/handoff.md instead; keep SendMessage for quick questions (process-tiers.md, Fresh "
            "fixer).")


def count_compactions(path, size):
    if size < SCAN_MIN_BYTES:
        return 0
    n, tail = 0, b""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 22)
            if not chunk:
                return n
            buf = tail + chunk  # the tail is shorter than the marker, so no marker is counted twice
            n += buf.count(COMPACT_MARKER)
            tail = buf[-(len(COMPACT_MARKER) - 1):]


def session_warnings(size, compactions, warned):
    """[(kind, message)] for the coordinating session, skipping kinds already warned about."""
    out = []
    if size >= SESSION_WARN_BYTES and "session-size" not in warned:
        out.append(("session-size", f"session_guard: this session's transcript is {size / 1e6:.0f} MB. Long sessions "
                    "re-read ever more context per turn; consider handing over (progress page, handoff notes) and "
                    "starting a fresh session for the next wave (process-tiers.md, Session SOP)."))
    if compactions >= SESSION_WARN_COMPACTIONS and "session-compactions" not in warned:
        out.append(("session-compactions", f"session_guard: this session has been compacted {compactions} times; "
                    "details from before are summaries now. Consider a fresh session with a handoff "
                    "(process-tiers.md, Session SOP)."))
    return out


def handle(event, log_path, now):
    """The message to show for one hook event (or None), recording what the next call needs."""
    sid = event.get("session_id", "")
    name = event.get("hook_event_name", "")
    tool = event.get("tool_name", "")
    if name == "PreToolUse" and tool in ("Agent", "Task"):
        msg = agent_warning(read_log(log_path), sid, now)
        append_log(log_path, {"kind": "agent", "session_id": sid, "t": now})
        return msg
    if name == "PreToolUse" and tool == "SendMessage":
        agent_id = (event.get("tool_input") or {}).get("to")
        path = subagent_transcript(event.get("transcript_path"), agent_id)
        return resume_warning(path.stat().st_size if path else None, agent_id)
    if name == "UserPromptSubmit":
        tp = event.get("transcript_path")
        if not tp or not Path(tp).is_file():
            return None
        size = Path(tp).stat().st_size
        warned = {r.get("kind") for r in read_log(log_path) if r.get("session_id") == sid}
        found = session_warnings(size, count_compactions(tp, size), warned)
        for kind, _ in found:
            append_log(log_path, {"kind": kind, "session_id": sid, "t": now})
        return "\n".join(m for _, m in found) or None
    return None


def main():
    try:
        event = json.load(sys.stdin)
        root = os.environ.get("CLAUDE_PROJECT_DIR")
        root_path = Path(root) if root else Path(__file__).resolve().parents[2]
        msg = handle(event, root_path / "logs" / "session_guard.jsonl", time.time())
        if msg:
            print(json.dumps({"systemMessage": msg}))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
