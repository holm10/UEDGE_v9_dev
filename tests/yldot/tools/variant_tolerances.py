"""Check how stored SENSITIVE variants reproduce on other builds (epic AIUE-9, PRD section 7.4; owner, 2026-10-22,
AIUE-94 D2 and D8).

Usage:
    <build's python> variant_tolerances.py replay REFS [--build FILE] [--json FILE] [family ...]
    <build's python> variant_tolerances.py collect REFS --label L --out DIR --build FILE [family ...]
    python variant_tolerances.py check REFS DIR [--report FILE] [family ...]

replay   the population check (review I1-B1, D8): every SENSITIVE variant of REFS, each once with this build in a
         fresh child, its recorded applied value replayed, checked against its stored reference through Store.check,
         yldot and the flag difference, with tol_i(variant) = max(rtol_eq*|ref_i(variant)|, k*sigma_i)
         (make_references.variant_tolerance: the PRD 7.4 rule with the variant's own reference and the default's
         sigma_i). REFS: a make_references.py run's --out DIR/references (<family>.h5 and <family>.json) or
         "installed" (tests/yldot/references); default families: every one REFS holds with classified variants.
         Prints per family the count, the failures (a failed evaluation is one) and the largest
         max |d_i| / tol_i(variant) (inf for a non-finite entry); --json writes every row; --build refuses
         references of another commit than FILE's.
collect and check: the seeded sample (D2) under the default's tol_i. For them REFS is the references directory of a
make_references.py run (--out DIR/references): <family>.json (the manifest fields, with each variant's applied
value) and samples/<family>.npz, the sample its child drew (make_references.tolerance_sample: the 20 SENSITIVE ids
with the smallest sha256("<seed>:<id>") plus every SENSITIVE timestep id) with that build's yldot, yldot_J, the
default's tol_<config> and the index arrays.
collect  runs inside one build's venv: each sampled variant once, in a fresh child, with its recorded applied value
         replayed (Runner.evaluate(..., replay=)), into DIR/L/<family>.npz. FILE is the build record (JSON: commit,
         options, compiler, ...); collect refuses a REFS whose provenance commit is not FILE's.
check    pairs the sides, the REFS run as linux-serial (the release-grade run of make_references.py) and the labels
         in DIR: mac_vs_linux (linux-serial against mac-serial) and o0_vs_o3 (mac-noopt against mac-serial), the
         serial pairs of measure_roundoff.py (AIUE-87). Per family, pair and variant, the largest |d_i| / tol_i over
         yldot and yldot_J, a non-finite entry in either inf. It passes iff every ratio is <= 1 (the test rule,
         decision 27); the largest is reported. A sample is 20-27 of ~300 SENSITIVE variants per family: it does not
         show that the population inherits the default's tol_i (review I1-M1); replay checks the population.

Exit codes: 0 every check passes; 2 usage, a missing side, references of another commit or (collect) a failed
evaluation; 3 a replay failure, a ratio above 1 or index arrays that differ between the builds: the epic owner
decides (decision 23), nothing is loosened.
"""
import argparse
import contextlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package

import numpy as np  # noqa: E402

from yldot.harness.state import INDEX_ARRAYS  # noqa: E402

LINUX = "linux-serial"
PAIRS = (("mac_vs_linux", LINUX, "mac-serial"), ("o0_vs_o3", "mac-noopt", "mac-serial"))
TIMEOUT_FACTOR = 5  # as make_references.py
INSTALLED = "installed"  # replay's REFS for tests/yldot/references


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


def worst(diff, tol):
    """max_i |diff_i| / tol_i, inf if any entry is not finite (a NaN in either term fails, review I1-m3)."""
    with np.errstate(invalid="ignore", over="ignore", divide="ignore"):
        r = np.abs(np.asarray(diff, dtype=np.float64)) / tol
    if not r.size:
        return 0.0
    return float(r.max()) if np.isfinite(r).all() else float("inf")


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
        out[vid] = max(worst(a[w][k] - b[w][k], tol) for w in ("yldot", "yldot_J"))
    return out


# ---------------------------------------------------------------- replay: every stored SENSITIVE variant (D8)


@contextlib.contextmanager
def reference_stores(refs, families):
    """{family: open Store} of REFS: "installed" (tests/yldot/references) or a make_references.py --out DIR/references
    directory (<family>.h5 and <family>.json, the manifest without release and external), opened through open_store
    from a scratch suite that links the file, so every SHA-256 and derived-field check applies."""
    from yldot.harness import open_store
    from yldot.harness import manifest as mf
    from yldot.harness.compare import load_regions
    from yldot.harness.process import family_dir
    from yldot.harness.store import file_sha256

    stores = {}
    with tempfile.TemporaryDirectory(prefix="yldot-replay-") as tmp, contextlib.ExitStack() as stack:
        if refs == INSTALLED:
            suite = mf.SUITE
            found = sorted(p.name.split(".")[0] for p in (suite / "references").glob("*.manifest.json")
                           if mf.load(p).get("variables"))
        else:
            src = Path(refs).resolve()
            found = sorted(p.stem for p in src.glob("*.json") if (src / "{}.h5".format(p.stem)).is_file())
            suite = Path(tmp)
            (suite / "references").mkdir()
        missing = sorted(set(families) - set(found))
        if missing or not found:
            raise Stop(2, "{}: no references with classified variants for {}".format(refs, missing or "any family"))
        for name in list(families) or found:
            if refs != INSTALLED:
                h5 = src / "{}.h5".format(name)
                m = json.loads((src / "{}.json".format(name)).read_text())
                m["release"] = None
                m["external"] = {mf.reference_path(name): {"sha256": file_sha256(h5), "bytes": h5.stat().st_size}}
                (suite / mf.reference_path(name)).symlink_to(h5)
                mf.dump(m, mf.path(name, suite))
            stores[name] = stack.enter_context(open_store(name, suite, regions=load_regions(family_dir(name))))
        yield stores


