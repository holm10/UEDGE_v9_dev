"""Round-off measurement of the yldot families and the tolerances derived from it (epic AIUE-9, PRD sections 7.4 and
7.7; AIUE-87).

Usage:
    <build's python> measure_roundoff.py collect <family>... --label L --out DIR --build FILE [--omp N ...]
    python measure_roundoff.py analyze DIR [--write] [--report FILE] [--families DIR] [--toml FILE]

collect  runs inside one build's venv (or the pinned Linux container, linux/collect.sh). Per family and
         configuration (steady, timestep), two fresh processes evaluate the protocol of harness/state.py (PRD
         section 6) and pickle yldot, yldot_J and the index arrays to DIR/L/<family>.<config>.<run>.pkl, with the
         build record of FILE (JSON: commit, options, compiler, platform, venv or image, date). A crash, an error or
         a timeout (TIMEOUT_FACTOR x family.toml timeout_s) is pickled too, with the log tail: a --debug trap is a
         finding, not a failure. --omp N (OpenMP build only)
         adds one process per N with ppp.OMPParallelJac = ppp.OMPParallelPandf1 = 1, ppp.Nthreads = N and
         OMP_NUM_THREADS = N, which after the protocol evaluates the RHS once through bbb.ffun (OpenMP) and once
         through bbb.pandf (serial) and records the effective ppp.Nthreads (ppp clamps it to OMP_GET_MAX_THREADS(),
         ppp/omp_parallel.F90:296-303); file <family>.<config>.omp<N>.pkl.
analyze  pairs the collections and reports, per family, configuration, pair and equation, the largest absolute
         spread, the block-normalised relative spread s = max_i |d_i| / max_i |ref_i| over the equation's rows
         (d over yldot and yldot_J; ref the pair's second side) and the largest per-entry relative spread. Then
         the floor report and the AIUE-81 re-check. --write writes tolerances.toml and families/<f>/sigma.h5.

Pairs (first side against second; run 1 unless named):
    same_build:<L>  run 1 against run 2 of every label L                         serial, expected exactly 0
    o0_vs_o3        mac-noopt (--serial --noopt, -O0) against mac-serial (-O3)    serial
    mac_vs_linux    linux-serial against mac-serial                               serial
    debug_vs_o3     mac-debug (--serial --debug, -Og, FPE traps) against mac-serial   report only
    omp_<N>         mac-omp ffun against mac-serial, and against pandf in the same process   report only (AIUE-59)
Only the serial pairs feed sigma and rtol (PRD section 7.7). Owner decisions (2026-10-21, AIUE-87 ticket page):
    rtol_eq  = max(RTOL_FACTOR * max s, RTOL_FLOOR), one value per equation over every family, configuration and
               serial pair;
    sigma_i  = max over the serial pairs of max(|d yldot_i|, |d yldot_J_i|), per family and configuration, written
               to families/<f>/sigma.h5 (/<config>/sigma, /<config>/source = the code of the pair that set it, -1
               where sigma_i = 0; root attributes pairs and schema);
    k        = K (PRD section 7.4).
Floor report (PRD section 7.4): per family, configuration and (equation, species, region), the fraction of entries
with sigma_i = 0 and the distribution of k * sigma_min,r / |ref_i| over them (ref_i = 0 counted apart); a group over
10 % goes to the epic owner. AIUE-81 re-check: per (equation, species) block, RMS(yldot at the base state) /
RMS(tol_i), how far the perturbed base state sits above the tolerance.

Builds (from one commit, venvs as ../uedge-wt/venvs/<KEY>-<kind>; BUILD.txt per venv):
    pip install --no-build-isolation . -C "--build-option=--serial"                                   mac-serial
    pip install --no-build-isolation . -C "--build-option=--serial" -C "--build-option=--noopt"      mac-noopt
    pip install --no-build-isolation . -C "--build-option=--serial" -C "--build-option=--debug"      mac-debug
    pip install --no-build-isolation .                                                                mac-omp
    tests/yldot/linux/collect.sh (Docker, pinned Ubuntu image)                                         linux-serial

Every evaluation runs in a fresh process (Forthon state is global), cwd the family directory, HOME an empty
temporary directory, UEDGE_BANNER=0. Exit codes: 0 ok, 2 usage or evaluation error, 3 a finding the owner has to
look at (a floor group over 10 %, a ToleranceEscalation, index arrays that differ between builds, an effective
Nthreads not above 1 for N > 1), 4 a defect: a nonzero same-build spread (file a bugfix/v9-* ticket per family,
never absorb it).
"""
import argparse
import hashlib
import json
import math
import os
import pickle
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

