"""Sketch sensitivity of the sketch-store families (epic AIUE-9, PRD section 7.11 (d); AIUE-92).

Usage:
    python sketch_sensitivity.py run <family>... (--from-collection DIR | --from-store) [--collections DIR]
                                     [--json FILE] [--report FILE] [--toml FILE]

The sketch comparator (harness/store.py, sketch_compare) passes a block b while every projection difference
|<new - ref, r_j>| stays within delta_b = c * sqrt(fsum(tol_i^2 over b)). A change of one entry i by delta moves every
projection of its block by +-delta, so the smallest detectable single-entry change of block b is delta_b, whichever
entry changes. Per family, configuration and block (equation, species, region) this reports:

    entry threshold  delta_b, analytic, confirmed by bisection with sketch_compare on the block alone at the
                     rows of test_thresholds' picks (to 1e-3 relative); |measured/analytic - 1| > 1e-2 is a
                     harness error (exit 2)
    ratio            R_i = delta_b / tol_i, how many of its own tolerances an entry must move to be seen: N, c*sqrt(N)
                     (R for a uniform tol), min/median/max R and the entry with the largest R
    cell multiple    a single-cell change moves every entry at one (ix, iy) by m * its own tol_e (owner, 2026-10-22,
                     AIUE-92 D5); m(ix, iy) = min over the blocks b holding the cell's entries of
                     delta_b / max_j |sum_e r_j,e tol_e| (one entry per block: delta_b / tol_e), with the block that
                     fires first; reported per region, the worst cell
    round-off        with --collections (measure_roundoff.py's collections directory): per serial pair and block,
                     max_j |<d, r_j>| / delta_b for d the pair's yldot difference and its Jacobian-flag difference
                     difference; a ratio >= 1 means c is too small for the measured round-off (exit 3)

The tolerances are those of test_default.py: compare.tolerances(ref, sigma, rtol, k, imap) with ref the release-grade
default, sigma families/<f>/sigma.h5 and rtol, k from tolerances.toml. --from-collection DIR reads the default from
DIR/<family>.<config>.1.pkl (a measure_roundoff collection, the linux-serial label before the reference file exists);
--from-store reads it from the family's reference file (open_store). The owner sets R_max from this table (D3).
Pure Python: no evaluation, no uedge import. Exit codes: 0 ok, 2 usage or harness error, 3 a finding for the owner.
"""
import argparse
import json
import math
import pickle
import sys
import tomllib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package
from yldot.harness import CONFIGS, FAMILIES, FamilyError, compare, open_store, store  # noqa: E402
from yldot.harness.process import family_dir  # noqa: E402

SUITE = Path(__file__).resolve().parents[1]
SEED_PICKS = 89  # test_thresholds.py's: the seed selects rows only
BISECT_RTOL = 1e-3
AGREE_RTOL = 1e-2
# the serial pairs of measure_roundoff.py (PRD section 7.7): (name, first label, first run, second label, second run)
SERIAL_LABELS = ("mac-serial", "mac-noopt", "linux-serial")
SERIAL_PAIRS = tuple(("same_build:" + label, label, "1", label, "2") for label in SERIAL_LABELS) + (
    ("o0_vs_o3", "mac-noopt", "1", "mac-serial", "1"),
    ("mac_vs_linux", "linux-serial", "1", "mac-serial", "1"))


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- the math


def sketch_thresholds(tol, labels, rows, imap, c=store.C, seed=store.SEED, k=store.K):
    """(delta, cell): delta[b] = c * sqrt(fsum(tol^2 over block b)), the smallest single-entry change block b's sketch
    detects; cell {(ix, iy): (m, b)}, the smallest multiple m of each entry's own tol that a change of every entry at
    (ix, iy) needs to fail some block, and the block b that fails first (D5)."""
    tol = np.asarray(tol, dtype=np.float64)
    if tol.shape != (imap.neq,) or not (np.isfinite(tol).all() and (tol > 0).all()):
        raise ValueError("tol must have shape ({},) and be finite and > 0 at every entry".format(imap.neq))
    delta = np.array([c * math.sqrt(store.fsum(tol[r] ** 2)) for r in rows])
    cell = {}
    for b, (label, r) in enumerate(zip(labels, rows)):
        r = np.asarray(r)
        s = store.signs(seed, label, len(r), k).astype(np.float64)
        keys = list(zip(imap.ix[r].tolist(), imap.iy[r].tolist()))
        uniq = sorted(set(keys))
        pos = {key: n for n, key in enumerate(uniq)}
        where = np.array([pos[key] for key in keys])
        moved = np.zeros((len(uniq), k))  # per cell, sum_e r_j,e tol_e over its entries in this block
        np.add.at(moved, where, (s * tol[r]).T)
        m = delta[b] / np.abs(moved).max(axis=1)
        for key, mb in zip(uniq, m.tolist()):
            if key not in cell or mb < cell[key][0]:
                cell[key] = (mb, b)
    return delta, cell


