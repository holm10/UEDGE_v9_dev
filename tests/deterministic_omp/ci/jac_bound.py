"""The C1 bound on the scaled post-exmain Jacobian of OpenMP runs vs their serial reference (AIUE-57).

  python jac_bound.py --flow FLOWDIR [--tol 1e-6] [--json FLOWDIR/bound.json]   # every jac group of a flow
  python jac_bound.py [--harness DIR] [--tol 1e-6] CHECKDIR [CHECKDIR ...]     # cli.py check directories

The bound is AIUE-56's C1 bound (docs/reviews/AIUE-56-c1-gate.py, same arithmetic), applied to the matrix it was
registered on: the scaled `post_exmain` Jacobian (decision in docs/reviews/omp-determinism-merge-validation.txt).
For every OpenMP run against the serial reference of the same configuration:

  magnitude: max |J| over the Te rows <= 10 x the serial reference's
  deviation: every differing entry (value, or present on one side only with the other side = 0) has
             |a - b| <= TOL x max |J| of that serial row

`post_exmain` is the LAST Jacobian of the run: in a one-evaluation run the first and only one; under --itermx N the
last psetnk one, row-normalised and (ireorder=1) permuted, so rows are not equations and the bound uses the global
max |J| instead of the row max (as the AIUE-56 script did). Earlier Jacobians are compared bitwise by the flow.
The raw captured Jacobians (`captured[k]`, AIUE-47 hook) are NOT judged: they are unscaled (their row max mixes
column units); their worst raw |a-b|/rowmax is printed for information only.

Fail closed: a serial and a run that disagree on which matrix post_exmain is (`post_exmain_permuted`,
`post_exmain_from`), an unreadable record, a missing serial reference, or any unexpected exception is exit 2.
A run without a record (it crashed) is skipped: the flow already counts it as a failure.

Flow mode looks at `<config>/jac_t<N>/run<k>` against `<config>/serial` (other arms, e.g. jacrhs_t<N>, are ignored)
and writes --json (default FLOWDIR/bound.json):
  {"tol": T, "matrix": "post_exmain", "exit_code": N,
   "groups": {"<config>/jac_t<N>": {"error": null | "...",
                                    "runs": {"run<k>": {"pass": bool, "worst_ratio": x, "worst_dev": x, "over": n,
                                                        "differ": n, "permuted": bool, "raw": [...],
                                                        "problems": [...]}
                                             | {"skipped": "..."} | {"error": "..."}}}}}
Check-dir mode (the AIUE-56 script's interface; `linux/gate_flows.py` passes --harness) also requires each run's
check_arm list (from --harness; default: the harness next to this script) to be empty.

Exit code: 0 every judged run within the bound, 1 a run outside it, 2 cannot judge.
"""
import argparse
import json
import os
import sys
import traceback

import numpy as np

TE = 2  # index of "te" in the harness EQ_CODES
DEFAULT_TOL = 1e-6  # the registered C1 bound (AIUE-56 plan)
MAX_RATIO = 10.0


class CannotJudge(Exception):
    pass


def load(rundir):
    try:
        with open(os.path.join(rundir, "record.json")) as f:
            meta = json.load(f)
        with np.load(os.path.join(rundir, "record.npz")) as data:
            arrays = {k: data[k] for k in data.files}
    except (OSError, ValueError, KeyError) as err:
        raise CannotJudge("{}: cannot read the record ({})".format(rundir, err))
    return meta, arrays


def has_record(rundir):
    return os.path.exists(os.path.join(rundir, "record.json")) and os.path.exists(os.path.join(rundir, "record.npz"))


def entries(vals, cols, ptr):
    """(rows, cols, values), 0-based, of a CSR matrix with 1-based column indices."""
    ptr = np.asarray(ptr, dtype=np.int64)
    rows = np.repeat(np.arange(len(ptr) - 1), np.diff(ptr))
    return rows, np.asarray(cols, dtype=np.int64) - 1, np.asarray(vals, dtype=np.float64)