if __name__ == "__main__" and sys.argv[1:2] == ["_worker"]:
    # before yldot.harness, whose import pins OMP_NUM_THREADS=1: libgomp reads it once, when uedge loads it
    if Path(".uedgerc.py").exists():
        sys.exit("refused: {} holds .uedgerc.py".format(Path.cwd()))
    import uedge  # noqa: F401

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package
from yldot.harness import FAMILIES, FamilyError, compare, load_evaluation  # noqa: E402
from yldot.harness.process import family_dir  # noqa: E402
from yldot.harness.state import INDEX_ARRAYS, MASK_ARRAYS  # noqa: E402

CONFIGS = ("steady", "timestep")
RUNS = ("1", "2")
K = 100.0
RTOL_FACTOR = 100.0
RTOL_FLOOR = 1e-14
FLOOR_LIMIT = 0.10  # owner-confirmed, decision 30
SCHEMA = 1
TIMEOUT_FACTOR = 5  # x family.toml timeout_s per collect child: the debug build and x86 emulation run slower
REF = "mac-serial"
SUITE = Path(__file__).resolve().parents[1]
# (name, first label, second label, serial); same_build:<L> is added for every label collected
PAIRS = (("o0_vs_o3", "mac-noopt", REF, True),
         ("mac_vs_linux", "linux-serial", REF, True),
         ("debug_vs_o3", "mac-debug", REF, False))
OMP_LABEL = "mac-omp"
REPORT_ONLY = ("mac-debug",)  # -Og with FPE traps: never in sigma or rtol (PRD 7.7); its same-build pair still checks
FLOOR_RULE = ("PRD 7.4: tol_i = max(rtol_eq*|ref_i|, k*sigma_i) where sigma_i > 0; where sigma_i = 0, "
              "max(rtol_eq*|ref_i|, k*sigma_min,r), sigma_min,r the smallest non-zero sigma of the entry's "
              "(equation, species, region), else of its (equation, species) over the family, else the epic owner")
SIGMA_RULE = "max over the serial pairs of max(|d yldot_i|, |d yldot_J_i|), per family and configuration"
# The epic owner's answers to what analyze sends them (decision 23), written to tolerances.toml [owner]; a later run
# that sends new items adds the new answers here (AIUE-87 ticket page, Findings and decisions)
OWNER_ANSWERS = (
    "2026-10-22, AIUE-87: every floor group over 10 % (sigma = 0 in rows bitwise identical across the serial builds) is "
    "accepted with the PRD 7.4 floor unchanged; d_mols phi[1] guard ix=7 iy=0 (ref -37.6) gets k*sigma_min,r = "
    "1.5e-3*|ref| from the ix=9 guard cells, and keeps the floor: AIUE-150 (no code change) found two base-state noise "
    "draws that nearly match in a dphi/dy = 0 boundary row",
    "2026-10-22, AIUE-87: the --debug bounds-check stop at bbb/pandf_plasma_energy.m:603 (ng(ix,iy,2) with ngsp = 1) "
    "is bug AIUE-145",
    "2026-10-22, AIUE-87: the OpenMP crashes with OMPParallelJac/OMPParallelPandf1 = 1 are bug AIUE-146; the measured "
    "OpenMP rows stay report only",
    "2026-10-22, AIUE-92: the owner families' floor groups over 10 % (53 per configuration; the same groups after "
    "AIUE-170, 2026-10-23) are accepted with the PRD 7.4 floor unchanged; the quiet-cell mutation stays at slab_phi "
    "(18,1)",
    "2026-10-23, AIUE-92: imp7's spread at its inner-target corner (1,42) and guard (0,42), which would have raised "
    "ni, up, ti and phi (AIUE-164), is removed by com.redopltvtag = 1 in imp7's deck (AIUE-170); imp7 sets no rtol",
    "2026-10-23, AIUE-92: up rises from 1.505e-8 to 1.589e-8, set by dnull_imp2 up[2] on its wall ring iy = ny "
    "(-O3 arm64 against -O0 and Linux, 2.3e-8 of the entry): accepted",
)
OWNER_ITEMS_ANSWERED = 290  # the owner items of the run those answers cover (the 145 floor groups per configuration)


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- child side


THREADS = 0  # set by worker for an --omp child (yldot.harness has pinned OMP_NUM_THREADS to 1 by then)


def omp_pre(bbb, com):
    """The pre hook of an --omp child: the OpenMP RHS and Jacobian (rhs_probe.py), Nthreads from the job."""
    from uedge import ppp

    ppp.OMPParallelJac = 1
    ppp.OMPParallelPandf1 = 1
    ppp.Nthreads = THREADS


