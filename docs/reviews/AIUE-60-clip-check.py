"""AIUE-60: does the OpenMP Jacobian keep the same entries as serial when jaccliplim > 0?

Serial jac_calc keeps an entry when |jacelem*sfscal(ii)| > jaccliplim (ii = row/equation, bbb/oderhs.m);
LocalJacBuilder used sfscal(iv) (iv = column/perturbed variable, ppp/parallel.F90) before AIUE-60. With the
default jaccliplim = 0 both tests reduce to jacelem*sfscal != 0; with jaccliplim > 0 they keep different
entries whenever sfscal is not uniform. This script shows which rule a build uses, on the AIUE-46 reproducer.

Inside the first (sfsetnk) Jacobian of an exmain, sfscal is 1 (AIUE-60 probe: the smallest kept |raw| is
exactly jaccliplim), so that Jacobian cannot tell the rules apart. The psetnk Jacobian at Newton iteration 0
is computed at the same initial state with the non-uniform sfscal sfsetnk just set. So one run (`run`, a
fresh process): deck -> preset -> arm; jaccliplim = L; itermx = 1; isrnorm = 0 and ireorder = 0 (both arms:
bbb.jac after exmain is then raw(r,c) * sfscal(r) / suscal(c) in natural order); exmain. Saves bbb.jac (CSR),
sfscal and suscal.

  python -I AIUE-60-clip-check.py check --python NEW/bin/python [--base-python OLD/bin/python] \\
         --preset full --clip 1e-6 --threads 4 --repeats 2 --out DIR

`check` runs, per build, a serial reference, a serial run with clip 0 (for the prediction) and K OpenMP-Jacobian
runs, one at a time, and reports:
  predicted   from the serial clip-0 Jacobian: entries the row rule and the column rule keep differently at L
  G1 (new)    every OpenMP entry present on one side only is a threshold flip: | |J(r,c)| - L/suscal(c) | <=
              TAU * max_c'|J(r,c')| (TAU = 1e-8, row max of that side's J; the row rule keeps |J(r,c)| > L/suscal(c)),
              i.e. the band is in the scale of the C2 round-off residual (<= 7.2e-9 x row max, AIUE-56). If a run's
              common values and sfscal are bitwise equal to serial, it must have no one-sided entry at all.
              Reported per run: entries in the band (serial), value differences of common entries.
  G2          report only: sfscal differences serial vs OpenMP (count, max relative). sfscal comes from the
              sfsetnk Jacobian, which round-off (C2) may change; each side's J is scaled by its own sfscal, so the
              band test above stays self-consistent. suscal must be bitwise equal (else exit 2: not comparable).
  G3 (base)   negative control: every base OpenMP run has non-flip pattern differences (the case is sensitive)
  G4          the serial Jacobians of base and new are bitwise equal (pattern and values; serial unchanged)
Exit: 0 all gates pass, 1 a gate fails, 2 harness error / precondition (suscal not bitwise, run failed).
The harness core (presets, case files, rates) is read from --harness (AIUE-57 reviewed core by default).
"""
import argparse
import json
import os
import subprocess
import sys
import time

DEFAULT_HARNESS = "/Users/holma/Documents/uedge/src/uedge-wt/AIUE-57/tests/deterministic_omp"


def worker(a):
    import numpy as np
    sys.path.insert(0, a.harness)
    sys.path.insert(0, os.getcwd())
    from harness.config import ARMS, DIAGNOSTIC_SWITCHES, apply_preset
    from input_mod4 import bbb, ppp  # runs the deck in the run directory

    apply_preset(bbb, a.preset)
    for name in DIAGNOSTIC_SWITCHES:
        setattr(ppp, name, 0)
    for name, value in ARMS[a.arm].items():
        setattr(ppp, name, value)
    ppp.Nthreads = a.threads
    for name, value in json.loads(a.ppp or "{}").items():
        setattr(ppp, name, value)
    bbb.itermx = 1
    bbb.isrnorm = 0
    bbb.ireorder = 0
    bbb.jaccliplim = a.clip
    bbb.exmain()
    neq = int(bbb.neq)
    nnz = int(bbb.jaci[neq]) - 1
    out = {"jac": np.array(bbb.jac[:nnz]), "jacj": np.array(bbb.jacj[:nnz]), "jaci": np.array(bbb.jaci[: neq + 1]),
           "sfscal": np.array(bbb.sfscal[:neq]), "suscal": np.array(bbb.suscal[:neq])}
    meta = {"preset": a.preset, "arm": a.arm, "threads": a.threads, "clip": a.clip, "neq": neq, "nnz": nnz,
            "ijactot": int(bbb.ijactot), "iterm": int(bbb.iterm), "Nthreads": int(ppp.Nthreads),
            "OMPParallelJac": int(ppp.OMPParallelJac), "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS")}
    np.savez("clip.npz", **out)
    with open("clip.json", "w") as f:
        json.dump(meta, f, indent=1)