def picks(labels, rows, ref):
    """{block label: sorted 0-based rows}, test_thresholds.py's rule: first, last, largest and smallest |ref_i|, and
    two from a generator seeded with (SEED_PICKS, block number)."""
    out = {}
    for b, (label, r) in enumerate(zip(labels, rows)):
        a = np.abs(ref[r])
        chosen = {r[0], r[-1], r[int(np.argmax(a))], r[int(np.argmin(a))]}
        chosen.update(np.random.default_rng([SEED_PICKS, b]).choice(r, size=min(2, len(r)), replace=False))
        out[label] = sorted(int(i) for i in chosen)
    return out


def bisect_threshold(ref, i, b, tol, labels, rows, imap, guess, c=store.C):
    """The smallest change of entry i that sketch_compare fails on block b alone, by bisection to BISECT_RTOL."""
    lab, r = [labels[b]], [rows[b]]
    refsk = store.sketch(ref, lab, r)

    def fails(d):
        x = ref.copy()
        x[i] += d
        return not store.sketch_compare(refsk, store.sketch(x, lab, r), tol, lab, r, imap, c=c).ok

    lo, hi = 0.0, 2.0 * guess
    while not fails(hi):
        lo, hi = hi, 2.0 * hi
        if hi > 1e6 * guess:
            raise Stop(2, "{}: no change up to 1e6 x the analytic threshold fails".format(imap.label(i)))
    while hi - lo > BISECT_RTOL * hi:
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if fails(mid) else (mid, hi)
    return hi


def roundoff_ratios(a, b, delta, labels, rows, seed=store.SEED, k=store.K):
    """Per block, max_j |<a - b, r_j>| / delta_b for yldot and for the flag difference yldot_J - yldot."""
    out = {}
    for part, va, vb in (("yldot", a["yldot"], b["yldot"]),
                         ("flag difference", np.asarray(a["yldot_J"]) - np.asarray(a["yldot"]),
                          np.asarray(b["yldot_J"]) - np.asarray(b["yldot"]))):
        sa, sb = store.sketch(va, labels, rows, seed, k), store.sketch(vb, labels, rows, seed, k)
        out[part] = np.abs(sa["proj"] - sb["proj"]).max(axis=1) / delta
    return out


# ---------------------------------------------------------------- per family


def load_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def sigma_h5(family, config):
    import h5py

    path = FAMILIES / family / "sigma.h5"
    if not path.is_file():
        raise Stop(2, "{}: no {} (measure_roundoff.py analyze --write writes it)".format(family, path))
    with h5py.File(path, "r") as f:
        return f[config]["sigma"][()]


def default_from_collection(directory, family, config):
    path = Path(directory) / "{}.{}.1.pkl".format(family, config)
    try:
        with open(path, "rb") as f:
            r = pickle.load(f)
    except OSError as e:
        raise Stop(2, "{}: {}".format(path, e))
    if r.get("status") != "ok":
        raise Stop(2, "{}: status {}".format(path, r.get("status")))
    regions = compare.load_regions(family_dir(family))
    return np.asarray(r["yldot"], dtype=np.float64), compare.index_map(r, regions), r


def analyze(family, config, ref, sigma, imap, tol_toml, collections=None):
    """The (d) table of one family and configuration as a dict; findings in its 'owner' and 'errors' lists."""
    t = compare.tolerances(ref, sigma, tol_toml["rtol"], tol_toml["rule"]["k"], imap).tol
    labels, rows, _ = store.blocks(imap)
    delta, cell = sketch_thresholds(t, labels, rows, imap)
    out = {"family": family, "config": config, "neq": int(imap.neq), "c": store.C, "blocks": [], "regions": {},
           "roundoff": {}, "errors": [], "owner": []}
    chosen = picks(labels, rows, ref)
    for b, (label, r) in enumerate(zip(labels, rows)):
        ratio = delta[b] / t[r]
        worst = int(r[int(np.argmax(ratio))])
        agree = []
        for i in chosen[label]:
            measured = bisect_threshold(ref, i, b, t, labels, rows, imap, delta[b])
            agree.append(measured / delta[b] - 1.0)
            if abs(measured / delta[b] - 1.0) > AGREE_RTOL:
                out["errors"].append("{} {}: {} bisection {:.6e} vs analytic {:.6e}".format(
                    family, config, imap.label(i), measured, delta[b]))
        out["blocks"].append({
            "block": label, "n": len(r), "delta": float(delta[b]), "c_sqrt_n": store.C * math.sqrt(len(r)),
            "r_min": float(ratio.min()), "r_median": float(np.median(ratio)), "r_max": float(ratio.max()),
            "worst": imap.label(worst), "bisection_max_dev": float(max(abs(a) for a in agree))})
    for (ix, iy), (m, b) in sorted(cell.items()):
        region = imap.region[rows[b][0]]
        cur = out["regions"].get(region)
        if cur is None or m > cur["m"]:
            out["regions"][region] = {"m": float(m), "ix": int(ix), "iy": int(iy), "fires": labels[b]}
    out["cell_m_median"] = float(np.median([m for m, _ in cell.values()]))
    if collections is not None:
        for name, la, ra, lb, rb in SERIAL_PAIRS:
            a, b = collections.get((la, ra)), collections.get((lb, rb))
            if a is None or b is None or a.get("status") != "ok" or b.get("status") != "ok":
                out["errors"].append("{} {}: pair {} not collected".format(family, config, name))
                continue
            ratios = roundoff_ratios(a, b, delta, labels, rows)
            worst = {part: (float(v.max()), labels[int(np.argmax(v))]) for part, v in ratios.items()}
            out["roundoff"][name] = {part: {"max": w, "block": lab} for part, (w, lab) in worst.items()}
            for part, (w, lab) in worst.items():
                if w >= 1.0:
                    out["owner"].append("{} {}: round-off {} {} block {} reaches {:.3g} of the sketch bound".format(
                        family, config, name, part, lab, w))
    return out