def worker(job):
    """Runs in the child, cwd = family directory. Writes its results to job['out']."""
    global THREADS
    from yldot.harness import state

    THREADS = job["omp"]

    spec = {"family": str(Path.cwd()), "config": job["config"], "mode": "spawn", "w": job["w"], "p": job["p"],
            "dt": job["dt"], "diagnostics": False, "pre": None, "post": "__main__:omp_pre" if job["omp"] else None,
            "variant": None, "log": None}
    try:
        out = state.evaluate(spec)
    except state.Stop as e:
        print("{}: {}".format(e.status, e), file=sys.stderr)
        return 3 if e.status in ("owner", "refused") else 2
    if job["omp"]:
        from uedge import bbb, ppp

        neq = out["neq"]
        yl = np.array(bbb.yl[:neq + 2])  # step 8b left yl[neq] = -1

        def rhs(f):
            o = np.zeros(neq + 2)
            f(yl.copy(), o)
            return o[:neq].copy()

        out["ffun"] = rhs(lambda y, o: bbb.ffun(neq, 0.0, y, o))
        out["pandf"] = rhs(lambda y, o: bbb.pandf(-1, -1, neq, 0.0, y, o))
        out["nthreads"] = int(ppp.Nthreads)
        out["parallel_pandf1"] = int(bbb.ParallelPandf1)
    out["machine"], out["platform"] = platform.machine(), sys.platform
    with open(job["out"], "wb") as f:
        pickle.dump(out, f)
    return 0


# ---------------------------------------------------------------- collect


def run_child(fdir, job, threads, timeout):
    """One fresh process; returns the unpickled results, or a record of the crash, error or timeout with the log
    tail."""
    with tempfile.TemporaryDirectory(prefix="yldot-home-") as home, \
            tempfile.TemporaryDirectory(prefix="yldot-out-") as outdir:
        job = dict(job, out=os.path.join(outdir, "out.pkl"))
        env = dict(os.environ, HOME=home, UEDGE_BANNER="0", OMP_NUM_THREADS=str(threads), OPENBLAS_NUM_THREADS="1",
                   GFORTRAN_UNBUFFERED_PRECONNECTED="y")
        try:
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_worker", json.dumps(job)],
                                  cwd=fdir, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            text = (e.stdout or b"").decode(errors="replace") + (e.stderr or b"").decode(errors="replace")
            return {"status": "timeout", "exitcode": None,
                    "log_tail": "\n".join(text.splitlines()[-40:]) + "\n(killed after {:g} s)".format(timeout)}
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-40:])
        # a child that wrote its whole result and then died at exit (seen with the OpenMP flags) keeps its result;
        # the exit code goes to the findings
        try:
            with open(job["out"], "rb") as f:
                out = pickle.load(f)
        except (OSError, EOFError, pickle.UnpicklingError):
            if proc.returncode == 0:
                return {"status": "error", "exitcode": 0, "log_tail": tail + "\n(no result written)"}
            return {"status": "crash" if proc.returncode < 0 else "error", "exitcode": proc.returncode,
                    "log_tail": tail}
        out.update(status="ok", exitcode=proc.returncode)
        if proc.returncode != 0:
            out["log_tail"] = tail
        return out


def cmd_collect(args):
    try:
        build = json.loads(Path(args.build).read_text())
    except (OSError, ValueError) as e:
        raise Stop(2, "--build {}: {}".format(args.build, e))
    dest = Path(args.out) / args.label
    dest.mkdir(parents=True, exist_ok=True)
    code = 0
    for name in args.family:
        try:
            fdir = family_dir(name)
        except FamilyError as e:
            raise Stop(2, str(e))
        ev = load_evaluation(fdir)
        for config in CONFIGS:
            job = {"config": config, "w": int(ev["w"]), "p": int(ev["p"]), "dt": float(ev["dt_timestep_s"]),
                   "omp": 0}
            runs = [(run, job, 1) for run in RUNS]
            runs += [("omp{}".format(n), dict(job, omp=n), n) for n in args.omp]
            for run, j, threads in runs:
                out = run_child(fdir, j, threads, TIMEOUT_FACTOR * float(ev["timeout_s"]))
                out.update(label=args.label, family=fdir.name, config=config, run=run, build=build)
                with open(dest / "{}.{}.{}.pkl".format(fdir.name, config, run), "wb") as f:
                    pickle.dump(out, f)
                extra = " Nthreads={}".format(out.get("nthreads")) if run.startswith("omp") else ""
                print("{} {} {} {}: {}{}".format(args.label, fdir.name, config, run, out["status"], extra))
                if out["status"] != "ok":
                    print(out["log_tail"], file=sys.stderr)
                    code = 2
    return code