def deviation(neq, s, r, loc):
    """(rel, differ): rel = |a-b| / base over the union of both patterns (an absent entry is 0), base = the
    serial row max (loc) or the serial global max; differ = the number of entries with a != b."""
    srow, scol, sval = s
    rrow, rcol, rval = r
    ks = srow * neq + scol
    kr = rrow * neq + rcol
    allk = np.union1d(ks, kr)
    a = np.zeros(len(allk))
    b = np.zeros(len(allk))
    a[np.searchsorted(allk, ks)] = sval
    b[np.searchsorted(allk, kr)] = rval
    diff = np.abs(a - b)
    if loc:
        rowmax = np.zeros(neq)
        np.maximum.at(rowmax, srow, np.abs(sval))
        base = rowmax[allk // neq]
    else:
        base = np.full(len(allk), np.abs(sval).max(initial=0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(base > 0, diff / base, np.where(diff > 0, np.inf, 0.0))
    return rel, int(np.count_nonzero(diff > 0))


def judge(serial, run, tol):
    """One run against its serial reference: a result dict (see the module docstring)."""
    smeta, sarr = serial
    rmeta, rarr = run
    for key in ("post_exmain_permuted", "post_exmain_from"):
        if smeta.get(key) != rmeta.get(key):
            raise CannotJudge("serial and run disagree on {} ({!r} vs {!r}): post_exmain is not the same matrix"
                              .format(key, smeta.get(key), rmeta.get(key)))
    neq = int(smeta["neq"])
    if int(rmeta.get("neq", -1)) != neq:
        raise CannotJudge("serial neq {} vs run neq {}".format(neq, rmeta.get("neq")))
    permuted = bool(smeta.get("post_exmain_permuted", False))
    loc = not permuted
    s = entries(sarr["jac_post"], sarr["jacj_post"], sarr["jaci_post"])
    r = entries(rarr["jac_post"], rarr["jacj_post"], rarr["jaci_post"])
    if loc:
        te_rows = np.asarray(sarr["eq"]) == TE
        s_max = np.abs(s[2][te_rows[s[0]]]).max(initial=0.0)
        r_max = np.abs(r[2][te_rows[r[0]]]).max(initial=0.0)
    else:
        s_max, r_max = np.abs(s[2]).max(initial=0.0), np.abs(r[2]).max(initial=0.0)
    ratio = r_max / s_max if s_max > 0 else (np.inf if r_max > 0 else 0.0)
    rel, differ = deviation(neq, s, r, loc)
    over = int(np.count_nonzero(rel > tol))
    worst = float(rel.max(initial=0.0))
    problems = []
    if ratio > MAX_RATIO:
        problems.append("post_exmain: max|J| {} {:.3e} vs serial {:.3e} (x{:.3g} > {:g})".format(
            "Te rows" if loc else "(permuted, all rows)", r_max, s_max, ratio, MAX_RATIO))
    if over:
        problems.append("post_exmain: {} entries exceed {:g} x serial {} (worst {:.3e}; {} entries differ)".format(
            over, tol, "row max" if loc else "max |J| (permuted)", worst, differ))
    raw = []
    sc, rc = int(smeta.get("capture", {}).get("count", 0)), int(rmeta.get("capture", {}).get("count", 0))
    for k in range(min(sc, rc)):
        try:
            crel, cdiff = deviation(neq, entries(sarr["capjac_{}".format(k)], sarr["capjacj_{}".format(k)],
                                                 sarr["capjaci_{}".format(k)]),
                                    entries(rarr["capjac_{}".format(k)], rarr["capjacj_{}".format(k)],
                                            rarr["capjaci_{}".format(k)]), True)
            raw.append({"k": k, "worst_dev": float(crel.max(initial=0.0)), "differ": cdiff})
        except KeyError as err:
            raw.append({"k": k, "note": "missing array {}".format(err)})
    return {"pass": not problems, "worst_ratio": float(ratio), "worst_dev": worst, "over": over, "differ": differ,
            "permuted": permuted, "raw": raw, "problems": problems}


def describe(name, res):
    if "error" in res:
        return "{}: ERROR (cannot judge): {}".format(name, res["error"])
    if "skipped" in res:
        return "{}: skipped ({})".format(name, res["skipped"])
    text = "{}: {} (post_exmain{}: worst magnitude ratio {:.3g}, worst |a-b|/base {:.3g}, {} entries differ)".format(
        name, "PASS" if res["pass"] else "FAIL", ", permuted" if res["permuted"] else "", res["worst_ratio"],
        res["worst_dev"], res["differ"])
    for p in res["problems"]:
        text += "\n    " + p
    for c in res["raw"]:
        if "worst_dev" in c:
            text += ("\n    captured[{}]: raw (unscaled), not judged; the bound is defined on the scaled post_exmain "
                     "Jacobian (worst raw |a-b|/rowmax {:.3e}; {} entries differ)").format(c["k"], c["worst_dev"],
                                                                                    c["differ"])
    return text


def run_dirs(group_dir):
    return sorted((d for d in os.listdir(group_dir) if d.startswith("run")), key=lambda d: (len(d), d))


def flow_mode(flow, tol):
    out = {"tol": tol, "matrix": "post_exmain", "groups": {}}
    if not os.path.isdir(flow):
        raise CannotJudge("{}: no flow directory".format(flow))
    for cfg in sorted(os.listdir(flow)):
        cdir = os.path.join(flow, cfg)
        if not os.path.isdir(cdir):
            continue
        groups = sorted(g for g in os.listdir(cdir) if g.startswith("jac_t") and os.path.isdir(os.path.join(cdir, g)))
        if not groups:
            continue
        serial = None
        serial_error = None
        try:
            serial = load(os.path.join(cdir, "serial"))
        except CannotJudge as err:
            serial_error = "serial reference: {}".format(err)
        for g in groups:
            key = "{}/{}".format(cfg, g)
            entry = {"error": serial_error, "runs": {}}
            out["groups"][key] = entry
            if serial is None:
                continue
            for r in run_dirs(os.path.join(cdir, g)):
                rdir = os.path.join(cdir, g, r)
                if not has_record(rdir):
                    entry["runs"][r] = {"skipped": "no record (the run failed; the flow counts it)"}
                    continue
                try:
                    entry["runs"][r] = judge(serial, load(rdir), tol)
                except CannotJudge as err:
                    entry["runs"][r] = {"error": str(err)}
    return out


def exit_of(result):
    code = 0
    for g in result["groups"].values():
        if g.get("error"):
            code = 2
        for res in g["runs"].values():
            if "error" in res:
                code = 2
            elif res.get("pass") is False:
                code = max(code, 1)
    return code


OWN_HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tests/deterministic_omp


def check_arm_problems(harness, rundir):
    harness = harness or OWN_HARNESS
    if harness not in sys.path:
        sys.path.insert(0, harness)
    try:
        from harness.compare import check_arm
        from harness.runner import Record
    except ImportError as err:
        raise CannotJudge("--harness {}: {}".format(harness, err))
    return ["check_arm: " + p for p in check_arm(Record(rundir))]


def check_mode(dirs, tol, harness):
    code = 0
    for d in dirs:
        try:
            serial = load(os.path.join(d, "serial"))
            for r in run_dirs(d):
                res = judge(serial, load(os.path.join(d, r)), tol)
                arm = check_arm_problems(harness, os.path.join(d, r))
                if arm:
                    res["problems"] += arm
                    res["pass"] = False
                code = max(code, 0 if res["pass"] else 1)
                print(describe("{} {}".format(d, r), res))
        except (CannotJudge, OSError) as err:
            print("{}: ERROR (cannot judge): {}".format(d, err))
            code = 2
    return code


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dirs", nargs="*", help="cli.py check directories (check-dir mode)")
    p.add_argument("--flow", default=None, help="a cli.py flow --out directory (flow mode)")
    p.add_argument("--tol", type=float, default=DEFAULT_TOL, help="deviation bound (default 1e-6, the C1 bound)")
    p.add_argument("--json", default=None, help="flow mode: where to write the result (default FLOWDIR/bound.json)")
    p.add_argument("--harness", default=None, help="check-dir mode: tests/deterministic_omp of the harness for check_arm "
                   "(default: the one next to this script)")
    args = p.parse_args(argv)
    if (args.flow is None) == (not args.dirs):
        p.error("give --flow FLOWDIR or CHECKDIR(s), not both")
    if not args.tol > 0:
        p.error("--tol must be > 0")
    if args.flow is None:
        code = check_mode(args.dirs, args.tol, args.harness)
        print("BOUND " + {0: "PASS", 1: "FAIL", 2: "ERROR"}[code])
        return code
    try:
        result = flow_mode(args.flow, args.tol)
        code = exit_of(result)
    except CannotJudge as err:
        result, code = {"tol": args.tol, "matrix": "post_exmain", "groups": {}, "error": str(err)}, 2
        print("{}: ERROR (cannot judge): {}".format(args.flow, err))
    result["exit_code"] = code
    for key, g in sorted(result["groups"].items()):
        if g.get("error"):
            print("[{}] {}: ERROR (cannot judge): {}".format(os.path.basename(os.path.normpath(args.flow)), key,
                                                            g["error"]))
        for r, res in g["runs"].items():
            print("[{}] {}".format(os.path.basename(os.path.normpath(args.flow)), describe("{}/{}".format(key, r), res)))
    path = args.json or os.path.join(args.flow, "bound.json")
    try:
        with open(path, "w") as f:
            json.dump(result, f, indent=1)
    except OSError as err:
        print("cannot write {}: {}".format(path, err))
        code = 2
    print("BOUND {} (tol {:g}, post_exmain)".format({0: "PASS", 1: "FAIL", 2: "ERROR"}[code], args.tol))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # fail closed: a traceback is "cannot judge", never a pass or a mismatch
        traceback.print_exc()
        sys.exit(2)