def load_collections(directory, family, config):
    """{(label, run): result} of the serial labels' runs of one family and configuration."""
    out = {}
    for label in SERIAL_LABELS:
        for run in ("1", "2"):
            path = Path(directory) / label / "{}.{}.{}.pkl".format(family, config, run)
            if path.is_file():
                with open(path, "rb") as f:
                    out[(label, run)] = pickle.load(f)
    return out


def run(families, args):
    tol_toml = load_toml(args.toml)
    tables = []
    for family in families:
        try:
            fdir = family_dir(family)
        except FamilyError as e:
            raise Stop(2, str(e))
        if load_toml(fdir / "family.toml")["family"].get("store") != "sketch":
            raise Stop(2, "{}: not a sketch-store family".format(family))
        for config in CONFIGS:
            if args.from_store:
                with open_store(family) as s:
                    ref, sigma, imap = np.array(s.default(config)), np.array(s.sigma(config)), s.imap
            else:
                ref, imap, _ = default_from_collection(args.from_collection, family, config)
                sigma = sigma_h5(family, config)
            coll = load_collections(args.collections, family, config) if args.collections else None
            tables.append(analyze(family, config, ref, sigma, imap, tol_toml, coll))
    return tables


# ---------------------------------------------------------------- report


def report(tables):
    lines = ["# Sketch sensitivity (PRD 7.11 (d))", "",
             "R = delta_b / tol_i: how many of its own tolerances one entry must move before its block's sketch fails "
             "(c = {}); c*sqrt(N) is R for a uniform tol. m: the same for a whole cell (D5).".format(store.C), ""]
    for t in tables:
        lines += ["## {} {} (neq {}, {} blocks)".format(t["family"], t["config"], t["neq"], len(t["blocks"])), "",
                  "| block | N | c*sqrt(N) | R min | R median | R max | worst entry |", "|---|---|---|---|---|---|---|"]
        for b in t["blocks"]:
            lines.append("| {} | {} | {:.0f} | {:.3g} | {:.3g} | {:.3g} | {} |".format(
                b["block"], b["n"], b["c_sqrt_n"], b["r_min"], b["r_median"], b["r_max"], b["worst"]))
        lines += ["", "Worst cell per region (median m over all cells {:.3g}):".format(t["cell_m_median"]), "",
                  "| region | m | ix | iy | fires first |", "|---|---|---|---|---|"]
        for region, w in sorted(t["regions"].items()):
            lines.append("| {} | {:.3g} | {} | {} | {} |".format(region, w["m"], w["ix"], w["iy"], w["fires"]))
        if t["roundoff"]:
            lines += ["", "Round-off against the sketch bound (max_j |<d, r_j>| / delta_b, worst block):", "",
                      "| pair | yldot | block | flag difference | block |", "|---|---|---|---|---|"]
            for name, r in t["roundoff"].items():
                lines.append("| {} | {:.3g} | {} | {:.3g} | {} |".format(
                    name, r["yldot"]["max"], r["yldot"]["block"], r["flag difference"]["max"],
                    r["flag difference"]["block"]))
        lines.append("")
    return "\n".join(lines)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="the (d) table of each sketch-store family")
    p.add_argument("family", nargs="+")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-collection", help="a measure_roundoff label directory holding the default")
    src.add_argument("--from-store", action="store_true", help="the family's reference file")
    p.add_argument("--collections", help="measure_roundoff collections directory: the round-off re-check of c")
    p.add_argument("--json", help="write the tables here")
    p.add_argument("--report", help="write the markdown report here")
    p.add_argument("--toml", default=str(SUITE / "tolerances.toml"))
    args = parser.parse_args(argv[1:])
    try:
        tables = run(args.family, args)
    except Stop as stop:
        print(str(stop), file=sys.stderr)
        return stop.code
    text = report(tables)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(tables, f, indent=1)
    errors = [m for t in tables for m in t["errors"]]
    owner = [m for t in tables for m in t["owner"]]
    for m in errors:
        print("ERROR: " + m, file=sys.stderr)
    for m in owner:
        print("OWNER: " + m, file=sys.stderr)
    return 2 if errors else 3 if owner else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