# ---------------------------------------------------------------- analyze: loading and pairing


def load(directory):
    """{label: {(family, config, run): result}} from DIR/<label>/*.pkl."""
    out = {}
    for path in sorted(Path(directory).glob("*/*.pkl")):
        with open(path, "rb") as f:
            r = pickle.load(f)
        out.setdefault(path.parent.name, {})[(r["family"], r["config"], r["run"])] = r
    if not out:
        raise Stop(2, "no collections under {}".format(directory))
    return out


def same_index(a, b):
    """The index arrays, masks and neq of two results agree exactly."""
    if a["neq"] != b["neq"]:
        return False
    if not all(np.array_equal(a[n], b[n]) for n in INDEX_ARRAYS):
        return False
    return all(np.array_equal(a["masks"][n], b["masks"][n]) for n in MASK_ARRAYS)


def finite(name, a):
    if not np.isfinite(a).all():
        raise Stop(2, "{}: non-finite entries at rows {}".format(name, compare.listed(
            np.flatnonzero(~np.isfinite(a)) + 1)))
    return a


def pair_list(data):
    """[(name, first label, first run, second label, second run, serial)] for the labels collected, sorted."""
    pairs = [("same_build:" + label, label, "1", label, "2", label not in REPORT_ONLY) for label in sorted(data)]
    pairs += [(name, a, "1", b, "1", serial) for name, a, b, serial in PAIRS]
    return sorted(pairs)


def spreads(a, b, imap):
    """Per entry d = max(|d yldot|, |d yldot_J|), and per equation max_abs, max_ref, s and max_rel."""
    dy = np.abs(a["yldot"] - b["yldot"])
    dj = np.abs(a["yldot_J"] - b["yldot_J"])
    d = np.maximum(dy, dj)
    ref = np.maximum(np.abs(b["yldot"]), np.abs(b["yldot_J"]))
    raw = {}
    for name, _, _ in compare.EQUATIONS:
        rows = np.flatnonzero(imap.eq == name)
        if not rows.size:
            continue
        max_abs, max_ref = float(d[rows].max()), float(ref[rows].max())
        s = 0.0 if max_abs == 0 else (max_abs / max_ref if max_ref > 0 else math.inf)
        nz = rows[ref[rows] > 0]
        rel = float((d[nz] / ref[nz]).max()) if nz.size else 0.0
        raw[name] = {"max_abs": max_abs, "max_ref": max_ref, "s": s, "max_rel": rel}
    return d, raw


