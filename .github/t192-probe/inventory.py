"""T192 Task 1: every INVALID manifest entry whose reason starts 'bounds-check', with its pinned serial outcome and
the read the T192 layout hook maps for it. Run from the worktree root: python3 .claude/work/T192/probes/inventory.py
[--json]."""
import glob
import json
import re
import sys

SERIAL = re.compile(r"\(serial build: (.*)\)$")
# the read each audit line makes, as named in the hook (t192hook.READS); None: no layout map (wraps to ekpt(1))
READ_OF = {"bbb/pandf_boundary.F:3474": "ni3", "bbb/pandf_boundary.F:1881": "tg2",
           "bbb/pandf_boundary.F:556": "fngysi0", "aph/aphrates.F:1054": None}


def entries():
    out = []
    for p in sorted(glob.glob("tests/yldot/references/*.manifest.json")):
        fam = p.split("/")[-1].split(".")[0]
        for vid, e in (json.load(open(p)).get("variables") or {}).items():
            r = str(e.get("reason", ""))
            if e.get("class") == "INVALID" and r.startswith("bounds-check"):
                where = r.split(": ")[1]
                pin = SERIAL.search(r).group(1)
                out.append({"family": fam, "id": vid, "where": where, "read": READ_OF[where],
                            "pin": pin if pin in ("SENSITIVE", "INERT", "MARGINAL", "EQSET") else
                            "INVALID " + pin.split()[0], "reason": r})
    return out


if __name__ == "__main__":
    rows = entries()
    if "--json" in sys.argv:
        print(json.dumps(rows))
    else:
        for r in rows:
            print("{family:11s} {id:24s} {where:28s} {read!s:8s} {pin}".format(**r))
        print(len(rows), "entries;", sum(r["pin"] == "SENSITIVE" for r in rows), "SENSITIVE,",
              sum(r["pin"].startswith("INVALID") for r in rows), "INVALID")
