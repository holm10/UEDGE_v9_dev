"""AIUE-56 C1 gate: magnitude and deviation bounds on OpenMP Jacobians vs the serial reference.

Usage: python AIUE-56-c1-gate.py [--harness DIR] CHECKDIR [CHECKDIR ...]

--harness: the tests/deterministic_omp directory of the reviewed harness core (for check_arm); without it the
check_arm result is taken from the harness on this branch if present, else reported as "not checked".

Each CHECKDIR is a `tests/deterministic_omp/harness/cli.py check` output directory (serial/ and run*/ with
record.npz + record.json). For every OpenMP run and every Jacobian both records hold (captured[k] if present,
else post_exmain), the gate requires (pre-registered in .claude/plans/AIUE-56-omp-jacobian-fix.md):

  magnitude: max |J| over the Te rows <= 10 x the serial reference's
  deviation: every mismatching entry (value mismatch, or present on one side only with the absent side = 0)
             has |a - b| <= 1e-6 x max |J| of that serial row

It also requires each run's check_arm list to be empty (the arm took effect). Prints one line per run and
"GATE PASS"/"GATE FAIL"; exit 0 / 1, or 2 if a directory can't be read.

Note (AIUE-57, after the OpenMP determinism merge): when the build has the AIUE-47 capture hook this script judges
the raw captured[k] Jacobians, which are unscaled; the bound is defined on the scaled post_exmain Jacobian
(decision in docs/reviews/omp-determinism-merge-validation.txt). Use tests/deterministic_omp/ci/jac_bound.py, which
applies the same bound to post_exmain only. This script is kept unchanged so the records that quote it reproduce.
"""
import json
import os
import sys

import numpy as np

TE = 2  # index of "te" in the harness EQ_CODES


def load(rundir):
    with open(os.path.join(rundir, "record.json")) as f:
        meta = json.load(f)
    with np.load(os.path.join(rundir, "record.npz")) as data:
        arrays = {k: data[k] for k in data.files}
    return meta, arrays


def matrices(meta, arrays):
    out = []
    for k in range(int(meta.get("capture", {}).get("count", 0))):
        out.append(("captured[{}]".format(k), arrays["capjac_{}".format(k)], arrays["capjacj_{}".format(k)],
                    arrays["capjaci_{}".format(k)], True))
    out.append(("post_exmain", arrays["jac_post"], arrays["jacj_post"], arrays["jaci_post"],
                not meta.get("post_exmain_permuted", False)))
    return out


def as_dict(vals, cols, ptr):
    """{(row, col): value}, 0-based; also the row of every entry."""
    ptr = np.asarray(ptr, dtype=np.int64)
    rows = np.repeat(np.arange(len(ptr) - 1), np.diff(ptr))
    return rows, np.asarray(cols, dtype=np.int64) - 1, np.asarray(vals, dtype=np.float64)


def gate(serial, run):
    smeta, sarr = serial
    rmeta, rarr = run
    neq = smeta["neq"]
    eq = sarr["eq"]
    problems = []
    worst = {"magnitude": 0.0, "deviation": 0.0}
    ms, mr = matrices(smeta, sarr), matrices(rmeta, rarr)
    if [m[0] for m in ms] != [m[0] for m in mr]:
        problems.append("different Jacobians: serial {} vs run {}".format([m[0] for m in ms], [m[0] for m in mr]))
        return problems, worst
    for (name, sv, sj, si, loc), (_, rv, rj, ri, _) in zip(ms, mr):
        srow, scol, sval = as_dict(sv, sj, si)
        rrow, rcol, rval = as_dict(rv, rj, ri)
        rowmax = np.zeros(neq)
        np.maximum.at(rowmax, srow, np.abs(sval))
        te_rows = eq == TE
        if loc:
            s_te = np.abs(sval[te_rows[srow]]).max(initial=0.0)
            r_te = np.abs(rval[te_rows[rrow]]).max(initial=0.0)
        else:  # permuted post-exmain matrix: rows are not equations; use all rows
            s_te, r_te = np.abs(sval).max(initial=0.0), np.abs(rval).max(initial=0.0)
        ratio = r_te / s_te if s_te > 0 else (np.inf if r_te > 0 else 0.0)
        worst["magnitude"] = max(worst["magnitude"], ratio)
        if ratio > 10:
            problems.append("{}: max|J| Te rows {:.3e} vs serial {:.3e} (x{:.3g})".format(name, r_te, s_te, ratio))
        ks = srow * neq + scol
        kr = rrow * neq + rcol
        allk = np.union1d(ks, kr)
        a = np.zeros(len(allk))
        b = np.zeros(len(allk))
        a[np.searchsorted(allk, ks)] = sval
        b[np.searchsorted(allk, kr)] = rval
        diff = np.abs(a - b)
        bad = diff > 0
        if loc:
            bound = 1e-6 * rowmax[allk // neq]
        else:
            bound = np.full(len(allk), 1e-6 * np.abs(sval).max(initial=0.0))
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = np.where(bound > 0, diff / bound, np.where(diff > 0, np.inf, 0.0))
        worst["deviation"] = max(worst["deviation"], float(rel.max(initial=0.0)) * 1e-6)
        over = int(np.count_nonzero(rel > 1.0))
        if over:
            problems.append("{}: {} entries exceed 1e-6 x serial row max (worst |a-b|/rowmax {:.3e}; {} entries "
                            "differ)".format(name, over, float(rel.max()) * 1e-6, int(bad.sum())))
    return problems, worst


HARNESS = [os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests",
                                          "deterministic_omp"))]


def check_arm_problems(rundir):
    sys.path.insert(0, HARNESS[0])
    try:
        from harness.compare import check_arm
        from harness.runner import Record
    except ImportError:
        return None  # harness not on this branch: the caller records check_arm separately
    return check_arm(Record(rundir))


def main(dirs):
    code = 0
    for d in dirs:
        try:
            serial = load(os.path.join(d, "serial"))
            runs = sorted(r for r in os.listdir(d) if r.startswith("run"))
            for r in runs:
                problems, worst = gate(serial, load(os.path.join(d, r)))
                arm = check_arm_problems(os.path.join(d, r))
                if arm is None:
                    problems.append("check_arm: not checked (no harness found)")
                elif arm:
                    problems += ["check_arm: " + p for p in arm]
                status = "PASS" if not problems else "FAIL"
                code = max(code, 0 if status == "PASS" else 1)
                print("{} {}: {} (worst magnitude ratio {:.3g}, worst |a-b|/rowmax {:.3g}){}".format(
                    d, r, status, worst["magnitude"], worst["deviation"],
                    "" if not problems else "\n    " + "\n    ".join(problems)))
        except (OSError, KeyError, ValueError) as err:
            print("{}: cannot read: {}".format(d, err))
            code = 2
    print("GATE " + {0: "PASS", 1: "FAIL", 2: "ERROR"}[code])
    return code


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--harness"]:
        HARNESS[0] = os.path.abspath(args[1])
        args = args[2:]
    sys.exit(main(args))