class Analysis:
    def __init__(self, data, families_dir):
        self.data = data
        self.families_dir = Path(families_dir)
        self.pairs = pair_list(data)
        self.serial = [p[0] for p in self.pairs if p[5]]
        self.defects, self.owner, self.findings, self.notes = [], [], [], []
        self.over = []  # (family, config) per floor group over FLOOR_LIMIT
        self.raw = {}  # (family, config, pair) -> {equation: {...}}
        self.sigma = {}  # family -> {config: (sigma, source)}
        self.imaps = {}  # (family, config) -> IndexMap
        self.refs = {}  # (family, config) -> the mac-serial run 1 result
        self.omp = []

    def get(self, label, family, config, run):
        return self.data.get(label, {}).get((family, config, run))

    def families(self):
        return sorted({k[0] for label in self.data.values() for k in label})

    def run(self):
        for label in sorted(self.data):
            for (family, config, run), r in sorted(self.data[label].items()):
                if r["status"] == "ok" and r.get("exitcode", 0) != 0:
                    self.findings.append("{} {} {} {}: exit code {} after the result was written".format(
                        label, family, config, run, r["exitcode"]))
                elif r["status"] != "ok":
                    where = [s for s in r["log_tail"].splitlines() if s.startswith(("At line", "Fortran runtime"))]
                    self.findings.append("{} {} {} {}: {} (exit {}){}".format(
                        label, family, config, run, r["status"], r["exitcode"],
                        ": " + " ".join(where) if where else ""))
        for family in self.families():
            regions = compare.load_regions(self.families_dir / family)
            for config in CONFIGS:
                ref = self.get(REF, family, config, "1")
                if ref is None or ref["status"] != "ok":
                    raise Stop(2, "{} {}: no {} run 1 to pair against".format(family, config, REF))
                imap = compare.index_map(ref, regions)
                self.imaps[(family, config)], self.refs[(family, config)] = imap, ref
                for a in ("yldot", "yldot_J"):
                    finite("{} {} {} {}".format(REF, family, config, a), ref[a])
                self.pair_family(family, config, imap)
                self.openmp(family, config, ref)

    def pair_family(self, family, config, imap):
        neq = imap.neq
        sigma, source = np.zeros(neq), np.full(neq, -1, dtype=np.int8)
        for name, la, ra, lb, rb, serial in self.pairs:
            a, b = self.get(la, family, config, ra), self.get(lb, family, config, rb)
            where = "{} {} {}".format(family, config, name)
            if a is None or b is None:
                if serial:
                    self.notes.append("{}: not measured ({} {} / {} {} missing)".format(
                        where, la, ra, lb, rb))
                continue
            failed = [r for r in (a, b) if r["status"] != "ok"]
            if failed:  # a report-only pair skips it: run() lists every failed result once
                r = failed[0]
                if serial:
                    raise Stop(2, "{}: {} run {} {} (exit {}):\n{}".format(where, r["label"], r["run"], r["status"],
                                                                          r["exitcode"], r["log_tail"]))
                continue
            if not same_index(a, b):
                self.owner.append("{}: the index arrays differ between {} and {}; {}".format(
                    where, la, lb, compare.OWNER))
                continue
            for r in (a, b):
                for v in ("yldot", "yldot_J"):
                    finite("{} {} {}".format(where, r["label"], v), r[v])
            d, raw = spreads(a, b, imap)
            self.raw[(family, config, name)] = raw
            if name.startswith("same_build:") and d.any():
                self.defects.append("{}: {} entries differ between two processes of the same build (max {:.3e}); "
                                    "file a bugfix/v9-* ticket".format(where, int(np.count_nonzero(d)), d.max()))
            if serial:
                code = self.serial.index(name)
                up = d > sigma
                sigma[up], source[up] = d[up], code
        self.sigma.setdefault(family, {})[config] = (sigma, source)

    def openmp(self, family, config, ref):
        for (f, c, run), r in sorted(self.data.get(OMP_LABEL, {}).items()):
            if (f, c) != (family, config) or not run.startswith("omp"):
                continue
            n = int(run[3:])
            row = {"family": family, "config": config, "threads": n, "status": r["status"]}
            shapes = {k: np.shape(r[k]) for k in ("ffun", "pandf") if k in r}
            if r["status"] == "ok" and set(shapes.values()) != {(ref["neq"],)}:
                row["status"] = "corrupt"
                self.findings.append("{} {} {}: result vectors of shapes {} for neq = {} (memory overwritten in the "
                                     "child)".format(family, config, run, shapes, ref["neq"]))
            elif r["status"] != "ok":
                row["exitcode"] = r["exitcode"]
            else:
                row.update(nthreads=r["nthreads"], parallel_pandf1=r["parallel_pandf1"])
                for what, other in (("vs_serial_build", ref["yldot"]), ("vs_pandf", r["pandf"])):
                    d = np.abs(r["ffun"] - other)
                    row[what] = {"rows": int(np.count_nonzero(d)), "max_abs": float(d.max()),
                                 "max_rel": float((d / np.maximum(np.abs(other), 1e-300)).max())}
                if n > 1 and r["nthreads"] <= 1:
                    self.owner.append("{} {} {}: effective Nthreads = {} for N = {}".format(
                        family, config, run, r["nthreads"], n))
            self.omp.append(row)

    # ------------------------------------------------------------ results

    def rtol(self):
        """{equation: (value, source)}: max(RTOL_FACTOR * max s over the serial pairs, RTOL_FLOOR)."""
        best = {}
        for (family, config, pair), raw in sorted(self.raw.items()):
            if pair not in self.serial:
                continue
            for eq, r in raw.items():
                if eq not in best or r["s"] > best[eq][0]:
                    best[eq] = (r["s"], "{} {} {}".format(family, config, pair))
        out = {}
        for eq, _, _ in compare.EQUATIONS:
            if eq in best:
                s, src = best[eq]
                v = max(RTOL_FACTOR * s, RTOL_FLOOR)
                out[eq] = (v, src if RTOL_FACTOR * s >= RTOL_FLOOR else "floor (largest s {:.3e}, {})".format(s, src))
        return out

    def floors(self):
        """Floor report rows: (family, config, eq, sp, region, n, zeros, n_ref0, min, median, max), with the
        sigma_min,r of compare.tolerances (region, else the (equation, species) block over the family)."""
        rows = []
        for (family, config), imap in sorted(self.imaps.items()):
            sigma = self.sigma[family][config][0]
            ref = self.refs[(family, config)]["yldot"]
            for (eq, sp), block in imap.blocks().items():
                bnz = sigma[block][sigma[block] > 0]
                for region in compare.REGIONS:
                    g = block[imap.region[block] == region]
                    if not g.size:
                        continue
                    z = g[sigma[g] == 0]
                    gnz = sigma[g][sigma[g] > 0]
                    floor = gnz.min() if gnz.size else (bnz.min() if bnz.size else None)
                    stats = (None, None, None)
                    ref0 = int(np.count_nonzero(ref[z] == 0))
                    if z.size and floor is not None and z.size > ref0:
                        x = K * floor / np.abs(ref[z][ref[z] != 0])
                        stats = (float(x.min()), float(np.median(x)), float(x.max()))
                    rows.append((family, config, eq, sp, region, int(g.size), int(z.size), ref0) + stats)
                    if z.size > FLOOR_LIMIT * g.size:
                        self.over.append((family, config))
                        self.owner.append("{} {} {}[{}] {}: sigma = 0 in {} of {} entries ({:.0%}) > 10 %".format(
                            family, config, eq, sp, region, z.size, g.size, z.size / g.size))
        return rows

    def tolerance_check(self, rtol):
        """compare.tolerances per family and configuration; returns {(family, config): Tolerance}."""
        out = {}
        values = {eq: v for eq, (v, _) in rtol.items()}
        for (family, config), imap in sorted(self.imaps.items()):
            sigma = self.sigma[family][config][0]
            try:
                out[(family, config)] = compare.tolerances(self.refs[(family, config)]["yldot"], sigma, values, K,
                                                           imap)
            except compare.ToleranceEscalation as e:
                self.owner.append("{} {}: {}".format(family, config, e))
            except ValueError as e:
                raise Stop(2, "{} {}: {}".format(family, config, e))
        return out

    def recheck(self, tols):
        """AIUE-81: per (equation, species) block, RMS(yldot at the base state) / RMS(tol_i)."""
        rows = []
        for (family, config), t in sorted(tols.items()):
            imap, y = self.imaps[(family, config)], self.refs[(family, config)]["yldot"]
            for (eq, sp), block in imap.blocks().items():
                rms_y = math.sqrt(float(np.mean(y[block] ** 2)))
                rms_t = math.sqrt(float(np.mean(t.tol[block] ** 2)))
                rows.append((family, config, eq, sp, rms_y / rms_t if rms_t > 0 else math.inf))
        return rows


