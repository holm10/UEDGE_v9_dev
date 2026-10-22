"""Confirm that variants inherit the default's tolerances (epic AIUE-9, PRD section 7.4; owner, 2026-10-22, AIUE-94
D2): the cross-build spread of a sample of SENSITIVE variants must stay within the default's per-entry tol_i.

Usage:
    <build's python> variant_tolerances.py collect REFS --label L --out DIR --build FILE [family ...]
    python variant_tolerances.py check REFS DIR [--report FILE] [family ...]

REFS is the references directory of a make_references.py run (--out DIR/references): <family>.json (the manifest
fields, with each variant's applied value) and samples/<family>.npz, the sample its child drew
(make_references.tolerance_sample: the 20 SENSITIVE ids with the smallest sha256("<seed>:<id>") plus every SENSITIVE
timestep id) with that build's yldot, yldot_J, the default's tol_<config> and the index arrays.

collect  runs inside one build's venv: each sampled variant once, in a fresh child, with its recorded applied value
         replayed (Runner.evaluate(..., replay=)), into DIR/L/<family>.npz. FILE is the build record (JSON: commit,
         options, compiler, ...); collect refuses a REFS whose provenance commit is not FILE's.
check    pairs the sides, the REFS run as linux-serial (the release-grade run of make_references.py) and the labels
         in DIR: mac_vs_linux (linux-serial against mac-serial) and o0_vs_o3 (mac-noopt against mac-serial), the
         serial pairs of measure_roundoff.py (AIUE-87). Per family, pair and variant, the largest |d_i| / tol_i over
         yldot and yldot_J. It passes iff every ratio is <= 1 (the test rule, decision 27); the largest is reported.

Exit codes: 0 every ratio <= 1; 2 usage, a missing side or a failed evaluation; 3 a ratio above 1 or index arrays
that differ between the builds: the epic owner decides (decision 23), nothing is loosened.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package

import numpy as np  # noqa: E402

from yldot.harness.state import INDEX_ARRAYS  # noqa: E402

LINUX = "linux-serial"
PAIRS = (("mac_vs_linux", LINUX, "mac-serial"), ("o0_vs_o3", "mac-noopt", "mac-serial"))
TIMEOUT_FACTOR = 5  # as make_references.py


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def families_of(refs, families):
    found = sorted(p.stem for p in (Path(refs) / "samples").glob("*.npz"))
    if not found:
        raise Stop(2, "{}: no samples/<family>.npz".format(refs))
    missing = sorted(set(families) - set(found))
    if missing:
        raise Stop(2, "{}: no sample for {}".format(refs, missing))
    return list(families) or found


def load(path):
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def collect(refs, label, out, build, families):
    from yldot.harness import Runner, load_evaluation, variants
    from yldot.harness.process import family_dir

    rec = json.loads(Path(build).read_text())
    plan = {v.id: v for v in variants.plan()}
    target = Path(out) / label
    target.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    for name in families_of(refs, families):
        m = json.loads((Path(refs) / "{}.json".format(name)).read_text())
        if m["provenance"]["commit"] != rec["commit"]:
            raise Stop(2, "{}: the references are of {}, this build of {}".format(name, m["provenance"]["commit"],
                                                                                  rec["commit"]))
        s = load(Path(refs) / "samples" / "{}.npz".format(name))
        timeout = TIMEOUT_FACTOR * float(load_evaluation(family_dir(name))["timeout_s"])
        ys, yjs, index = [], [], None
        for vid in s["ids"].tolist():
            r = runner.evaluate(name, variant=plan[vid], replay=m["variables"][vid]["applied"], timeout=timeout)
            if not r.ok:
                raise Stop(2, "{} {}: {} {}\n{}".format(name, vid, r.status, r.message, r.log_tail))
            ys.append(r.data["yldot"])
            yjs.append(r.data["yldot_J"])
            index = {n: np.asarray(r.data[n]) for n in INDEX_ARRAYS}
        np.savez(target / "{}.npz".format(name), ids=s["ids"], yldot=np.array(ys), yldot_J=np.array(yjs), **index)
        print("{}: {} variants -> {}".format(name, len(ys), target / "{}.npz".format(name)), flush=True)
    (target / "build.json").write_text(json.dumps(rec, indent=1) + "\n")


def ratios(a, b, ref):
    """{id: largest |a_i - b_i| / tol_i over yldot and yldot_J}, tol from ref (the REFS sample)."""
    if a["ids"].tolist() != b["ids"].tolist():
        raise Stop(2, "the sides hold different variants")
    for n in INDEX_ARRAYS:
        if not np.array_equal(a[n], b[n]):
            raise Stop(3, "index array {} differs between the builds: the epic owner decides".format(n))
    out = {}
    for k, (vid, config) in enumerate(zip(ref["ids"].tolist(), ref["configs"].tolist())):
        tol = ref["tol_" + config]
        r = max(float((np.abs(a[w][k] - b[w][k]) / tol).max()) for w in ("yldot", "yldot_J"))
        out[vid] = r if np.isfinite(r) else float("inf")
    return out


def check(refs, directory, families, report=None):
    lines, worst_all = [], 0.0
    rows = ["| family | pair | variants | largest ratio | variant |", "| --- | --- | --- | --- | --- |"]
    for name in families_of(refs, families):
        ref = load(Path(refs) / "samples" / "{}.npz".format(name))
        sides = {LINUX: ref}
        for label in {p[1] for p in PAIRS} | {p[2] for p in PAIRS}:
            if label == LINUX:
                continue
            p = Path(directory) / label / "{}.npz".format(name)
            if not p.is_file():
                raise Stop(2, "{}: no collection {}".format(name, p))
            sides[label] = load(p)
        parts = []
        for pair, first, second in PAIRS:
            r = ratios(sides[first], sides[second], ref)
            vid = max(r, key=r.get)
            worst_all = max(worst_all, r[vid])
            over = sorted(v for v, x in r.items() if x > 1)
            rows.append("| {} | {} | {} | {:.3g} | {} |".format(name, pair, len(r), r[vid], vid))
            parts.append("{} {:.3g} ({}){}".format(pair, r[vid], vid, "; over 1: {}".format(over) if over else ""))
        lines.append("{}: {} variants, largest ratio {}".format(name, len(ref["ids"]), ", ".join(parts)))
    text = "\n".join(rows + [""] + lines)
    print(text)
    if report:
        Path(report).write_text(text + "\n")
    return worst_all


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect", help="evaluate the sample with this build")
    p.add_argument("refs")
    p.add_argument("family", nargs="*")
    p.add_argument("--label", required=True, help="mac-serial or mac-noopt")
    p.add_argument("--out", required=True)
    p.add_argument("--build", required=True, help="JSON: the build record")
    p = sub.add_parser("check", help="the serial pairs against the default's tol_i")
    p.add_argument("refs")
    p.add_argument("dir")
    p.add_argument("family", nargs="*")
    p.add_argument("--report")
    args = parser.parse_args(argv[1:])
    try:
        if args.cmd == "collect":
            collect(args.refs, args.label, args.out, args.build, args.family)
            return 0
        worst = check(args.refs, args.dir, args.family, args.report)
    except Stop as e:
        print(str(e), file=sys.stderr)
        return e.code
    if worst > 1:
        print("a variant's spread exceeds the default's tol_i: the epic owner decides (decision 23)", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
