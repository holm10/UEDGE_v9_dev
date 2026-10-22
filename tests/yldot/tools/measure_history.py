"""History, warm-up and cost characterisation of the yldot families (epic AIUE-9, PRD sections 7.7 and 7.9).

Usage (from anywhere):
    python measure_history.py run <family>... [--repeats N] [--json FILE] [--log FILE]
    python measure_history.py check <family>... [--log FILE]

run    per family, every comparison below, W and P chosen from them, the reuse sequence and the costs; prints a
       report and a TOML fragment for family.toml ([evaluation] w, p, child_reuse and a [history] table).
check  the family.toml W and P against W+1 and P+1 in both configurations, the flag sequence and the steady
       +1/-1 rule: what test_history.py runs.

The comparisons are bit for bit, on yldot and yldot_J of the protocol in harness/state.py (PRD section 6):
    W      exmain x w, w = 1, 2, 3, each in a fresh process, both configurations, at p = 1; plus a second w = 1
           process, the control: the same settings in two processes must agree.
    P      pandf x p, p = 1, 2, 3 at the chosen W, fresh processes.
    flag   after the protocol, in the same process, one more pandf at -1 must reproduce yldot (the -1 -> +1 -> -1
           sequence of step 8b) and one more at +1 must reproduce yldot_J.
    +1/-1  steady yldot_J against yldot. Rows may differ only through the flag-gated branches active in steady:
           ishosor's volume integration (bbb/pandf_plasma_continuity.m:714); add_timestep is off at dtreal = 1e20
           (bbb/pandf.m:739), ismcnon is not tested (decision 22). Differing rows are listed by equation, species and
           region, and a counterfactual with ishosor = 0 must make them equal.
    reuse  one process runs steady, steady, timestep, steady, intake, steady (state.evaluate each time, so input.py
           is executed again each time). Report only: child reuse is not allowed for any family (owner, 2026-10-21,
           AIUE-86).
W and P are the smallest counts whose results equal those of every larger count measured. Since the states are
round-trip fixed points (AIUE-140), the old suite's "fnrm still changes after 1 exmain, but not after 2" no longer
applies: one exmain no longer changes the saved state.

Costs (PRD section 7.9): the wall time of one evaluation child through the harness Runner (forkserver, as the
suite runs), median of --repeats per configuration; inside a child the whole protocol and one pandf (median of 5);
the sweep estimate is the planned non-excluded variants per configuration (variants.plan()) times that wall time.

Every measurement runs in a fresh process (Forthon state is global), cwd the family directory, HOME an empty
temporary directory, UEDGE_BANNER=0 and one thread, as in make_base_state.py. Exit codes: 0 ok, 2 usage or
evaluation error, 3 a family the owner has to look at (svrpkg/ifixpsor, or +1/-1 rows the ishosor counterfactual
does not explain), 4 a defect: a nonzero difference between repeated exmain or pandf calls, the flag sequence, or
two processes at the same settings (file a bugfix/v9-* ticket, never absorb it).
"""
import argparse
import json
import os
import pickle
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package
from yldot.harness import FamilyError, Runner, compare, load_evaluation, variants  # noqa: E402
from yldot.harness.process import family_dir  # noqa: E402

COUNTS = (1, 2, 3)  # the W and P values measured by run
REUSE_SEQUENCE = ("steady", "steady", "timestep", "steady", "intake", "steady")
PANDF_TIMINGS = 5


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def same(a, b):
    """Bit for bit (NaN equals itself)."""
    return a.shape == b.shape and a.tobytes() == b.tobytes()


def ndiff(a, b):
    """Rows that differ bit for bit."""
    return int(np.count_nonzero(a.view(np.uint64) != b.view(np.uint64)))


# ---------------------------------------------------------------- child side


def protocol(state, job):
    """The protocol of state.py, then, on the live bbb, the flag sequence, pandf timings and the counterfactual."""
    from uedge import bbb  # before the clock: the forkserver children of the suite have uedge preloaded

    t = time.perf_counter()
    out = state.evaluate(job)
    out["t_eval"] = time.perf_counter() - t

    neq = out["neq"]

    def pandf(flag):
        bbb.yl[neq] = flag
        bbb.pandf(-1, -1, neq, 0.0, bbb.yl, bbb.yldot)
        return bbb.yldot[:neq].copy()

    out["flag_back"] = pandf(-1.0)  # step 8b left the last call at +1: -1 -> +1 -> -1
    out["plus_again"] = pandf(1.0)
    timings = []
    for _ in range(PANDF_TIMINGS):
        t = time.perf_counter()
        pandf(-1.0)
        timings.append(time.perf_counter() - t)
    out["t_pandf"] = statistics.median(timings)
    out["flags"] = {"ishosor": int(bbb.ishosor), "ismcnon": int(bbb.ismcnon)}
    if job["config"] == "steady" and not same(out["yldot"], out["yldot_J"]):
        ishosor = int(bbb.ishosor)
        bbb.ishosor = 0
        try:
            out["counterfactual"] = (pandf(-1.0), pandf(1.0))
        finally:
            bbb.ishosor = ishosor
    bbb.yl[neq] = -1.0
    return out