# ---------------------------------------------------------------- analyze: output


def g(x):
    return "-" if x is None else "{:.3g}".format(x)


def report(an, rtol, floors, recheck):
    L = ["# Round-off measurement (tools/measure_roundoff.py, AIUE-87)", ""]
    L += ["## Builds", "", "| label | commit | options | compiler | platform |", "|---|---|---|---|---|"]
    for label in sorted(an.data):
        b = next(iter(an.data[label].values()))["build"]
        L.append("| {} | {} | {} | {} | {} |".format(label, b.get("commit", "?")[:10], b.get("options", "?"),
                                                    b.get("compiler", "?"), b.get("platform", "?")))
    L += ["", "## rtol_eq (k = {:g}, factor {:g}, floor {:g})".format(K, RTOL_FACTOR, RTOL_FLOOR), "",
          "| equation | rtol_eq | set by |", "|---|---|---|"]
    L += ["| {} | {:.3e} | {} |".format(eq, v, src) for eq, (v, src) in rtol.items()]
    L += ["", "## Spreads per pair (max over configurations and families: s / max_abs)", ""]
    eqs = list(rtol)
    L += ["| pair | serial | " + " | ".join(eqs) + " |", "|---|---|" + "---|" * len(eqs)]
    for name, *_, serial in an.pairs:
        cells = []
        for eq in eqs:
            vals = [r[eq] for (f, c, p), r in an.raw.items() if p == name and eq in r]
            cells.append("{:.2e} / {:.2e}".format(max(v["s"] for v in vals), max(v["max_abs"] for v in vals))
                         if vals else "-")
        L.append("| {} | {} | {} |".format(name, "yes" if serial else "no", " | ".join(cells)))
    L += ["", "## Sigma: entries with sigma_i = 0", "", "| family | config | entries | sigma = 0 |", "|---|---|---|---|"]
    for family in sorted(an.sigma):
        for config, (sigma, _) in an.sigma[family].items():
            L.append("| {} | {} | {} | {} ({:.1%}) |".format(family, config, sigma.size,
                                                            int(np.count_nonzero(sigma == 0)),
                                                            np.mean(sigma == 0)))
    L += ["", "## Floor report (PRD 7.4): k*sigma_min,r/|ref_i| over the entries with sigma_i = 0", "",
          "| family | config | block | region | entries | sigma = 0 | ref = 0 | min | median | max |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for f, c, eq, sp, region, n, z, r0, lo, med, hi in floors:
        flag = " **> 10 %**" if z > FLOOR_LIMIT * n else ""
        L.append("| {} | {} | {}[{}] | {} | {} | {}{} | {} | {} | {} | {} |".format(f, c, eq, sp, region, n, z, flag,
                                                                                  r0, g(lo), g(med), g(hi)))
    L += ["", "## AIUE-81 re-check: RMS(yldot at base) / RMS(tol_i) per block", "",
          "| family | config | block | ratio |", "|---|---|---|---|"]
    L += ["| {} | {} | {}[{}] | {:.3g} |".format(*r) for r in recheck]
    L += ["", "## OpenMP (report only until AIUE-59)", "",
          "| family | config | N | Nthreads | ParallelPandf1 | ffun vs serial build: rows, max_rel | "
          "ffun vs pandf: rows, max_rel |", "|---|---|---|---|---|---|---|"]
    for r in an.omp:
        if r["status"] != "ok":
            L.append("| {} | {} | {} | {} | | | |".format(r["family"], r["config"], r["threads"], r["status"]))
            continue
        L.append("| {} | {} | {} | {} | {} | {}, {:.2e} | {}, {:.2e} |".format(
            r["family"], r["config"], r["threads"], r["nthreads"], r["parallel_pandf1"],
            r["vs_serial_build"]["rows"], r["vs_serial_build"]["max_rel"], r["vs_pandf"]["rows"],
            r["vs_pandf"]["max_rel"]))
    for title, items in (("Defects", an.defects), ("Owner", an.owner), ("Findings", an.findings),
                         ("Notes", an.notes)):
        if items:
            L += ["", "## " + title, ""] + ["- " + m.replace("\n", "\n  ") for m in items]
    return "\n".join(L) + "\n"


def tq(s):
    """A TOML basic string (JSON's escapes are a subset of TOML's)."""
    return json.dumps(s, ensure_ascii=False)


def tv(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return "inf" if v == math.inf else repr(v)
    if isinstance(v, dict):
        return "{ " + ", ".join("{} = {}".format(tk(k), tv(x)) for k, x in v.items()) + " }"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(tv(x) for x in v) + "]"
    return tq(str(v))


def tk(k):
    return k if all(c.isalnum() or c in "_-" for c in k) else tq(k)


def sigma_file(path, sigma, pairs):
    """families/<f>/sigma.h5; returns its SHA-256."""
    import h5py

    with h5py.File(path, "w") as f:
        f.attrs["schema"] = SCHEMA
        f.attrs["pairs"] = np.array(pairs, dtype=h5py.string_dtype())
        for config in sorted(sigma):
            grp = f.create_group(config, track_order=False)
            s, src = sigma[config]
            grp.create_dataset("sigma", data=s.astype("<f8"), track_times=False)
            grp.create_dataset("source", data=src.astype("i1"), track_times=False)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(an, rtol, families_dir, toml_path):
    shas = {}
    for family in sorted(an.sigma):
        shas[family] = sigma_file(Path(families_dir) / family / "sigma.h5", an.sigma[family], an.serial)
    L = ["# yldot tolerances (epic AIUE-9, PRD sections 7.4 and 7.7). Generated by", "#   python tests/yldot/tools/"
         "measure_roundoff.py analyze <collections> --write   (AIUE-87); do not edit by hand.",
         "# Owner decisions (2026-10-21, AIUE-87 ticket page): Linux pin Ubuntu 24.04 amd64 (tests/yldot/linux/);",
         "# rtol_eq block-normalised, one value per equation; sigma_i over the serial pairs and both vectors;",
         "# sigma stored per family in families/<f>/sigma.h5. OpenMP and --debug rows are report only.", "",
         "[rule]", "k = {}".format(tv(K)), "rtol_factor = {}".format(tv(RTOL_FACTOR)),
         "rtol_floor = {}".format(tv(RTOL_FLOOR)), "floor_limit = {}".format(tv(FLOOR_LIMIT)),
         "floor = {}".format(tq(FLOOR_RULE)), "sigma = {}".format(tq(SIGMA_RULE)),
         "rtol = {}".format(tq("max(rtol_factor * s, rtol_floor), s = max_i |d_i| / max_i |ref_i| over the "
                               "equation's rows, d over yldot and yldot_J; the max over every family, configuration "
                               "and serial pair")),
         "", "[rtol]"]
    L += ["{} = {}".format(eq, tv(v)) for eq, (v, _) in rtol.items()]
    L += ["", "[rtol_source]"] + ["{} = {}".format(eq, tq(src)) for eq, (_, src) in rtol.items()]
    for label in sorted(an.data):
        b = next(iter(an.data[label].values()))["build"]
        L += ["", "[builds.{}]".format(tk(label))] + ["{} = {}".format(tk(k), tv(b[k])) for k in sorted(b)]
    for name, la, ra, lb, rb, serial in an.pairs:
        L += ["", "[pairs.{}]".format(tk(name)), "first = {}".format(tq("{} run {}".format(la, ra))),
              "second = {}".format(tq("{} run {}".format(lb, rb))), "serial = {}".format(tv(serial)),
              "code = {}".format(an.serial.index(name) if serial else -1)]
    for (family, config, pair), raw in sorted(an.raw.items()):
        L += ["", "[raw.{}.{}.{}]".format(tk(family), config, tk(pair))]
        L += ["{} = {}".format(eq, tv(r)) for eq, r in raw.items()]
    for family in sorted(an.sigma):
        L += ["", "[sigma.{}]".format(tk(family)), 'file = "families/{}/sigma.h5"'.format(family),
              "sha256 = {}".format(tq(shas[family]))]
        for config, (s, _) in sorted(an.sigma[family].items()):
            L.append("{} = {}".format(config, tv({"entries": s.size, "zero": int(np.count_nonzero(s == 0)),
                                                  "max": float(s.max())})))
    L += ["", "[openmp]  # report only until AIUE-59: ffun (OpenMP RHS) against the serial build and against pandf"]
    for r in an.omp:
        key = "{}.{}.n{}".format(r["family"], r["config"], r["threads"])
        L.append("{} = {}".format(tq(key), tv({k: v for k, v in r.items()
                                              if k not in ("family", "config", "threads", "log_tail")})))
    over = {}
    for family, config in an.over:
        over.setdefault(family, {}).setdefault(config, 0)
        over[family][config] += 1
    L += ["", "[floor]  # PRD 7.4 floor report: (equation, species, region) groups with sigma = 0 in more than "
          "floor_limit of their entries", "over_limit = {}".format(tv(dict(sorted(over.items()))))]
    L += ["", "[owner]  # items_raised must equal items_answered: new owner items need new answers",
          "items_raised = {}".format(len(an.owner)), "items_answered = {}".format(OWNER_ITEMS_ANSWERED),
          "answers = [{}]".format(", ".join("\n  " + tq(a) for a in OWNER_ANSWERS) + "\n")]
    L += ["", "[findings]"]
    same = {p: all(r[e]["max_abs"] == 0 for (f, c, q), r in an.raw.items() if q == p for e in r)
            for p, *_ in an.pairs if p.startswith("same_build:")}
    L.append("same_build_zero = {}".format(tv(dict(sorted(same.items())))))
    L.append("items = {}".format(tv([m.split("\n")[0] for m in an.findings + an.defects])))
    Path(toml_path).write_text("\n".join(L) + "\n")
    return shas


def cmd_analyze(args):
    an = Analysis(load(args.dir), args.families)
    an.run()
    rtol = an.rtol()
    floors = an.floors()
    tols = an.tolerance_check(rtol)
    text = report(an, rtol, floors, an.recheck(tols))
    print(text)
    if args.report:
        Path(args.report).write_text(text)
    if args.write:
        write(an, rtol, args.families, args.toml)
    for kind, items in (("OWNER", an.owner), ("DEFECT", an.defects)):
        for m in items[:compare.MAX_LISTED]:
            print("{}: {}".format(kind, m.split("\n")[0]), file=sys.stderr)
        if len(items) > compare.MAX_LISTED:
            print("{}: ... {} in all (the report lists every one)".format(kind, len(items)), file=sys.stderr)
    return 4 if an.defects else 3 if an.owner else 0


def main(argv):
    if argv[1:2] == ["_worker"]:
        return worker(json.loads(argv[2]))
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect", help="evaluate the families in this build and pickle the results")
    p.add_argument("family", nargs="+")
    p.add_argument("--label", required=True, help="build label, e.g. mac-serial")
    p.add_argument("--out", required=True, help="collections directory")
    p.add_argument("--build", required=True, help="JSON file: the build record")
    p.add_argument("--omp", type=int, nargs="*", default=[], help="OpenMP thread counts (OpenMP build only)")
    p = sub.add_parser("analyze", help="pair the collections, report, and with --write write the tolerances")
    p.add_argument("dir")
    p.add_argument("--write", action="store_true")
    p.add_argument("--report", help="also write the markdown report here")
    p.add_argument("--families", default=str(FAMILIES), help="families directory (regions; sigma.h5 is written here)")
    p.add_argument("--toml", default=str(SUITE / "tolerances.toml"))
    args = parser.parse_args(argv[1:])
    try:
        return cmd_collect(args) if args.cmd == "collect" else cmd_analyze(args)
    except Stop as stop:
        print(str(stop), file=sys.stderr)
        return stop.code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
