#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""
PostToolUse hook — the visibility pillar.

Fires AFTER every tool call. It can't block (the tool already ran), so its job is
to *observe*: append the full event as one JSON line to
<project>/logs/post_tool_use.jsonl. The result is a complete local audit trail of
exactly what the agent did — every command, every edit. `logs/` is gitignored.

The log always lives at the project root (via $CLAUDE_PROJECT_DIR), no matter
which directory the agent has `cd`-ed into, and each call appends a single line
instead of rewriting the file.

Pre = gate. Post = log.

Fails OPEN: any error exits 0, so logging can never break your session.
"""

import json
import os
import sys
from pathlib import Path


def main() -> None:
    try:
        data = json.load(sys.stdin)

        root = os.environ.get("CLAUDE_PROJECT_DIR")
        root_path = Path(root) if root else Path(__file__).resolve().parents[2]
        log_dir = root_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        with open(log_dir / "post_tool_use.jsonl", "a") as f:
            f.write(json.dumps(data) + "\n")

        sys.exit(0)

    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