def reuse(state, job):
    """REUSE_SEQUENCE in this one process; stops at the first exception after the first step (report only). The
    first step runs in a fresh process like every protocol child, so an exception there is an evaluation error."""
    out = {"results": [], "error": None}
    for step, config in enumerate(REUSE_SEQUENCE):
        try:
            r = state.evaluate(dict(job, config=config))
        except Exception as e:  # xerrab arrives as RuntimeError (Forthon's kaboom)
            if step == 0:
                raise
            out["error"] = {"step": step, "config": config, "message": repr(e),
                            "where": traceback.format_exc().strip().splitlines()[-3:]}
            break
        out["results"].append({k: r[k] for k in ("yldot", "yldot_J") if k in r})
    return out


def worker(job):
    """Runs in the child, cwd = family directory. Writes its results to job['out']."""
    family = Path.cwd()
    if (family / ".uedgerc.py").exists():
        print("refused: {} holds .uedgerc.py".format(family), file=sys.stderr)
        return 2
    from yldot.harness import state

    spec = {"family": str(family), "config": job["config"], "mode": "spawn", "w": job["w"], "p": job["p"],
            "dt": job["dt"], "diagnostics": False, "pre": None, "post": None, "variant": None, "log": None}
    try:
        out = protocol(state, spec) if job["kind"] == "protocol" else reuse(state, spec)
    except state.Stop as e:
        print("{}: {}".format(e.status, e), file=sys.stderr)
        return 3 if e.status in ("owner", "refused") else 2
    with open(job["out"], "wb") as f:
        pickle.dump(out, f)
    return 0


# ---------------------------------------------------------------- parent side


def run_child(family_dir, job, log):
    """One fresh process per measurement; returns the unpickled results."""
    with tempfile.TemporaryDirectory(prefix="yldot-home-") as home, \
            tempfile.TemporaryDirectory(prefix="yldot-out-") as outdir:
        job = dict(job, out=os.path.join(outdir, "out.pkl"))
        env = dict(os.environ, HOME=home, UEDGE_BANNER="0", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_worker", json.dumps(job)],
                              cwd=family_dir, env=env, capture_output=True, text=True)
        log.write(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-20:])
            raise Stop(3 if proc.returncode == 3 else 2,
                       "child exit {} in {} ({}):\n{}".format(proc.returncode, family_dir.name, job["kind"], tail))
        with open(job["out"], "rb") as f:
            out = pickle.load(f)
        # Fortran's xerrab text goes to stdout, not into the RuntimeError that Forthon raises
        out["remarks"] = [s.strip() for s in proc.stdout.splitlines() if s.strip().startswith("***")]
        return out


