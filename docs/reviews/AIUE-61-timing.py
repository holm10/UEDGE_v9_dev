"""AIUE-61 G7 (and R4): interleaved timing of the OpenMP Jacobian, one UEDGE process at a time.

  python3 AIUE-61-timing.py OUTDIR BATCH         BATCH: g7 | r4 | g7it3

Every run is AIUE-61-jworker.py through AIUE-61-launch.sh (fresh `python -I` process, empty HOME, full problem, jac
arm, one Jacobian with ftol=1e20, or itermx=3 Newton iterations for g7it3) and records com.ttjstor (Jacobian time),
the exmain wall time and the Jacobian hash.

Wait for quiet (plan G7 rules, review L2-m1): before each run, poll the 1-minute load average every 15 s until
load1 <= 14 - T (14 CPUs: 10 performance, 4 efficiency); give up on the slot after 20 min (recorded as "skipped").
The threshold is never relaxed.

Order: units are shuffled with a fixed seed. A NEW/OLD pair is one unit, run back to back in random order. LEG and
the R4 settings are single units.
g7:    T=2 and T=4: 5 pairs + 5 LEG; T=8: 9 pairs + 9 LEG.
g7it3: T=4 and T=8: 3 pairs (itermx=3, mean ttjstor per Jacobian; report only).
r4:    OMPJacNchunksFixed 32 and 128 at T=4 and 8, 8 and 16 at T=8, 3 repeats each, each paired with an OLD run.
Writes OUTDIR/<batch>.jsonl (one line per run) and OUTDIR/<batch>_summary.txt (medians, min-max, the ratio of
medians NEW/OLD and LEG/OLD, the median of the paired NEW/OLD ratios; G7 PASS iff ratio of medians <= 1.10 at each T).
"""
import json, os, random, statistics, subprocess, sys, time

W = "/Users/holma/Documents/uedge/src/uedge-wt"
R = os.path.dirname(os.path.abspath(__file__))
PY = {"NEW": W + "/venvs/AIUE-61-omp/bin/python", "LEG": W + "/venvs/AIUE-61-omp/bin/python",
      "OLD": W + "/venvs/AIUE-60-omp/bin/python"}
FIX = {"OMPJacFixedChunks": 1, "OMPJacNchunksFixed": 64, "OMPJacMinChunkLen": 300}
NCPU = 14


def settings(cfg, nfix=None):
    if cfg == "NEW":
        return dict(FIX, OMPJacNchunksFixed=nfix or 64)
    if cfg == "LEG":
        return {"OMPJacFixedChunks": 0}
    return {}  # OLD: the AIUE-60 build's default (the pre-AIUE-61 partition)


def wait_quiet(T, log):
    t0 = time.time()
    while True:
        l1 = os.getloadavg()[0]
        if l1 <= NCPU - T:
            return l1, time.time() - t0
        if time.time() - t0 > 1200:
            return None, time.time() - t0
        time.sleep(15)


def run(out, batch, k, cfg, T, nfix, it3):
    name = "{}_{:03d}_{}_t{}{}".format(batch, k, cfg, T, "_n{}".format(nfix) if nfix else "")
    rd = os.path.join(out, "runs", name)
    l1, waited = wait_quiet(T, None)
    rec = {"name": name, "cfg": cfg, "T": T, "nfix": nfix, "it3": it3, "wait_s": round(waited, 1)}
    if l1 is None:
        rec["skipped"] = "busy (load above {} for 20 min)".format(NCPU - T)
        return rec
    rec["load1_start"] = round(l1, 2)
    extra = {"ppp": settings(cfg, nfix)}
    if it3:
        extra["bbb"] = {"ftol": 1e-8, "itermx": 3}
    t0 = time.time()
    subprocess.run([R + "/AIUE-61-launch.sh", PY[cfg], rd, str(T), R + "/AIUE-61-jworker.py", "full", "jac", str(T),
                    json.dumps(extra)], capture_output=True, text=True)
    rec["process_s"] = round(time.time() - t0, 2)
    rec["load1_end"] = round(os.getloadavg()[0], 2)
    try:
        j = json.load(open(os.path.join(rd, "jrun.json")))
        rec.update({"ttjstor": j["ttjstor"], "wall": j["wall"], "hash": j["jachash"], "ijactot": j.get("ijactot"),
                    "NchunksJac": j.get("NchunksJac")})
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
    return rec


