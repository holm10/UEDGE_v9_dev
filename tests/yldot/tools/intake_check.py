"""Intake residual check of the yldot families (epic AIUE-9, PRD section 7.1, decision 20).

Usage (from anywhere):
    python intake_check.py [family ...] [--worst N] [--out DIR]

For each family (default: all) it evaluates the unperturbed reference_state.h5 with nksol's scaling (issfon = 1;
the harness's intake configuration) and prints s_i = |sfscal*yldot|_i: the convergence norm max(s) next to the case's
ftol and the fmax recorded in family.toml, the L2 norm, then per (equation, species) block and per region the row
count, median, max and the rows above ftol, and the N worst rows with their equation, species, cell and region.
Guard rows are included like every other row.

It flags nothing by itself: the epic owner judges each family from these tables (owner, 2026-10-20, AIUE-83 ticket
page). A row is never masked. Rows, cells and regions come only from UEDGE's index arrays and the owner-confirmed
[regions] of family.toml (harness/compare.py).

--out DIR writes <family>_intake.npz (s, yldot, sfscal, eq, species, ix, iy, region) for the record.

Exit codes: 0 done, 2 an evaluation failed, 3 max(s) differs from the recorded fmax by more than 1e-3 relative,
4 the index map or the regions failed (ask the epic owner).
"""
import argparse
import sys
import tomllib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package

from yldot.harness import FAMILIES, INTAKE, Runner  # noqa: E402
from yldot.harness.compare import REGIONS, IndexTruthError, index_map, load_regions  # noqa: E402

FMAX_RTOL = 1e-3  # family.toml records fmax to 5 significant digits


def table(title, keys, groups, s, ftol):
    print("  {:14s} {:>5s} {:>10s} {:>10s} {:>8s}".format(title, "rows", "median", "max", ">ftol"))
    for key in keys:
        rows = groups.get(key)
        if rows is None or not rows.size:
            continue
        v = s[rows]
        name = key if isinstance(key, str) else "{}[{}]".format(*key)
        print("  {:14s} {:5d} {:10.3e} {:10.3e} {:8d}".format(name, rows.size, np.median(v), v.max(),
                                                              int((v > ftol).sum())))


def check(runner, family, worst, out):
    toml = FAMILIES / family / "family.toml"
    with open(toml, "rb") as f:
        recorded = tomllib.load(f).get("reference_state", {})
    res = runner.evaluate(family, config=INTAKE)
    if not res.ok:
        print("{}: {} {}\n{}".format(family, res.status, res.message, res.log_tail))
        return 2
    d = res.data
    try:
        imap = index_map(d, load_regions(family))
    except IndexTruthError as e:
        print("{}: {}".format(family, e))
        return 4
    s = np.abs(d["sfscal"] * d["yldot"])
    ftol = float(recorded.get("ftol", d["ftol_case"]))
    fmax, fnrm = float(s.max()), float(np.sqrt(np.sum(s ** 2)))
    code = 0
    line = "{}: neq={} ftol={:.1e} max(s)={:.4e} L2={:.4e} rows>ftol={}".format(
        family, imap.neq, ftol, fmax, fnrm, int((s > ftol).sum()))
    if "fmax" in recorded:
        rel = abs(fmax - recorded["fmax"]) / abs(recorded["fmax"])
        line += " recorded fmax={:.4e}".format(recorded["fmax"])
        if rel > FMAX_RTOL:
            line += " MISMATCH ({:.1e} relative): ask the epic owner".format(rel)
            code = 3
    if float(d["ftol_case"]) != ftol:
        line += " (input.py ftol={:.1e})".format(float(d["ftol_case"]))
    print(line)
    blocks = imap.blocks()
    table("block", list(blocks), blocks, s, ftol)
    regions = {r: np.flatnonzero(imap.region == r) for r in REGIONS}
    table("region", REGIONS, regions, s, ftol)
    print("  worst rows:")
    for i in np.argsort(-s, kind="stable")[:worst]:
        print("    {:40s} s={:.3e}".format(imap.label(i), s[i]))
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        np.savez(out / "{}_intake.npz".format(family), s=s, yldot=d["yldot"], sfscal=d["sfscal"], eq=imap.eq,
                 species=imap.species, ix=imap.ix, iy=imap.iy, region=imap.region)
    return code


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("families", nargs="*", help="family names (default: all)")
    parser.add_argument("--worst", type=int, default=10, help="worst rows to list per family")
    parser.add_argument("--out", type=Path, help="directory for <family>_intake.npz")
    args = parser.parse_args(argv[1:])
    names = args.families or sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
    runner = Runner()
    codes = [check(runner, f, args.worst, args.out) for f in names]
    return max(codes) if codes else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
