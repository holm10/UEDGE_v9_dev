"""Rebuild the AIUE-54 pre-fix data set from harness run directories.

Writes, under --out:
  records/<dataset>/<relative run path>.json   copy of every run's record.json (failed runs too)
  prefix_runs.csv                              one row per run, compared bitwise against its serial reference
  prefix_stats.txt                             per-group numbers quoted in docs/rca/AIUE-8-omp-jacobian-nondeterminism.md

Usage (paths are the original scratch directories; the record.npz arrays are not committed):
  python make_prefix_data.py --out . NAME=DIR [NAME=DIR ...]

The committed data was made with these NAME=DIR pairs (DIR relative to the AIUE-8 session scratch directory):
  k2_all=AIUE-52/acc2_all_k2  k20_tebox=char_tebox_k20  k20_full=char_full_k20
  ctl_base_t4_k3/<cfg>=v56/base_<cfg>_t4_k3 for cfg in tebox full te te_phi ti ni up ng
  r54_new/<check>=r54/new/<check> for every check directory there
  k2_extra/<flow>/full/jacrhs_t<N>=<flow>/full/jacrhs_t<N> for flow in AIUE-52/acc_all_k2 AIUE-52/quick
      AIUE-52/r1/quick rev52/quick and N in 2 4 8 (where present)

A run directory is any directory holding spec.json. Its serial reference is the sibling "serial" directory of
the run's parent (flow layout <config>/<arm>_t<N>/runK and check layout <out>/runK both work). Agreement
uses the reviewed harness rules: bitwise in fnrm (final hex and every printed value), sfscal, suscal, the
post-exmain Jacobian (pattern and values) and ijactot; yldot and the RHS probe may differ in the sign of a
zero only when the record says the RHS was parallel (PRD P3-m2).
"""
import argparse
import collections
import csv
import glob
import hashlib
import json
import os
import re
import shutil

import numpy as np

EQ = ["ni", "up", "te", "ti", "ng", "tg", "phi"]
FTOL = 1e20


def eqname(c):
    return EQ[int(c)] if int(c) >= 0 else "?"


def bits(a):
    return np.ascontiguousarray(a, dtype=np.float64).view(np.uint64)


def iter_fnrm_from_log(path):
    """Printed fnrm per iteration of the harness exmain: the 'OMP iter=' lines of an OpenMP run, else the
    lines after the first 'Updating Jacobian' (the deck's own exmain prints an earlier iteration 0)."""
    try:
        t = open(path, errors="replace").read()
    except OSError:
        return []
    omp = re.findall(r"OMP iter=\s+(\d+)\s+fnrm=\s+(\S+)", t)
    if omp:
        return [(int(a), b) for a, b in omp]
    i = t.find("Updating Jacobian")
    t = t[i:] if i >= 0 else t
    return [(int(a), b) for a, b in re.findall(r"iter=\s+(\d+)\s+fnrm=\s+(\S+)", t)]


def load(d):
    rec, arr = None, None
    p = os.path.join(d, "record.json")
    if os.path.exists(p):
        try:
            rec = json.load(open(p))
        except ValueError:
            rec = {"error": "unreadable record.json"}
    z = os.path.join(d, "record.npz")
    if os.path.exists(z):
        f = np.load(z)
        arr = {k: f[k] for k in f.files}
    return rec, arr


def keys(a):
    ia = a["jaci_post"]
    n = len(ia) - 1
    rows = np.repeat(np.arange(n, dtype=np.int64), np.diff(ia))
    cols = a["jacj_post"].astype(np.int64) - 1
    return rows * n + cols, rows, cols