def launch(python, harness, preset, arm, threads, clip, ppp, rundir):
    sys.path.insert(0, harness)
    from harness.runner import DEFAULT_RATES, prepare_rundir
    prepare_rundir(rundir)
    home = os.path.join(rundir, "home")
    os.makedirs(home)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OMP_", "GOMP_", "KMP_", "PYTHON"))}
    env.update({"HOME": home, "UEDGE_OMP_RATES_DIR": DEFAULT_RATES, "OMP_NUM_THREADS": str(threads),
                "OMP_STACKSIZE": "512M"})
    cmd = [python, "-I", os.path.abspath(__file__), "run", "--harness", harness, "--preset", preset, "--arm", arm,
           "--threads", str(threads), "--clip", repr(clip)] + (["--ppp", ppp] if ppp else [])
    t0 = time.time()
    with open(os.path.join(rundir, "run.log"), "wb") as log:
        rc = subprocess.run(cmd, cwd=rundir, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    if rc != 0 or not os.path.exists(os.path.join(rundir, "clip.json")):
        raise RuntimeError("run failed (exit %d): %s" % (rc, rundir))
    meta = json.load(open(os.path.join(rundir, "clip.json")))
    want = 1 if arm != "serial" else 0
    if meta["OMPParallelJac"] != want or (arm != "serial" and meta["Nthreads"] != threads) or meta["ijactot"] < 2:
        raise RuntimeError("arm did not take effect, or no psetnk Jacobian, in %s: %s" % (rundir, meta))
    meta["elapsed_s"] = round(time.time() - t0, 1)
    return meta


def load(rundir):
    import numpy as np
    return dict(np.load(os.path.join(rundir, "clip.npz")))


def entries(d):
    import numpy as np
    ia, ja, a = d["jaci"], d["jacj"], d["jac"]
    rows = np.repeat(np.arange(1, len(ia)), np.diff(ia))
    return dict(zip(zip(rows.tolist(), ja.tolist()), a.tolist()))


def predicted(ser0, clip):
    """From the serial unclipped psetnk Jacobian (a clip-0 run at the same state): entries the row rule and the
    column rule keep differently at clip. bbb.jac = raw*sf(r)/su(c), so the row-rule value is |J*su(c)|."""
    sf, su = ser0["sfscal"], ser0["suscal"]
    n_row = n_col = n_xor = 0
    for (r, c), v in entries(ser0).items():
        v_row = abs(v * su[c - 1])
        keep_row, keep_col = v_row > clip, v_row / sf[r - 1] * sf[c - 1] > clip
        n_row += keep_row
        n_col += keep_col
        n_xor += keep_row != keep_col
    return {"row_rule_keeps": int(n_row), "col_rule_keeps": int(n_col), "rules_differ": int(n_xor)}


TAU = 1e-8  # band half-width in units of the row max (C2 residual <= 7.2e-9 x row max, AIUE-56)


def row_max(d):
    import numpy as np
    ia, a = d["jaci"], np.abs(d["jac"])
    return np.array([a[ia[i] - 1:ia[i + 1] - 1].max() if ia[i + 1] > ia[i] else 0.0 for i in range(len(ia) - 1)])


def in_band(v, r, c, su, rmax, clip):
    """bbb.jac = raw*sf(r)/su(c) and the row rule keeps |raw*sf(r)| > clip, i.e. |J(r,c)| > clip/su(c). An entry is
    a threshold flip when |J(r,c)| lies within TAU x (row max of J) of that threshold: the C2 scale."""
    return abs(abs(v) - clip / su[c - 1]) <= TAU * rmax[r - 1]


def pattern_diff(ser, omp, clip):
    s, o = entries(ser), entries(omp)
    su = ser["suscal"]
    rmax_s, rmax_o = row_max(ser), row_max(omp)
    only = [(rc, v, "serial") for rc, v in s.items() if rc not in o] + \
           [(rc, v, "omp") for rc, v in o.items() if rc not in s]
    flips = nonflips = 0
    worst = 0.0
    for (r, c), v, side in only:
        rmax = rmax_s if side == "serial" else rmax_o  # each side's own J and row scale (its own sfscal)
        if in_band(v, r, c, su, rmax, clip):
            flips += 1
        else:
            nonflips += 1
            worst = max(worst, abs(abs(v) - clip / su[c - 1]) / max(rmax[r - 1], 1e-300))
    vdiff = sum(1 for rc in s if rc in o and s[rc] != o[rc])
    band = sum(1 for (r, c), v in s.items() if in_band(v, r, c, su, rmax_s, clip))
    sf_diff = int((ser["sfscal"] != omp["sfscal"]).sum())
    sf_rel = float(abs(omp["sfscal"] / ser["sfscal"] - 1).max())
    return {"nnz_serial": len(s), "nnz_omp": len(o), "only_serial": sum(1 for x in only if x[2] == "serial"),
            "only_omp": sum(1 for x in only if x[2] == "omp"), "threshold_flips": flips, "non_flips": nonflips,
            "worst_nonflip_dist_rowmax": float(worst), "value_diffs_common": vdiff,
            "serial_entries_in_band": band, "sfscal_diffs": sf_diff, "sfscal_max_rel_diff": sf_rel}


def g1_pass(d):
    """No non-flip one-sided entry; and if the common values and sfscal are bitwise equal to serial (no round-off
    residual in this run), no one-sided entry at all."""
    one_sided = d["only_serial"] + d["only_omp"]
    return d["non_flips"] == 0 and (d["value_diffs_common"] > 0 or d["sfscal_diffs"] > 0 or one_sided == 0)


def check(a):
    import numpy as np
    os.makedirs(a.out)
    builds = [("new", a.python)] + ([("base", a.base_python)] if a.base_python else [])
    rep = {"args": vars(a), "builds": {}}
    rc = 0
    sers = {}
    for label, py in builds:
        b = rep["builds"][label] = {"python": py, "runs": []}
        sdir = os.path.join(a.out, label, "serial")
        b["serial_meta"] = launch(py, a.harness, a.preset, "serial", 1, a.clip, a.ppp, sdir)
        ser = sers[label] = load(sdir)
        launch(py, a.harness, a.preset, "serial", 1, 0.0, a.ppp, sdir + "_clip0")
        b["predicted"] = predicted(load(sdir + "_clip0"), a.clip)
        print(label, "serial nnz", b["serial_meta"]["nnz"], "predicted", b["predicted"], flush=True)
        for k in range(a.repeats):
            odir = os.path.join(a.out, label, "jac_t%d_run%d" % (a.threads, k))
            meta = launch(py, a.harness, a.preset, "jac", a.threads, a.clip, a.ppp, odir)
            omp = load(odir)
            if not np.array_equal(omp["suscal"].view(np.int64), ser["suscal"].view(np.int64)):
                print("ERROR: suscal differs from serial in", odir, "(runs not comparable)")
                rc = 2
            d = pattern_diff(ser, omp, a.clip)
            d["run"] = odir
            d["elapsed_s"] = meta["elapsed_s"]
            b["runs"].append(d)
            print(label, "run%d" % k, json.dumps({x: d[x] for x in d if x != "run"}), flush=True)
        if label == "new":
            b["G1"] = "PASS" if all(g1_pass(r) for r in b["runs"]) else "FAIL"
        else:
            b["G3"] = "PASS" if all(r["non_flips"] > 0 for r in b["runs"]) else "FAIL (case not sensitive)"
    if a.base_python:
        sn, sb = entries(sers["new"]), entries(sers["base"])
        same = sn.keys() == sb.keys() and all(np.float64(sn[k]).tobytes() == np.float64(sb[k]).tobytes() for k in sn)
        rep["G4"] = "PASS" if same else "FAIL"
    gates = [rep["builds"]["new"]["G1"]] + ([rep["builds"]["base"]["G3"], rep["G4"]] if a.base_python else [])
    if rc == 0 and any(not g.startswith("PASS") for g in gates):
        rc = 1
    rep["result"] = {"G1": gates[0], "G3": gates[1] if a.base_python else None,
                     "G4": gates[2] if a.base_python else None, "exit": rc}
    with open(os.path.join(a.out, "clip_check.json"), "w") as f:
        json.dump(rep, f, indent=1)
    print("RESULT", json.dumps(rep["result"]))
    return rc


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "check"):
        s = sub.add_parser(name)
        s.add_argument("--harness", default=DEFAULT_HARNESS)
        s.add_argument("--preset", default="tebox")
        s.add_argument("--threads", type=int, default=4)
        s.add_argument("--clip", type=float, required=True)
        s.add_argument("--ppp", default=None, help="extra ppp settings as JSON")
    r = sub.choices["run"]
    r.add_argument("--arm", default="serial", choices=["serial", "jac"])
    c = sub.choices["check"]
    c.add_argument("--python", required=True)
    c.add_argument("--base-python", default=None)
    c.add_argument("--repeats", type=int, default=3)
    c.add_argument("--out", required=True)
    a = p.parse_args()
    if a.cmd == "run":
        worker(a)
        return 0
    if a.clip <= 0:
        p.error("--clip must be > 0 for check")
    return check(a)


if __name__ == "__main__":
    sys.exit(main())