class Family:
    """The measurements of one family; defects and owner findings are collected, not raised, until the report."""

    def __init__(self, family, log):
        try:
            self.dir = family_dir(family)  # a name under FAMILIES, or a path to a family directory
        except FamilyError as e:
            raise Stop(2, str(e))
        self.name = self.dir.name
        self.ev = load_evaluation(self.dir)
        self.log = log
        self.defects = []
        self.owner = []

    def protocol(self, config, w, p):
        return run_child(self.dir, {"kind": "protocol", "config": config, "w": w, "p": p,
                                    "dt": float(self.ev["dt_timestep_s"])}, self.log)

    def rows(self, a, b):
        """Rows of yldot plus rows of yldot_J that differ between two protocol results."""
        return ndiff(a["yldot"], b["yldot"]) + ndiff(a["yldot_J"], b["yldot_J"])

    def sweep(self, what, results):
        """results: {count: protocol result} per configuration -> (chosen count, {config: rows differing between
        consecutive counts}). Any difference is a history effect inside one process: a defect."""
        diffs, chosen = {}, 1
        for config, res in results.items():
            counts = sorted(res)
            d = [self.rows(res[a], res[b]) for a, b in zip(counts, counts[1:])]
            diffs[config] = d
            for i, n in enumerate(d):
                if n:
                    self.defects.append("{} {}: {} {} vs {}: {} rows differ".format(
                        self.name, config, what, counts[i], counts[i + 1], n))
            # the smallest count equal to every larger one
            last = max((i + 1 for i, n in enumerate(d) if n), default=0)
            chosen = max(chosen, counts[last])
        return chosen, diffs

    def flags(self, res, config):
        """The flag sequence inside one process: one more call at -1 and at +1 reproduce yldot and yldot_J."""
        n = ndiff(res["flag_back"], res["yldot"]) + ndiff(res["plus_again"], res["yldot_J"])
        if n:
            self.defects.append("{} {}: the -1 -> +1 -> -1 sequence does not reproduce: {} rows".format(
                self.name, config, n))
        return n

    def plus_minus(self, res):
        """Steady yldot_J against yldot: differing rows by (equation, species, region) and whether ishosor = 0
        removes them (the only flag-gated branch active in steady)."""
        d = np.flatnonzero(res["yldot"].view(np.uint64) != res["yldot_J"].view(np.uint64))
        out = {"rows": int(d.size), "gated_rows": 0, "by_block": {}, "flags": res["flags"]}
        if not d.size:
            return out
        imap = compare.index_map(res, compare.load_regions(self.dir))
        out["by_block"] = {"{}[{}] {}".format(*k): v for k, v in sorted(Counter(
            (imap.eq[i], int(imap.species[i]), imap.region[i] or "-") for i in d).items())}
        cf = res.get("counterfactual")
        if cf is not None and same(cf[0], cf[1]):
            out["gated_rows"] = int(d.size)
        else:
            self.owner.append("{}: steady +1 and -1 differ in {} rows that ishosor = 0 does not explain ({}); "
                              "irregular: ask the epic owner (decision 23)".format(self.name, d.size,
                                                                                 out["by_block"]))
        return out

    def reuse(self, w, p):
        res = run_child(self.dir, {"kind": "reuse", "config": "steady", "w": w, "p": p,
                                   "dt": float(self.ev["dt_timestep_s"])}, self.log)
        steps = []
        first = res["results"][0] if res["results"] else None
        for config, r in zip(REUSE_SEQUENCE, res["results"]):
            steps.append(self.rows(first, r) if config == "steady" else None)
        if res["error"]:
            res["error"]["remarks"] = res["remarks"]
        return {"sequence": list(REUSE_SEQUENCE), "steady_rows_vs_first": steps, "error": res["error"]}

    def costs(self, at, repeats):
        runner = Runner()
        wall = {}
        for config in variants.CONFIGS:
            times = []
            for _ in range(repeats):
                r = runner.evaluate(self.dir, config=config)
                if not r.ok:
                    raise Stop(2, "{} {}: {}: {}\n{}".format(self.name, config, r.status, r.message, r.log_tail))
                times.append(r.wall_s)
            wall[config] = statistics.median(times)
        n = Counter(v.config for v in variants.plan() if not v.excluded)
        return {"child_wall_s": wall, "eval_in_child_s": {c: at[c]["t_eval"] for c in variants.CONFIGS},
                "pandf_s": at["steady"]["t_pandf"], "n_variants": dict(n),
                "sweep_cpu_s": sum(n[c] * wall[c] for c in variants.CONFIGS)}


def cmd_run(fam, repeats):
    """Every comparison, W and P, reuse and costs for one family -> the report."""
    sweep_w = {c: {w: fam.protocol(c, w, 1) for w in COUNTS} for c in variants.CONFIGS}
    control = {c: fam.rows(sweep_w[c][1], fam.protocol(c, 1, 1)) for c in variants.CONFIGS}
    for c, n in control.items():
        if n:
            fam.defects.append("{} {}: two processes at w = 1, p = 1 differ in {} rows".format(fam.name, c, n))
    w, w_diffs = fam.sweep("exmain x", sweep_w)
    sweep_p = {c: {p: fam.protocol(c, w, p) for p in COUNTS} for c in variants.CONFIGS}
    p, p_diffs = fam.sweep("pandf x", sweep_p)
    at = {c: sweep_p[c][p] for c in variants.CONFIGS}
    return {
        "family": fam.name, "uedge_ver": at["steady"]["uedge_ver"], "w": w, "p": p,
        "w_sweep": w_diffs, "p_sweep": p_diffs, "control_two_processes": control,
        "flag_sequence": {c: fam.flags(at[c], c) for c in variants.CONFIGS},
        "steady_plus_minus": fam.plus_minus(at["steady"]),
        "reuse": fam.reuse(w, p),
        "costs": fam.costs(at, repeats),
    }


