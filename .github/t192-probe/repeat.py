"""T192 Tasks 3-4: evaluate bounds-check entries N times through the real harness (Runner, forkserver or spawn) and
classify each run as test_invalid does (tests/yldot/test_variants.py:257-268), with the t192hook layout record.

  python repeat.py --out RESULTS.jsonl [--n N] [--mode forkserver|spawn] [--no-hook] [--tag TEXT] FAMILY:ID ...

The environment of this process (MALLOC_PERTURB_, PYTHONHASHSEED, a padding variable) is what the forkserver inherits:
one process per condition. The default of each (family, config) is cached in cache/ (it has no out-of-bounds read).
Run from the worktree root, with the venv's python; needs a __main__ guard (uedge-gotchas.md, Test tooling)."""
import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "tests" / "yldot").is_dir())
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "yldot" / "tools"))
sys.path.insert(0, str(HERE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entries", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--mode", default=None)
    ap.add_argument("--no-hook", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--cache", default=str(HERE.parent / "cache"))
    a = ap.parse_args()
    os.environ["PYTHONPATH"] = os.pathsep.join([str(HERE)] + [p for p in [os.environ.get("PYTHONPATH")] if p])
    ctrl = HERE.parent / "ctrl-{}.json".format(os.getpid())
    os.environ["T192_CTRL"] = str(ctrl)  # set before the forkserver starts: it fixes its environment then

    import inventory
    from yldot.harness import compare, manifest as mf, variants
    from yldot.harness.process import Runner, family_dir
    import make_references as mr

    inv = {(r["family"], r["id"]): r for r in json.loads(json.dumps(_inv(inventory)))}
    runner = Runner(a.mode)
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    platform = "{}-{}".format(sys.platform, os.uname().machine)
    for spec in a.entries:
        family, vid = spec.split(":", 1)
        row = inv[family, vid]
        e = mf.load(family)["variables"][vid]
        plan = {v.id: v for v in variants.plan(family=family)}
        cfile = cache / "{}-{}-{}.pkl".format(platform, family, e["config"] + ("-" + e["base"] if e.get("base") else ""))
        if cfile.exists():
            base = pickle.loads(cfile.read_bytes())
        else:
            if e.get("base"):
                b = mf.load(family)["variables"][e["base"]]
                rb = runner.evaluate(family, variant=plan[e["base"]], replay=b["applied"])
            else:
                rb = runner.evaluate(family, config=e["config"])
            assert rb.ok, rb.message
            base = rb.data
            cfile.write_bytes(pickle.dumps(base))
        fdir = family_dir(family)
        tol = mr.tolerance(fdir, base["yldot"], e["config"], compare.index_map(base, compare.load_regions(fdir)))
        layout = HERE.parent / "layout-{}.jsonl".format(os.getpid())
        ctrl.write_text(json.dumps({"read": row["read"], "out": str(layout)}))
        for i in range(a.n):
            if layout.exists():
                layout.unlink()
            t0 = time.time()
            r = runner.evaluate(family, variant=plan[vid], post=None if a.no_hook else "t192hook:post")
            cls, reason, finding = mr.classify(r, base, tol)
            lay = json.loads(layout.read_text().splitlines()[-1]) if layout.exists() else {}
            rec = {"tag": a.tag, "platform": platform, "mode": runner.mode, "family": family, "id": vid, "i": i,
                   "pin": row["pin"], "class": cls, "reason": (reason or finding or "")[:160],
                   "status": r.status, "wall_s": round(time.time() - t0, 1),
                   "malloc_perturb": os.environ.get("MALLOC_PERTURB_"), "hashseed": os.environ.get("PYTHONHASHSEED"),
                   "pad": len(os.environ.get("T192_PAD", "")), "hook": not a.no_hook, "layout": lay}
            with open(a.out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(json.dumps({k: rec[k] for k in ("family", "id", "i", "class", "reason", "wall_s")}
                             | {"last": lay.get("last"), "hits": lay.get("hits")}), flush=True)


def _inv(inventory):
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        return inventory.entries()
    finally:
        os.chdir(cwd)


if __name__ == "__main__":
    main()