def compare(s, x, rhs_parallel):
    """Return a dict of mismatch counts between serial (s) and run (x) arrays/records."""
    (rs, zs), (rx, zx) = s, x
    out = {}
    eq = zs["eq"]
    ks, _, _ = keys(zs)
    kx, rowx, colx = keys(zx)
    n = len(zs["jaci_post"]) - 1
    os_ = np.argsort(ks)
    ox = np.argsort(kx)
    ks_s, kx_s = ks[os_], kx[ox]
    in_s = np.isin(kx_s, ks_s, assume_unique=True)
    in_x = np.isin(ks_s, kx_s, assume_unique=True)
    vs = zs["jac_post"][os_][in_x]
    vx = zx["jac_post"][ox][in_s]
    vd = bits(vs) != bits(vx)
    extra_k = kx_s[~in_s]
    miss_k = ks_s[~in_x]
    val_k = kx_s[in_s][vd]
    out["jac_extra"] = int(len(extra_k))
    out["jac_missing"] = int(len(miss_k))
    out["jac_valdiff"] = int(vd.sum())
    out["jac_entries_differ"] = out["jac_extra"] + out["jac_missing"] + out["jac_valdiff"]
    bad_rows = set((np.concatenate([extra_k, miss_k, val_k]) // n).tolist())
    sf = np.nonzero(bits(zs["sfscal"]) != bits(zx["sfscal"]))[0]
    su = np.nonzero(bits(zs["suscal"]) != bits(zx["suscal"]))[0]
    out["sfscal_rows_differ"] = int(len(sf))
    out["suscal_rows_differ"] = int(len(su))
    bad_rows |= set(sf.tolist()) | set(su.tolist())
    for name in ("yldot", "yldot_probe"):
        a, b = zs[name], zx[name]
        strict = bits(a) != bits(b)
        sz = strict & (a == 0) & (b == 0)
        out[name + "_differ"] = int(strict.sum() - sz.sum())
        out[name + "_signed_zero"] = int(sz.sum())
        tolerant = rhs_parallel
        d = np.nonzero(strict & ~sz)[0] if tolerant else np.nonzero(strict)[0]
        out[name + "_counted"] = int(len(d))
        bad_rows |= set(d.tolist())
    out["mismatch_row_eqs"] = "+".join(sorted({eqname(eq[r]) for r in bad_rows}, key=EQ.index)) if bad_rows else ""
    fp_s = [i["fnrm_printed"] for i in rs.get("iterations", [])]
    fp_x = [i["fnrm_printed"] for i in rx.get("iterations", [])]
    agree = (out["jac_entries_differ"] == 0 and not len(sf) and not len(su)
             and out["yldot_counted"] == 0 and out["yldot_probe_counted"] == 0
             and rs.get("fnrm_final_hex") == rx.get("fnrm_final_hex") and fp_s == fp_x
             and rs.get("ijactot") == rx.get("ijactot"))
    out["agrees_with_serial"] = "yes" if agree else "no"
    absj = np.abs(zx["jac_post"])
    out["max_abs_jac"] = float(absj.max()) if len(absj) else 0.0
    out["min_abs_jac"] = float(absj.min()) if len(absj) else 0.0
    # extra entries by column equation (full-problem breakdown)
    out["_extra_cols"] = collections.Counter(eqname(eq[c]) for c in (extra_k % n).tolist()) if len(extra_k) < 2_000_000 else None
    return out


def digest(rx, zx):
    h = hashlib.sha1()
    for k in ("jaci_post", "jacj_post", "jac_post", "sfscal", "suscal", "yldot", "yldot_probe"):
        h.update(np.ascontiguousarray(zx[k]).tobytes())
    h.update(str(rx.get("fnrm_final_hex")).encode())
    h.update(str([i["fnrm_printed"] for i in rx.get("iterations", [])]).encode())
    return h.hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("datasets", nargs="+", help="NAME=DIR")
    a = ap.parse_args()
    rows = []
    groups = collections.defaultdict(list)
    extra_cols = {}
    for item in a.datasets:
        name, root = item.split("=", 1)
        root = os.path.abspath(root)
        for sp in sorted(glob.glob(os.path.join(root, "**", "spec.json"), recursive=True)):
            d = os.path.dirname(sp)
            rel = os.path.relpath(d, root)
            if os.path.basename(d) == "serial":
                continue
            spec = json.load(open(sp))
            rec, arr = load(d)
            ser_dir = os.path.join(os.path.dirname(d), "serial")
            if not os.path.isdir(ser_dir):
                ser_dir = os.path.join(os.path.dirname(os.path.dirname(d)), "serial")
            srec, sarr = load(ser_dir)
            dst = os.path.join(a.out, "records", name, rel + ".json")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(os.path.join(d, "record.json")):
                shutil.copyfile(os.path.join(d, "record.json"), dst)
            sdst = os.path.join(a.out, "records", name, os.path.relpath(ser_dir, root) + ".json")
            if srec is not None and not os.path.exists(sdst):
                os.makedirs(os.path.dirname(sdst), exist_ok=True)
                shutil.copyfile(os.path.join(ser_dir, "record.json"), sdst)
            log_iters = iter_fnrm_from_log(os.path.join(d, "run.log"))
            pv = (rec or {}).get("provenance", {})
            row = {
                "dataset": name, "path": rel, "configuration": spec["preset"], "arm": spec["arm"],
                "threads": spec["threads"], "itermx": spec.get("itermx") or "", "ppp": json.dumps(spec.get("ppp") or {}, sort_keys=True) if spec.get("ppp") else "",
                "harness_commit": (pv.get("harness_commit") or pv.get("commit") or "")[:7],
                "ParallelJac": pv.get("ParallelJac", ""), "ParallelPandf1": pv.get("ParallelPandf1", ""),
                "Nthreads": pv.get("Nthreads", ""), "OMP_NUM_THREADS": pv.get("OMP_NUM_THREADS", ""),
            }
            if rec is None:
                row["status"] = "no record (see run.log; exit -11 in the flow summary)"
            elif "error" in rec:
                row["status"] = "error: " + rec["error"].strip().splitlines()[-1].strip()[:80]
            else:
                row["status"] = "ok"
            it = (rec or {}).get("iterations") or [{"iter": i, "fnrm_printed": f} for i, f in log_iters]
            row["n_iterations_logged"] = len(it)
            row["fnrm_printed_iter0"] = it[0]["fnrm_printed"] if it else ""
            row["fnrm_printed_last"] = it[-1]["fnrm_printed"] if it else ""
            row["iter0_fnrm_above_ftol"] = "yes" if it and float(it[0]["fnrm_printed"].replace("D", "E")) > FTOL else "no" if it else ""
            row["ijactot"] = (rec or {}).get("ijactot", "")
            row["fnrm_final_hex"] = (rec or {}).get("fnrm_final_hex", "")
            row["nnz_post_exmain"] = (rec or {}).get("nnz_post", "")
            stored = ""
            if row["status"] == "ok":
                stored = "iteration 0 (sfsetnk, 1/suscal)" if rec.get("ijactot") == 1 else "later iteration (ijactot={})".format(rec.get("ijactot"))
                if rec.get("post_exmain_from") == "psetnk":
                    stored += ", psetnk (row-normalised, permuted)"
            row["stored_jacobian"] = stored
            row["elapsed_s"] = (rec or {}).get("elapsed_s", "")
            row["serial_fnrm_iter0"] = (srec or {}).get("iterations", [{}])[0].get("fnrm_printed", "") if srec else ""
            row["serial_nnz"] = (srec or {}).get("nnz_post", "") if srec else ""
            row["serial_elapsed_s"] = (srec or {}).get("elapsed_s", "") if srec else ""
            if arr is not None and sarr is not None and "error" not in srec:
                c = compare((srec, sarr), (rec, arr), bool(rec.get("rhs_probe_parallel")))
                ec = c.pop("_extra_cols")
                if ec is not None and spec["preset"] == "full":
                    extra_cols[(name, rel)] = ec
                row.update(c)
                row["digest"] = digest(rec, arr)
            else:
                row["agrees_with_serial"] = "no (run failed)" if row["status"] != "ok" else ""
            rows.append(row)
            groups[(name, spec["preset"], spec["arm"], spec["threads"], row["itermx"], row["ppp"])].append(row)
    fields = ["dataset", "path", "harness_commit", "configuration", "arm", "threads", "itermx", "ppp", "status",
              "agrees_with_serial", "ijactot", "n_iterations_logged", "iter0_fnrm_above_ftol", "fnrm_printed_iter0",
              "fnrm_printed_last", "fnrm_final_hex", "nnz_post_exmain", "stored_jacobian", "jac_entries_differ",
              "jac_extra", "jac_missing", "jac_valdiff", "sfscal_rows_differ", "suscal_rows_differ", "yldot_differ",
              "yldot_signed_zero", "yldot_probe_differ", "yldot_probe_signed_zero", "mismatch_row_eqs",
              "max_abs_jac", "min_abs_jac", "elapsed_s", "serial_fnrm_iter0", "serial_nnz", "serial_elapsed_s",
              "ParallelJac", "ParallelPandf1", "Nthreads", "OMP_NUM_THREADS", "digest"]
    with open(os.path.join(a.out, "prefix_runs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(a.out, "prefix_stats.txt"), "w") as f:
        f.write("# generated by make_prefix_data.py; compact table first, then one block per group\n")
        f.write("# group | runs | ok | agree | arm engaged | iter0 fnrm>ftol | ijactot | distinct results | "
                "mismatch rows | elapsed_s (serial)\n")
        order = sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0]))
        for g, rs in order:
            ok = [r for r in rs if r["status"] == "ok"]
            cmp_ = [r for r in ok if "digest" in r]
            el = [r["elapsed_s"] for r in ok]
            f.write("{:<70} | {} | {} | {} | {} | {} | {} | {} | {} | {} ({})\n".format(
                " ".join(str(x) for x in g if x != ""), len(rs), len(ok),
                sum(r.get("agrees_with_serial") == "yes" for r in rs), sum(engaged(r) for r in ok),
                sum(r["iter0_fnrm_above_ftol"] == "yes" for r in rs),
                dict(collections.Counter(r["ijactot"] for r in ok)), len({r["digest"] for r in cmp_}),
                sorted({r["mismatch_row_eqs"] or "none" for r in cmp_}),
                "{}-{}".format(min(el), max(el)) if el else "-", ok[0]["serial_elapsed_s"] if ok else "-"))
        for g, rs in order:
            ok = [r for r in rs if r["status"] == "ok"]
            f.write("\n== dataset {} | {} | arm {} | threads {} | itermx {} | ppp {}\n".format(*[x or "-" for x in g]))
            f.write("   runs {}  ok {}  harness {}\n".format(len(rs), len(ok), sorted({r["harness_commit"] for r in rs})))
            f.write("   status: {}\n".format(dict(collections.Counter(r["status"] for r in rs))))
            f.write("   agree with serial: {}/{}\n".format(sum(r.get("agrees_with_serial") == "yes" for r in rs), len(rs)))
            f.write("   arm engaged (ParallelJac/ParallelPandf1/Nthreads as the arm requires): {}/{}\n".format(
                sum(engaged(r) for r in ok), len(ok)))
            above = [r for r in rs if r["iter0_fnrm_above_ftol"] == "yes"]
            f.write("   iteration-0 fnrm > ftol=1e20: {}/{} {}\n".format(len(above), len(rs), sorted(float(r["fnrm_printed_iter0"]) for r in above)))
            f.write("   ijactot: {}\n".format(dict(collections.Counter(r["ijactot"] for r in ok))))
            for part, sub in (("ijactot=1", [r for r in ok if r["ijactot"] == 1]), ("ijactot>1", [r for r in ok if r["ijactot"] != 1])):
                if not sub:
                    continue
                fp = [float(r["fnrm_printed_iter0"]) for r in sub]
                fl = [float(r["fnrm_printed_last"]) for r in sub]
                nnz = [r["nnz_post_exmain"] for r in sub]
                f.write("   [{}] n={} fnrm iter0: distinct {} min {!r} max {!r} most common {}\n".format(
                    part, len(sub), len(set(fp)), min(fp), max(fp), collections.Counter(r["fnrm_printed_iter0"] for r in sub).most_common(2)))
                if part != "ijactot=1":
                    f.write("      fnrm last printed: min {!r} max {!r}\n".format(min(fl), max(fl)))
                f.write("      nnz stored: distinct {} range {}-{} {}\n".format(len(set(nnz)), min(nnz), max(nnz), collections.Counter(nnz).most_common(4)))
                cmp_ = [r for r in sub if "jac_entries_differ" in r]
                if cmp_:
                    for k in ("jac_entries_differ", "jac_extra", "jac_missing", "sfscal_rows_differ", "yldot_differ",
                              "yldot_signed_zero", "yldot_probe_differ", "max_abs_jac", "min_abs_jac"):
                        v = [r[k] for r in cmp_]
                        f.write("      {}: {}-{}  (zero in {}/{})\n".format(k, min(v), max(v), sum(x == 0 for x in v), len(v)))
                    f.write("      mismatch row equations: {}\n".format(dict(collections.Counter(r["mismatch_row_eqs"] for r in cmp_))))
                    f.write("      distinct results (digest of Jacobian, scalings, yldot, probe, fnrm): {} of {}\n".format(
                        len({r["digest"] for r in cmp_}), len(cmp_)))
                el = [r["elapsed_s"] for r in sub]
                f.write("      elapsed_s: {}-{}; serial reference {}\n".format(min(el), max(el), sub[0]["serial_elapsed_s"]))
            if ok:
                f.write("   serial reference: fnrm iter0 {} nnz {}\n".format(ok[0]["serial_fnrm_iter0"], ok[0]["serial_nnz"]))
        if extra_cols:
            f.write("\n== full problem: extra Jacobian entries by column equation (per run)\n")
            for (name, rel), c in sorted(extra_cols.items()):
                tot = sum(c.values()) or 1
                f.write("   {} {}: {}\n".format(name, rel, ", ".join("{} {:.0f}%".format(k, 100 * v / tot) for k, v in c.most_common())))


def engaged(r):
    arm, th = r["arm"], r["threads"]
    pj = (r["ParallelJac"] or 0) > 0
    pr = (r["ParallelPandf1"] or 0) > 0
    if arm == "serial":
        return not pj and not pr
    return pj and pr == (arm == "jacrhs") and r["Nthreads"] == th and str(r["OMP_NUM_THREADS"]) == str(th)


if __name__ == "__main__":
    main()