def cmd_check(fam):
    """family.toml W and P against W+1 and P+1, the flag sequence and the +1/-1 rule."""
    w, p = int(fam.ev["w"]), int(fam.ev["p"])
    out = {"family": fam.name, "w": w, "p": p}
    for c in variants.CONFIGS:
        base = fam.protocol(c, w, p)
        fam.sweep("exmain x", {c: {w: base, w + 1: fam.protocol(c, w + 1, p)}})
        fam.sweep("pandf x", {c: {p: base, p + 1: fam.protocol(c, w, p + 1)}})
        out["flag_sequence_" + c] = fam.flags(base, c)
        if c == "steady":
            out["steady_plus_minus"] = fam.plus_minus(base)
    return out


def inline(d):
    return "{ " + ", ".join("{} = {}".format(k, json.dumps(v)) for k, v in d.items()) + " }"


def fragment(r):
    """The family.toml lines (comments, owner attributions and the reuse note are added by hand)."""
    c, pm, ru = r["costs"], r["steady_plus_minus"], r["reuse"]
    if ru["error"]:
        reuse_text = "input.py fails when run again in the same process, step {} ({}): {} {}".format(
            ru["error"]["step"], ru["error"]["config"], ru["error"]["message"], " ".join(ru["error"]["remarks"]))
    elif any(ru["steady_rows_vs_first"]):
        reuse_text = "steady rows differing from the first steady: {} ({})".format(
            ru["steady_rows_vs_first"], ", ".join(ru["sequence"]))
    else:
        reuse_text = "bit-identical: {}".format(", ".join(ru["sequence"]))
    rnd = {k: round(v, 4) for k, v in c["child_wall_s"].items()}
    return "\n".join([
        "[evaluation]",
        "w = {}".format(r["w"]),
        "p = {}".format(r["p"]),
        "child_reuse = false",
        "",
        "[history]",
        'measured = "{}"'.format(date.today().isoformat()),
        'uedge_ver = "{}"'.format(r["uedge_ver"]),
        "w_sweep = {}".format(inline(r["w_sweep"])),
        "p_sweep = {}".format(inline(r["p_sweep"])),
        "control_two_processes = {}".format(inline(r["control_two_processes"])),
        "flag_sequence = {}".format(inline(r["flag_sequence"])),
        "steady_plus_minus_rows = {}".format(pm["rows"]),
        "gated_rows = {}".format(pm["gated_rows"]),
        "flags = {}".format(inline(pm["flags"])),
        "reuse = {}".format(json.dumps(reuse_text)),
        "child_wall_s = {}".format(inline(rnd)),
        "eval_in_child_s = {}".format(inline({k: round(v, 4) for k, v in c["eval_in_child_s"].items()})),
        "pandf_s = {:.2e}".format(c["pandf_s"]),
        "n_variants = {}".format(inline(c["n_variants"])),
        "sweep_cpu_s = {:.0f}".format(c["sweep_cpu_s"]),
    ])


def main(argv):
    if len(argv) > 1 and argv[1] == "_worker":
        return worker(json.loads(argv[2]))
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="measure history, W, P, reuse and costs")
    p.add_argument("family", nargs="+")
    p.add_argument("--repeats", type=int, default=5, help="Runner children per configuration for the costs")
    p.add_argument("--json", help="write the full report here")
    p.add_argument("--log", help="child output log (default: discarded)")
    p = sub.add_parser("check", help="check family.toml W and P, the flag sequence and the +1/-1 rule")
    p.add_argument("family", nargs="+")
    p.add_argument("--log", help="child output log (default: discarded)")
    args = parser.parse_args(argv[1:])
    log = open(args.log, "a") if args.log else open(os.devnull, "w")
    reports, code = [], 0
    try:
        for name in args.family:
            fam = Family(name, log)
            r = cmd_run(fam, args.repeats) if args.cmd == "run" else cmd_check(fam)
            r["defects"], r["owner"] = fam.defects, fam.owner
            reports.append(r)
            print(json.dumps({k: v for k, v in r.items() if k not in ("costs",)}, default=str))
            if args.cmd == "run":
                print("# {} family.toml fragment\n{}\n".format(name, fragment(r)))
            for m in fam.owner:
                print("OWNER: " + m, file=sys.stderr)
            for m in fam.defects:
                print("DEFECT: " + m, file=sys.stderr)
            code = max(code, 4 if fam.defects else 3 if fam.owner else 0)
    except Stop as stop:
        print(str(stop), file=sys.stderr)
        return stop.code
    finally:
        log.close()
    if getattr(args, "json", None):
        with open(args.json, "w") as f:
            json.dump(reports, f, indent=1, default=str)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