def replay_family(name, s, runner, plan, timeout):
    """{id: row} for every SENSITIVE variant of the open store s: the variant evaluated once with this build, in a
    fresh child, its recorded applied value replayed, and checked against its stored reference with
    make_references.variant_tolerance (D8) through Store.check, yldot and the flag difference. A row: ok, ratio
    (the largest |d_i| / tol_i(variant) over both, inf for a non-finite entry) and, for a failed evaluation,
    status and message."""
    import make_references as mr
    from yldot.harness import compare
    from yldot.harness.process import family_dir

    if s.kind != "full":
        raise Stop(2, "{}: a {} store holds no dense variant reference, D8's rtol term needs one".format(name, s.kind))
    fdir = family_dir(name)
    rows = {}
    for vid, e in s.manifest["variables"].items():
        if e["class"] != "SENSITIVE":
            continue
        if vid not in plan:
            raise Stop(2, "{} {}: not in this inventory (prune it first, AIUE-95)".format(name, vid))
        r = runner.evaluate(name, variant=plan[vid], replay=e["applied"], timeout=timeout)
        if not r.ok:
            rows[vid] = {"ok": False, "ratio": float("inf"), "status": r.status, "message": mr.error_reason(r)}
            continue
        config = e["config"]
        ref, ref_j = s.variant(config, vid)
        tol = mr.variant_tolerance(fdir, ref, config, s.imap)
        y, yj = r.data["yldot"], r.data["yldot_J"]
        ratio = max(worst(y - ref, tol), worst((yj - y) - ref_j, tol))
        chk = s.check(config, vid, y, yj, tol, compare.index_map(r.data, compare.load_regions(fdir)))
        rows[vid] = {"ok": bool(chk.ok) and ratio <= 1, "ratio": ratio}
    return rows


def replay(refs, families, build=None, out=None):
    """Replay every SENSITIVE variant of REFS with this build (D8); prints per family the count, the failures and
    the largest ratio; out: the rows as JSON. Returns the number of failures."""
    from yldot.harness import Runner, load_evaluation, variants
    from yldot.harness.process import family_dir

    rec = json.loads(Path(build).read_text()) if build else None
    plan = {v.id: v for v in variants.plan()}
    runner = Runner()
    result, failures = {}, 0
    with reference_stores(refs, families) as stores:
        for name, s in stores.items():
            if rec is not None and s.manifest["provenance"]["commit"] != rec["commit"]:
                raise Stop(2, "{}: the references are of {}, this build of {}".format(
                    name, s.manifest["provenance"]["commit"], rec["commit"]))
            timeout = TIMEOUT_FACTOR * float(load_evaluation(family_dir(name))["timeout_s"])
            rows = replay_family(name, s, runner, plan, timeout)
            bad = sorted((vid for vid, x in rows.items() if not x["ok"]), key=lambda vid: -rows[vid]["ratio"])
            failures += len(bad)
            top = max(rows, key=lambda vid: rows[vid]["ratio"]) if rows else None
            print("{}: {} SENSITIVE replayed, {} fail, largest ratio {}{}".format(
                name, len(rows), len(bad), "{:.3g} ({})".format(rows[top]["ratio"], top) if top else "-",
                "; failing: " + ", ".join("{} {:.3g}{}".format(vid, rows[vid]["ratio"], " " + rows[vid]["message"]
                                                               if "message" in rows[vid] else "") for vid in bad)
                if bad else ""), flush=True)
            result[name] = rows
    if out:
        Path(out).write_text(json.dumps({"refs": str(refs), "build": rec, "families": result}, indent=1,
                                        sort_keys=True) + "\n")
    return failures


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
    p = sub.add_parser("replay", help="every SENSITIVE variant with this build, under tol_i(variant) (D8)")
    p.add_argument("refs", help="a make_references.py --out DIR/references directory, or 'installed'")
    p.add_argument("family", nargs="*")
    p.add_argument("--build", help="JSON: the build record; refuses references of another commit")
    p.add_argument("--json", help="write the rows here")
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
        if args.cmd == "replay":
            failures = replay(args.refs, args.family, args.build, args.json)
            if failures:
                print("{} stored SENSITIVE variants not reproduced within tol_i(variant): the epic owner decides "
                      "(decision 23)".format(failures), file=sys.stderr)
                return 3
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