def units(batch):
    u = []
    if batch == "g7":
        for T, n in ((2, 5), (4, 5), (8, 9)):
            u += [("pair", T, None, False)] * n + [("LEG", T, None, False)] * n
    elif batch == "g7it3":
        for T in (4, 8):
            u += [("pair", T, None, True)] * 3
    elif batch == "r4":
        for T, nf in ((4, 32), (4, 128), (8, 32), (8, 128), (8, 8), (8, 16)):
            u += [("pairn", T, nf, False)] * 3
    return u


def main():
    out, batch = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(out, "runs"), exist_ok=True)
    rng = random.Random(61)
    us = units(batch)
    rng.shuffle(us)
    jl = open(os.path.join(out, batch + ".jsonl"), "a")
    k = 0
    for i, (kind, T, nf, it3) in enumerate(us):
        if kind in ("pair", "pairn"):
            order = ["NEW", "OLD"]
            rng.shuffle(order)
            pair = []
            for cfg in order:
                k += 1
                rec = run(out, batch, k, cfg, T, nf if cfg == "NEW" else None, it3)
                rec["unit"] = i
                pair.append(rec)
                jl.write(json.dumps(rec) + "\n"); jl.flush()
        else:
            k += 1
            rec = run(out, batch, k, kind, T, None, it3)
            rec["unit"] = i
            jl.write(json.dumps(rec) + "\n"); jl.flush()
    jl.close()
    summarize(out, batch)


def summarize(out, batch):
    recs = [json.loads(l) for l in open(os.path.join(out, batch + ".jsonl"))]
    ok = [r for r in recs if "ttjstor" in r]
    lines = ["{} summary: {} runs, {} skipped, {} errors".format(batch, len(recs),
             sum("skipped" in r for r in recs), sum("error" in r for r in recs))]
    verdict = True
    for T in sorted({r["T"] for r in ok}):
        def vals(cfg, nfix=None):
            return [r["ttjstor"] / (r["ijactot"] if r["it3"] else 1) for r in ok
                    if r["T"] == T and r["cfg"] == cfg and r.get("nfix") == nfix]
        old = vals("OLD")
        groups = [("NEW", None), ("LEG", None)] + [("NEW", n) for n in sorted({r["nfix"] for r in ok
                                                                                 if r["nfix"]})]
        for cfg, nf in [("OLD", None)] + groups:
            v = vals(cfg, nf)
            if not v:
                continue
            lab = cfg + ("_n{}".format(nf) if nf else "")
            line = "  T={} {:8s} n={:2d} median {:7.3f} s  [{:.3f}-{:.3f}]".format(T, lab, len(v), statistics.median(v),
                                                                                  min(v), max(v))
            if cfg != "OLD" and old:
                ratio = statistics.median(v) / statistics.median(old)
                line += "  median/median(OLD) {:.3f}".format(ratio)
                # paired ratios: NEW and OLD runs of the same unit
                pr = []
                for u in {r["unit"] for r in ok if r["T"] == T and r["cfg"] == cfg and r.get("nfix") == nf}:
                    a = [r for r in ok if r["unit"] == u and r["cfg"] == cfg]
                    b = [r for r in ok if r["unit"] == u and r["cfg"] == "OLD"]
                    if a and b:
                        x = lambda r: r["ttjstor"] / (r["ijactot"] if r["it3"] else 1)  # noqa: E731
                        pr.append(x(a[0]) / x(b[0]))
                if pr:
                    line += "  paired median {:.3f} (n={})".format(statistics.median(pr), len(pr))
                if batch == "g7" and cfg == "NEW" and nf is None:
                    need = 9 if T == 8 else 5
                    full = len(v) >= need and len(old) >= need
                    verdict = verdict and full and ratio <= 1.10
                    line += "  G7 {}".format("PASS" if (full and ratio <= 1.10) else
                                             ("NOT RUN (too few valid runs)" if not full else "FAIL"))
            lines.append(line)
    if batch == "g7":
        lines.append("G7 {}".format("PASS" if verdict else "NOT PASS (see lines)"))
    open(os.path.join(out, batch + "_summary.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[3] == "--summary":
        summarize(sys.argv[1], sys.argv[2])
    else:
        main()
