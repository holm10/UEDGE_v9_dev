"""T192: summarise repeat.py results. python summarize.py RESULTS.jsonl ...
Per entry: runs, runs per class, runs that test_invalid would fail (invalid_problem against the pin), the distinct
'last' locations of the read (offsets stripped for gaps) and the conditions under which any run left the pin."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "tests" / "yldot").is_dir())
sys.path.insert(0, str(ROOT / "tests" / "yldot" / "tools"))


def group(tag):
    return re.sub(r"\d+$", "", tag) or tag


def fails(rec):
    """test_invalid's verdict for this run (test_variants.invalid_problem, without importing pytest-only code)."""
    pin = rec["pin"]
    if pin.startswith("INVALID"):
        return rec["class"] != "INVALID" or rec["reason"].split(":")[0].split()[0] != pin.split()[1]
    return rec["class"] != pin


def main(paths):
    rows = [json.loads(s) for p in paths for s in open(p) if s.strip()]
    by = defaultdict(list)
    for r in rows:
        by[r["family"], r["id"]].append(r)
    for (fam, vid), rs in sorted(by.items()):
        cls = Counter(r["class"] + ("" if r["class"] != "INVALID" else " " + r["reason"].split(":")[0][:40])
                      for r in rs)
        bad = [r for r in rs if fails(r)]
        lasts = Counter(re.sub(r"[+-]\d+|\[\d+\]", "", str(r["layout"].get("last"))) for r in rs if r["hook"])
        conds = Counter(group(r["tag"]) for r in rs)
        print("{}:{}  pin {}  runs {}  conditions {}".format(fam, vid, rs[0]["pin"], len(rs), dict(conds)))
        print("    classes {}".format(dict(cls)))
        print("    last read {}".format(dict(lasts)))
        print("    test_invalid would fail: {}{}".format(
            len(bad), "  (tags {})".format(dict(Counter(r["tag"] for r in bad))) if bad else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
