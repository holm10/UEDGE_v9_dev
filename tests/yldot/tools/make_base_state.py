"""Reference and base states for the yldot families (epic AIUE-9, PRD section 7.1).

Usage (from anywhere; paths in --state/--source are absolute or relative to the family directory):
    python make_base_state.py check <family> [--state FILE]
    python make_base_state.py make <family> --source FILE --seed N [--sigmas 0.02,0.03,0.05]

check  evaluates the family at a state (default reference_state.h5) with issfon=1 and prints nksol's
       convergence norm max|sfscal*yldot| next to the case's ftol and the L2 fnrm. Report only: the
       reference states are the pytests templates used as they are, converged or not (owner, 2026-10-19).
make   restores --source and writes it as reference_state.h5, then perturbs it with a seeded draw
       (log-normal on nis, tes, tis, ngs, tgs; sound-speed-scaled noise on ups; sigma*Te on phis) and
       writes base_state.h5. It takes the smallest sigma at which every (equation, species) block of
       the raw yldot has an RMS at least 10x the reference state's, with the floor guards passing.
       The blocks come only from UEDGE's idx* arrays. Prints a TOML fragment for family.toml.

Every UEDGE evaluation runs in a fresh child process (Forthon state is global), with HOME in an empty
temporary directory, UEDGE_BANNER=0 and one thread. A family directory holding .uedgerc.py is refused,
because import uedge would execute it. Exit codes: 0 ok, 2 usage or evaluation error, 3 a family the
owner has to look at (svrpkg/ifixpsor), 4 the idx* map is not a bijection onto the rows, 5 no sigma
passes the rule, 6 a guard failed.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

FAMILIES = Path(__file__).resolve().parent.parent / "families"
STATE_VARS = ["nis", "ups", "tes", "tis", "phis", "ngs", "tgs"]
OPTIONAL_VARS = ["tipers"]  # hdf5_save adds these only if the build has them (src/uedge/hdf5.py:105-109)
IDX_ARRAYS = ["idxn", "idxu", "idxte", "idxti", "idxg", "idxtg", "idxphi"]
RATIO_MIN = 10.0  # owner, 2026-10-19
NEAR_FLOOR = 1.1  # a cell counts as "at the floor" when value <= NEAR_FLOOR * floor
BACKG_FRACTION = 0.1  # ng, impurity ni floors are this fraction of ngbackg, nzbackg (owner, 2026-10-19)


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def saved_vars(d):
    """The datasets hdf5_save writes for this build: STATE_VARS plus the optional ones present in d."""
    return STATE_VARS + [v for v in OPTIONAL_VARS if v in d]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def data_sha256(path):
    """Hash of the bbb datasets (name, dtype, shape, bytes): hdf5_save stamps ctime/time, so the file hash
    differs on every run while the data does not."""
    import h5py
    h = hashlib.sha256()
    with h5py.File(path, "r") as hf:
        for v in sorted(hf["bbb"]):
            a = np.ascontiguousarray(hf["bbb"][v][()])
            h.update("{}:{}:{}".format(v, a.dtype.str, a.shape).encode())
            h.update(a.tobytes())
    return h.hexdigest()


# ---------------------------------------------------------------- child process side


def worker(job):
    """Runs in the child, cwd = family directory. Writes its results to job['out']."""
    family = Path.cwd()
    if (family / ".uedgerc.py").exists():
        print("refused: {} holds .uedgerc.py".format(family), file=sys.stderr)
        return 2
    code = compile((family / "input.py").read_text(), "input.py", "exec")
    exec(code, {"__name__": "__family_input__"})

    from uedge import bbb, com
    from uedge.hdf5 import hdf5_restore, hdf5_save

    svrpkg = bbb.svrpkg.tobytes().decode().strip() if hasattr(bbb.svrpkg, "tobytes") else str(bbb.svrpkg).strip()
    if svrpkg.strip("b'\" ") != "nksol" or int(bbb.ifixpsor) != 0:
        print("svrpkg={!r} ifixpsor={}: ask the owner (PRD section 6)".format(svrpkg, int(bbb.ifixpsor)),
              file=sys.stderr)
        return 3
    ftol_case = float(bbb.ftol)

    bbb.allocate()
    hdf5_restore(job["state"])
    bbb.restart = 1
    out = {"ftol_case": ftol_case}

    if job["mode"] == "save":
        # The restored arrays, written in the hdf5_restore format (fresh list: hdf5_save appends to it)
        hdf5_save(job["save_to"], varlist=["bbb." + v for v in STATE_VARS])
        for v in STATE_VARS + [v for v in OPTIONAL_VARS if v in bbb.varlist()]:
            out[v] = np.array(getattr(bbb, v)).copy()
        out["temin"] = float(bbb.temin)
        out["tgmin"] = float(bbb.tgmin)
        out["ngbackg"] = np.array(bbb.ngbackg).copy()
        out["nzbackg"] = np.array(bbb.nzbackg).copy()
        out["ev"] = float(bbb.ev)
        out["mi"] = np.array(bbb.mi).copy()
        for n in ("nhsp", "nisp", "nusp", "ngsp"):
            out[n] = int(getattr(com, n))
        out["ineudif"] = int(bbb.ineudif)
        np.savez(job["out"], **out)
        return 0

    bbb.issfon = job["issfon"]
    bbb.ftol = 1e50
    bbb.dtreal = 1e20
    bbb.exmain()
    neq = int(bbb.neq)
    if bbb.yl.size < neq + 2:
        print("yl holds {} entries, need neq+2 = {}".format(bbb.yl.size, neq + 2), file=sys.stderr)
        return 2
    bbb.yl[neq] = -1.0  # nksol-RHS flag
    bbb.yl[neq + 1] = 0.0  # nufak
    bbb.pandf(-1, -1, neq, 0.0, bbb.yl, bbb.yldot)

    out.update(neq=neq, yldot=bbb.yldot[:neq].copy(), sfscal=bbb.sfscal[:neq].copy(),
               isflxlde=int(bbb.isflxlde), conxe=np.array(bbb.conxe).copy(),
               hcxe=np.array(bbb.hcxe).copy(), sx=np.array(com.sx).copy(), gxf=np.array(com.gxf).copy(),
               uedge_ver=bbb.uedge_ver.tobytes().decode(errors="replace").strip()
               if hasattr(bbb.uedge_ver, "tobytes") else str(bbb.uedge_ver).strip())
    for name in IDX_ARRAYS:
        out[name] = np.array(getattr(bbb, name)).copy()
    np.savez(job["out"], **out)
    return 0


# ---------------------------------------------------------------- parent side


def run_child(family_dir, job, log):
    """One fresh process per evaluation; returns the loaded results."""
    with tempfile.TemporaryDirectory(prefix="yldot-home-") as home, \
            tempfile.TemporaryDirectory(prefix="yldot-out-") as outdir:
        job = dict(job, out=os.path.join(outdir, "out.npz"))
        env = dict(os.environ, HOME=home, UEDGE_BANNER="0", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_worker", json.dumps(job)],
                              cwd=family_dir, env=env, capture_output=True, text=True)
        log.write(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-20:])
            raise Stop(3 if proc.returncode == 3 else 2,
                       "child exit {} in {}:\n{}".format(proc.returncode, family_dir.name, tail))
        with np.load(job["out"]) as data:
            return {k: data[k] for k in data.files}


def resolve(family_dir, path):
    p = Path(path)
    return p if p.is_absolute() else (family_dir / p)


def norms(res):
    scaled = res["sfscal"] * res["yldot"]
    return float(np.max(np.abs(scaled))), float(np.sqrt(np.sum(scaled ** 2)))


def blocks(res):
    """(label, rows) per equation and species, from the idx* arrays only; checks the bijection."""
    neq = int(res["neq"])
    found = []
    for name in IDX_ARRAYS:
        idx = res[name]
        slices = [(name, idx)] if idx.ndim == 2 else [("{}[{}]".format(name, s), idx[:, :, s])
                                                      for s in range(idx.shape[2])]
        for label, a in slices:
            rows = a[a > 0].astype(np.int64) - 1
            if rows.size:
                found.append((label, rows))
    claimed = np.concatenate([r for _, r in found]) if found else np.array([], dtype=np.int64)
    counts = np.bincount(claimed, minlength=neq) if claimed.size else np.zeros(neq, dtype=np.int64)
    if claimed.size and claimed.max() >= neq:
        raise Stop(4, "idx* entries point past neq={} (max row {}): ask the owner".format(neq, claimed.max() + 1))
    if np.any(counts[:neq] != 1):
        missing = np.flatnonzero(counts[:neq] == 0)[:10] + 1
        twice = np.flatnonzero(counts[:neq] > 1)[:10] + 1
        raise Stop(4, "idx* map is not a bijection onto 1..{}: {} rows unclaimed (first {}), {} claimed "
                      "more than once (first {}): ask the owner".format(
                          neq, int(np.sum(counts[:neq] == 0)), missing.tolist(),
                          int(np.sum(counts[:neq] > 1)), twice.tolist()))
    return found


def floors(ref):
    """(array name, floor array broadcast to the array's shape), owner decision 2026-10-19."""
    out = []
    te_floor = ref["temin"] * ref["ev"]
    out.append(("tes", np.full(ref["tes"].shape, te_floor)))
    out.append(("tis", np.full(ref["tis"].shape, te_floor)))
    ngsp = int(ref["ngsp"])
    out.append(("tgs", np.full(ref["tgs"].shape, ref["tgmin"] * ref["ev"])))
    # ngbackg, nzbackg set soft background sources (bbb/bbb.v:68-81), not floors: converged states sit below them
    out.append(("ngs", BACKG_FRACTION * np.broadcast_to(ref["ngbackg"][:ngsp], ref["ngs"].shape)))
    nhsp, nisp = int(ref["nhsp"]), int(ref["nisp"])
    if nisp > nhsp:  # impurity species: ifld >= nhsp (0-based)
        imp = np.zeros(ref["nis"].shape)
        imp[:, :, nhsp:] = BACKG_FRACTION * np.broadcast_to(ref["nzbackg"][nhsp:nisp],
                                                            ref["nis"][:, :, nhsp:].shape)
        out.append(("nis_imp", imp))
    return out


def perturb(ref, sigma, seed):
    rng = np.random.default_rng(seed)
    new = {v: ref[v].copy() for v in saved_vars(ref)}
    # Fixed draw order; the same seed for every sigma, so only the amplitude changes
    for v in ("nis", "tes", "tis", "ngs", "tgs"):
        new[v] = ref[v] * np.exp(sigma * rng.standard_normal(ref[v].shape))
    nusp = int(ref["nusp"])
    noise = rng.standard_normal(ref["ups"].shape)
    for ifld in range(nusp):
        cs = np.sqrt((ref["tes"] + ref["tis"]) / ref["mi"][ifld])
        new["ups"][:, :, ifld] = ref["ups"][:, :, ifld] + sigma * cs * noise[:, :, ifld]
    new["phis"] = ref["phis"] + sigma * (ref["tes"] / ref["ev"]) * rng.standard_normal(ref["phis"].shape)
    return new


def guards(ref, new):
    """Hard failures, never a clamp or a re-draw. Returns the guard summary for family.toml."""
    for v in saved_vars(new):
        if not np.all(np.isfinite(new[v])):
            bad = np.argwhere(~np.isfinite(new[v]))[0].tolist()
            raise Stop(6, "{} is not finite at {}".format(v, bad))
    for v in ("nis", "ngs"):
        if np.any(new[v] <= 0):
            raise Stop(6, "{} <= 0 at {} (log(ng) guard for ineudif=3; densities)".format(
                v, np.argwhere(new[v] <= 0)[0].tolist()))
    summary = {}
    for name, floor in floors(ref):
        v = "nis" if name == "nis_imp" else name
        sel = floor > 0
        below_new = sel & (new[v] < floor)
        below_ref = sel & (ref[v] < floor)
        near_new = int(np.sum(sel & (new[v] <= NEAR_FLOOR * floor)))
        near_ref = int(np.sum(sel & (ref[v] <= NEAR_FLOOR * floor)))
        if np.any(below_new & ~below_ref):
            cell = np.argwhere(below_new & ~below_ref)[0].tolist()
            raise Stop(6, "{} drops below its floor at {}: {:.4e} < {:.4e}".format(
                name, cell, new[v][tuple(cell)], floor[tuple(cell)]))
        if near_new > near_ref:
            raise Stop(6, "{}: {} cells within {}x the floor at base, {} at the reference".format(
                name, near_new, NEAR_FLOOR, near_ref))
        summary[name] = {"near_floor_ref": near_ref, "near_floor_base": near_new,
                         "below_floor_ref": int(np.sum(below_ref))}
    return summary


def write_state(template, target, new):
    """base_state.h5: a copy of reference_state.h5 with the perturbed datasets."""
    import h5py
    shutil.copyfile(template, target)
    with h5py.File(target, "r+") as hf:
        for v in saved_vars(new):
            ds = hf["bbb"][v]
            if ds.shape != new[v].shape:
                raise Stop(2, "{}: dataset shape {} != array shape {}".format(v, ds.shape, new[v].shape))
            ds[...] = new[v]


def read_back(path, expect):
    import h5py
    with h5py.File(path, "r") as hf:
        for v in saved_vars(expect):
            if v not in hf["bbb"]:
                raise Stop(2, "{} lacks bbb/{}".format(path, v))
            if not np.array_equal(hf["bbb"][v][()], expect[v]):
                raise Stop(2, "{}: bbb/{} differs from the array written".format(path, v))


def limiter_count(res):
    """Faces where the electron parallel heat-flux limiter dominates (qr >= 1); report only."""
    if int(res["isflxlde"]) != 0:
        return None
    csh = res["sx"] * res["hcxe"] * res["gxf"]
    ok = (csh > 0) & (res["conxe"] > 0)
    qr = np.sqrt(csh[ok] / res["conxe"][ok]) - 1.0
    return int(np.sum(qr >= 1.0))


def cmd_check(args, log):
    family_dir = FAMILIES / args.family
    state = resolve(family_dir, args.state)
    res = run_child(family_dir, {"mode": "eval", "state": str(state), "issfon": 1}, log)
    fmax, fnrm = norms(res)
    ftol = float(res["ftol_case"])
    if not (np.isfinite(fmax) and np.isfinite(fnrm)):
        raise Stop(2, "{}: non-finite yldot at {}".format(args.family, state.name))
    print("{:9s} state={} neq={} fmax={:.4e} ftol={:.1e} fnrm={:.4e} converged={}".format(
        args.family, state.name, int(res["neq"]), fmax, ftol, fnrm, str(fmax <= ftol).lower()))
    return 0


def cmd_make(args, log):
    family_dir = FAMILIES / args.family
    source = resolve(family_dir, args.source)
    reference = family_dir / "reference_state.h5"
    base = family_dir / "base_state.h5"
    ref = run_child(family_dir, {"mode": "save", "state": str(source), "save_to": str(reference)}, log)
    read_back(reference, ref)

    ref_eval = run_child(family_dir, {"mode": "eval", "state": str(reference), "issfon": 0}, log)
    found = blocks(ref_eval)
    sigmas = [float(s) for s in args.sigmas.split(",")]
    chosen = None
    for sigma in sigmas:
        new = perturb(ref, sigma, args.seed)
        try:
            guard_summary = guards(ref, new)
        except Stop as stop:
            print("sigma={}: guard failed: {}".format(sigma, stop))
            chosen = ("guard", sigma, stop)
            break
        write_state(reference, base, new)
        read_back(base, new)
        base_eval = run_child(family_dir, {"mode": "eval", "state": str(base), "issfon": 0}, log)
        if int(base_eval["neq"]) != int(ref_eval["neq"]):
            raise Stop(2, "neq differs between reference and base")
        ratios = []
        for label, rows in found:
            r_ref = float(np.sqrt(np.mean(ref_eval["yldot"][rows] ** 2)))
            r_base = float(np.sqrt(np.mean(base_eval["yldot"][rows] ** 2)))
            ratio = np.inf if r_ref == 0 and r_base > 0 else (0.0 if r_base == 0 else r_base / r_ref)
            ratios.append((label, rows.size, r_ref, r_base, ratio))
        worst = min(ratios, key=lambda t: t[4])
        print("sigma={}: min block ratio {:.3g} ({})".format(sigma, worst[4], worst[0]))
        if all(t[4] >= RATIO_MIN for t in ratios):
            chosen = ("ok", sigma, ratios, guard_summary, base_eval)
            break
    if chosen is None or chosen[0] != "ok":
        for label, n, r_ref, r_base, ratio in ratios if chosen is None else []:
            print("  {:12s} rows={:5d} rms_ref={:.3e} rms_base={:.3e} ratio={:.3g}".format(
                label, n, r_ref, r_base, ratio))
        if base.exists():
            base.unlink()
        if chosen is not None:
            raise chosen[2]
        raise Stop(5, "{}: no sigma in {} gives every block ratio >= {}: ask the owner".format(
            args.family, sigmas, RATIO_MIN))

    _, sigma, ratios, guard_summary, base_eval = chosen
    for label, n, r_ref, r_base, ratio in ratios:
        print("  {:12s} rows={:5d} rms_ref={:.3e} rms_base={:.3e} ratio={:.3g}".format(
            label, n, r_ref, r_base, ratio))
    print("\n# --- family.toml fragment ---")
    print("[perturbation]")
    print("sigma = {}".format(sigma))
    print("seed = {}".format(args.seed))
    print('rule = "every (equation, species) block: RMS(raw yldot at base) / RMS(at reference) >= {:g}"'.format(
        RATIO_MIN))
    print("min_block_ratio = {:.4g}".format(min(t[4] for t in ratios)))
    print('floors = "te, ti >= temin*ev; tg >= tgmin*ev; ng >= {0:g}*ngbackg(igsp); impurity ni >= {0:g}*nzbackg(ifld)"'
          .format(BACKG_FRACTION))
    print("near_floor_factor = {}".format(NEAR_FLOOR))
    for name, s in guard_summary.items():
        print("near_floor_{} = {{ reference = {}, base = {} }}".format(name, s["near_floor_ref"],
                                                                     s["near_floor_base"]))
    print('base_state_sha256 = "{}"'.format(sha256(base)))
    print('reference_state_sha256 = "{}"'.format(sha256(reference)))
    print('base_state_data_sha256 = "{}"'.format(data_sha256(base)))
    print('reference_state_data_sha256 = "{}"'.format(data_sha256(reference)))
    print('source_state_sha256 = "{}"'.format(sha256(source)))
    print("\n[limiter_report]")
    lim_ref, lim_base = limiter_count(ref_eval), limiter_count(base_eval)
    if lim_ref is None:
        print('note = "isflxlde != 0: not computed"')
    else:
        print("flalfe_qr_ge_1_reference = {}".format(lim_ref))
        print("flalfe_qr_ge_1_base = {}".format(lim_base))
    return 0


def main(argv):
    if len(argv) > 1 and argv[1] == "_worker":
        return worker(json.loads(argv[2]))
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="report nksol's convergence norm at a state")
    p.add_argument("family")
    p.add_argument("--state", default="reference_state.h5")
    p = sub.add_parser("make", help="write reference_state.h5 and base_state.h5")
    p.add_argument("family")
    p.add_argument("--source", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--sigmas", default="0.02,0.03,0.05")
    p.add_argument("--log", help="child output log (default: discarded)")
    p_check = sub.choices["check"]
    p_check.add_argument("--log", help="child output log (default: discarded)")
    args = parser.parse_args(argv[1:])
    if not (FAMILIES / args.family / "input.py").exists():
        print("no family {} under {}".format(args.family, FAMILIES), file=sys.stderr)
        return 2
    log = open(args.log, "a") if args.log else open(os.devnull, "w")
    try:
        return (cmd_check if args.cmd == "check" else cmd_make)(args, log)
    except Stop as stop:
        print(str(stop), file=sys.stderr)
        return stop.code
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
