"""AIUE-60 flow gates (plan Testing 3): per run and per section, AIUE-60 flow vs the AIUE-56 flow.

  python -I AIUE-60-flow-gates.py --base FLOW_AIUE56 --new FLOW_AIUE60 [--harness DIR] [--c1-gate PATH] [--stage DIR]

Both directories are `cli.py flow` outputs (flow.json, <config>/serial, <config>/<arm>_t<n>/run<k>). Classes are fixed
in advance (plan): X = ti, ni, up, ng; Y = tebox, full, te, phi. For every AIUE-60 group (config, arm, threads):
  (a) class X: every comparison report agrees (every section bitwise; group PASS)
  (b) class Y: in the agreement reports, every mismatch of a jacobian:* section lies in a Te row
  (c) class Y: AIUE-56-c1-gate.py passes on the group's runs (adapter: a staging directory with symlinks
      serial -> <config>/serial and run<k> -> <config>/<arm>_t<n>/run<k>, the layout the gate script reads)
  (d) every class: the RHS sections (yldot, yldot_probe, sfscal, suscal, fnrm_final, fnrm_printed) agree with serial
      in every agreement report
  (f) no run failure (crash, timeout, UEDGE error) unless the AIUE-56 group of the same key also had one
Fallback (mechanical): if the AIUE-56 group of the same key itself violates (a), or (d) for a section, AIUE-60's
violation of that gate there is marked RERUN (judged by the plan's re-run rule), not FAIL. A harness error in a group
(flow "errors") is ERROR. Exit: 0 all PASS, 1 any FAIL, 3 no FAIL but RERUN needed, 2 any ERROR.
"""
import argparse
import json
import os
import subprocess
import sys

CLASS_X = {"ti", "ni", "up", "ng"}
CLASS_Y = {"tebox", "full", "te", "phi"}
RHS_SECTIONS = ("yldot", "yldot_probe", "sfscal", "suscal", "fnrm_final", "fnrm_printed")
HERE = os.path.dirname(os.path.abspath(__file__))


def fails(sec):
    return bool(sec.get("mismatches", 0) or sec.get("nonfinite_a", 0) or sec.get("nonfinite_b", 0) or sec.get("error"))


def agreement(group):
    return [r for r in group.get("reports", []) if r.get("kind", "").startswith("agreement") and not r.get("errors")]


def gate_a(group):
    return [] if group.get("verdict") == "PASS" else ["(a) group verdict {}".format(group.get("verdict"))]


def gate_b(group):
    out = []
    for r in agreement(group):
        for name, sec in r["sections"].items():
            if not name.startswith("jacobian:") or not fails(sec):
                continue
            pairs = sec.get("by_equation_pair")
            if not pairs:
                out.append("(b) {} {}: mismatches not localised".format(r["kind"], name))
                continue
            rows = {p.split("/")[0] for p in pairs}
            if rows - {"te"}:
                out.append("(b) {} {}: rows {}".format(r["kind"], name, sorted(rows)))
    return out


def gate_d(group):
    """[(section, message)] for every RHS section that fails in an agreement report."""
    out = []
    for r in agreement(group):
        for name in RHS_SECTIONS:
            sec = r["sections"].get(name)
            if sec is not None and fails(sec):
                out.append((name, "(d) {} {}: {}".format(r["kind"], name, sec.get("by_equation", sec.get("mismatches")))))
    return out


def gate_c(flowdir, group, stage, c1_gate, harness):
    key = "{}_{}_t{}".format(group["config"], group["arm"], group["threads"])
    d = os.path.join(stage, key)
    os.makedirs(d, exist_ok=True)
    links = {"serial": os.path.join(flowdir, group["serial"]["rundir"])}
    for k, run in enumerate(group.get("runs", [])):
        if not run.get("error"):
            links["run{}".format(k)] = os.path.join(flowdir, run["rundir"])
    for name, target in links.items():
        p = os.path.join(d, name)
        if not os.path.lexists(p):
            os.symlink(os.path.abspath(target), p)
    cmd = [sys.executable, "-I", c1_gate] + (["--harness", harness] if harness else []) + [d]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return ([] if res.returncode == 0 else ["(c) c1-gate exit {}: {}".format(res.returncode, res.stdout.strip()[-400:])],
            res.stdout)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--harness", default="/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp")
    p.add_argument("--c1-gate", default=os.path.join(HERE, "AIUE-56-c1-gate.py"))
    p.add_argument("--stage", default=None, help="staging directory for gate (c) (default: <new>/c1_stage)")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    base = {(g["config"], g["arm"], g["threads"]): g for g in json.load(open(os.path.join(a.base, "flow.json")))["groups"]}
    new = json.load(open(os.path.join(a.new, "flow.json")))["groups"]
    stage = a.stage or os.path.join(a.new, "c1_stage")
    results = []
    for g in new:
        key = (g["config"], g["arm"], g["threads"])
        b = base.get(key)
        res = {"group": "{} {} t{}".format(*key), "fail": [], "rerun": [], "c1": ""}
        if g.get("errors") or b is None or b.get("errors"):
            res["error"] = (g.get("errors") or []) + (["no AIUE-56 group"] if b is None else b.get("errors") or [])
        else:
            if g["config"] in CLASS_X:
                v = gate_a(g)
                (res["rerun"] if gate_a(b) else res["fail"]).extend(v)
            if g["config"] in CLASS_Y:
                res["fail"].extend(gate_b(g))
                v, out = gate_c(a.new, g, stage, a.c1_gate, a.harness)
                res["fail"].extend(v)
                res["c1"] = out.strip().splitlines()[-1] if out.strip() else ""
            base_sections = {s for s, _ in gate_d(b)}  # fallback: sections AIUE-56 itself violates here
            for section, msg in gate_d(g):
                (res["rerun"] if section in base_sections else res["fail"]).append(msg)
            if g.get("run_failures"):
                (res["rerun"] if b.get("run_failures") else res["fail"]).extend(
                    "(f) " + f for f in g["run_failures"])
        status = "ERROR" if res.get("error") else ("FAIL" if res["fail"] else ("RERUN" if res["rerun"] else "PASS"))
        res["status"] = status
        results.append(res)
        print("{:<22} {:<5} {}{}".format(res["group"], status, res["c1"],
                                         "".join("\n    " + x for x in res.get("error", []) + res["fail"] + res["rerun"])))
    statuses = {r["status"] for r in results}
    code = 2 if "ERROR" in statuses else 1 if "FAIL" in statuses else 3 if "RERUN" in statuses else 0
    print("FLOW GATES", {0: "PASS", 1: "FAIL", 2: "ERROR", 3: "RERUN NEEDED"}[code])
    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, indent=1)
    return code


if __name__ == "__main__":
    sys.exit(main())
