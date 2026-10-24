"""Run one configuration of the reproducer and save everything the comparison needs.

Executed by runner.py as   python -I worker.py <spec.json>   in a prepared run directory
(a copy of tests/deterministic_omp/case). Never import this module in a process that
should keep running: it imports uedge, whose state is global.

Writes, in the run directory:
  record.npz   arrays (Jacobians, yldot, sfscal, suscal, index maps)
  record.json  scalars, provenance and the capture description
Exit status: 0 on success, 2 on any error (record.json then holds "error").
"""
import json
import os
import platform
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # tests/deterministic_omp, for "harness"
sys.path.insert(0, os.getcwd())  # the run directory, for input_mod4

from harness.config import ARMS, DIAGNOSTIC_SWITCHES, RunSpec, apply_preset, force_newton  # noqa: E402

EQ_CODES = ["ni", "up", "te", "ti", "ng", "tg", "phi"]


def _text(value):
    """A Forthon character variable (bytes, numpy bytes array, or str) as a stripped str."""
    import numpy as np

    if isinstance(value, np.ndarray):
        value = value.ravel()[0] if value.size else b""
    if isinstance(value, (bytes, bytearray, np.bytes_)):
        value = bytes(value).decode(errors="replace")
    return str(value).strip()


def git_state(path):
    """(HEAD, dirty) of the git checkout holding path, or ("unknown", None)."""
    try:
        head = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or "unknown"
        status = subprocess.run(["git", "-C", path, "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True, timeout=30).stdout
        return head, bool(status.strip())
    except Exception:
        return "unknown", None


def build_identity():
    """Which build this process runs: the installed uedge's source tree (pip's direct_url.json),
    that tree's git HEAD and dirty state, a SHA-256 over the compiled extension modules, whether
    they link an OpenMP runtime, and the compiler they were built with (from the .comment
    strings, found on Linux/ELF builds; macOS Mach-O builds keep none, so the list is empty there).
    The compile flags are not recorded in the binaries, so they can't be recovered from them; a
    build from AIUE-181 on records setup.py's flags and Forthon's own optimisation flags (not its
    precision and form flags) in uedge/_build_info.json, which build_probe.py reads. The source
    tree's HEAD and dirty state are read at run time; together with extensions_sha256 they
    identify the build, but a tree changed after the build would show its current state."""
    import glob
    import hashlib
    import importlib.metadata
    import uedge

    ident = {"uedge_file": uedge.__file__}
    try:
        dist = importlib.metadata.distribution("uedge")
        direct = dist.read_text("direct_url.json")
        url = json.loads(direct).get("url", "") if direct else ""
        src = url[len("file://"):] if url.startswith("file://") else url
        ident["source_dir"] = src or None
        if src:
            ident["source_head"], ident["source_dirty"] = git_state(src)
    except Exception as err:  # not a pip install from a directory
        ident["source_dir"] = None
        ident["source_error"] = repr(err)
    sos = sorted(glob.glob(os.path.join(os.path.dirname(uedge.__file__), "*.so")))
    digest = hashlib.sha256()
    openmp = False
    compilers = set()
    for so in sos:
        data = open(so, "rb").read()
        digest.update(os.path.basename(so).encode() + b"\0" + hashlib.sha256(data).digest())
        openmp = openmp or b"GOMP_" in data or b"__kmpc_" in data
        for marker in (b"GCC: (",):
            i = data.find(marker)
            if i >= 0:
                compilers.add(data[i:i + 80].split(b"\0")[0].decode(errors="replace"))
    ident["extensions_sha256"] = digest.hexdigest()
    ident["n_extensions"] = len(sos)
    ident["openmp_build"] = openmp
    ident["compiler"] = sorted(compilers)
    return ident


def equation_map(bbb, com, neq):
    """For every equation index iv (0-based), its equation code (index into EQ_CODES; -1 not found,
    -2 claimed by two tables) and species (-1 if none), from the idx* tables (bbb/bbb.v Indexes)."""
    import numpy as np

    eq = np.full(neq, -1, dtype=np.int64)
    species = np.full(neq, -1, dtype=np.int64)
    tables = [("ni", bbb.idxn, True), ("up", bbb.idxu, True), ("te", bbb.idxte, False),
              ("ti", bbb.idxti, False), ("ng", bbb.idxg, True), ("tg", bbb.idxtg, True),
              ("phi", bbb.idxphi, False)]
    switches = {"ni": bbb.isnion, "up": bbb.isupon, "te": [bbb.isteon], "ti": [bbb.istion],
                "ng": bbb.isngon, "tg": bbb.istgon, "phi": [bbb.isphion]}
    for name, idx, per_species in tables:
        arr = np.asarray(idx)
        if arr.size == 0:
            continue
        if not per_species:
            arr = arr[..., None]
        for isp in range(arr.shape[2]):
            on = np.atleast_1d(switches[name])
            if isp >= on.size or on[isp] == 0:
                continue
            ivs = arr[:, :, isp].ravel()
            ivs = ivs[(ivs >= 1) & (ivs <= neq)] - 1
            clash = eq[ivs] != -1
            eq[ivs] = np.where(clash, -2, EQ_CODES.index(name))  # -2: assigned twice, unreliable
            species[ivs] = isp if per_species else -1
    return eq, species


SOURCES = {1: "jac_calc", 2: "jac_calc_parallel"}
CALLERS = {0: "other", 1: "sfsetnk", 2: "psetnk"}


def has_capture_hook(bbb):
    """True if the build has the AIUE-47 raw-Jacobian capture (bbb group Jacobian_capture)."""
    return "jaccapture" in bbb.varlist()


def start_capture(bbb, slots):
    bbb.jaccapture = slots
    bbb.jaccapskip = 0
    bbb.jaccapcount = 0
    bbb.jaccapn = 0


def collect_capture(bbb, arrays):
    """Copy the captured raw Jacobians into arrays (capjac_k, capjacj_k, capjaci_k, 0-based k)
    and describe them. Raw = before sfsetnk/psetnk scale, normalise or reorder."""
    import numpy as np

    n = int(bbb.jaccapn)
    desc = {"hook": True, "count": n, "seen": int(bbb.jaccapcount), "slots": int(bbb.jaccapture),
            "source": [], "caller": [], "seq": []}
    for k in range(n):
        neq, nnz = int(bbb.jaccapneq[k]), int(bbb.jaccapnnz[k])
        arrays["capjac_{}".format(k)] = np.array(bbb.jaccapv[:nnz, k])
        arrays["capjacj_{}".format(k)] = np.array(bbb.jaccapj[:nnz, k])
        arrays["capjaci_{}".format(k)] = np.array(bbb.jaccapi[: neq + 1, k])
        desc["source"].append(SOURCES.get(int(bbb.jaccapsrc[k]), "unknown"))
        desc["caller"].append(CALLERS.get(int(bbb.jaccapfrom[k]), "unknown"))
        desc["seq"].append(int(bbb.jaccapseq[k]))
    if int(bbb.jaccapcount) > n:
        desc["truncated"] = True  # more Jacobians than slots: raise RunSpec.capture
    return desc


def run(spec):
    import numpy as np
    from input_mod4 import bbb, com, ppp  # runs the deck in the current directory

    apply_preset(bbb, spec.preset)
    for name in DIAGNOSTIC_SWITCHES:  # never on in a measured run
        setattr(ppp, name, 0)
    for name, value in ARMS[spec.arm].items():
        setattr(ppp, name, value)
    ppp.Nthreads = spec.threads
    for name, value in spec.ppp.items():
        setattr(ppp, name, value)
    if spec.itermx is None:
        bbb.ftol = 1e20
    else:
        force_newton(bbb, spec.itermx)
    hook = has_capture_hook(bbb) and spec.capture > 0
    if hook:
        start_capture(bbb, spec.capture)  # after the deck, so its populate exmain isn't captured

    bbb.exmain()

    neq = int(bbb.neq)
    nnz = int(bbb.jaci[neq]) - 1
    arrays = {
        "yldot": np.array(bbb.yldot[:neq]),
        "sfscal": np.array(bbb.sfscal[:neq]),
        "suscal": np.array(bbb.suscal[:neq]),
        "jac_post": np.array(bbb.jac[:nnz]),
        "jacj_post": np.array(bbb.jacj[:nnz]),
        "jaci_post": np.array(bbb.jaci[: neq + 1]),
        "igyl": np.array(bbb.igyl[:neq, :]),
    }
    arrays["eq"], arrays["species"] = equation_map(bbb, com, neq)
    capture = collect_capture(bbb, arrays) if hook else {"hook": False, "count": 0}
    # Which Jacobian bbb.jac holds after exmain: the sfsetnk one (scaled by 1/suscal only), or,
    # once nksol has called psetnk, the last psetnk one (scaled, row-normalised and, with
    # premeth="ilut" and ireorder=1, permuted in place by jac_reorder).
    if capture["count"]:
        last = capture["caller"][-1]
    else:
        last = "psetnk" if int(bbb.ijactot) > 1 else "sfsetnk"
    permuted = last == "psetnk" and int(bbb.ireorder) == 1
    meta = {
        "spec": json.loads(spec.to_json()),
        "neq": neq,
        "nnz_post": nnz,
        "numvar": int(bbb.numvar),
        "ijactot": int(bbb.ijactot),
        "capture": capture,
        "post_exmain_from": last,
        "post_exmain_permuted": permuted,
        # why nksol stopped (1 ftol, 2 stptol, 3 line search, 4 itermx, ...) and the tolerances it ran with;
        # informational, not compared
        "iterm": int(bbb.iterm),
        "ftol": float(bbb.ftol),
        "stptol": float(bbb.stptol),
    }

    if spec.rhs_probe:
        # One more RHS evaluation through the solver's path (ffun -> PandfRHS_interface), before
        # get_fnrm (which runs the serial pandf and overwrites bbb.yldot). With OMPParallelPandf1=1
        # and ijactot>0 this is the parallel RHS (OMPPandf1Rhs). pandf reads yl(neq+1), so pass
        # the whole neq+2 vector.
        yl = np.array(bbb.yl[: neq + 2])
        out = np.zeros(neq + 2)
        bbb.ffun(neq, 0.0, yl, out)
        arrays["yldot_probe"] = out[:neq].copy()
        meta["rhs_probe_parallel"] = bool(int(bbb.ParallelPandf1) > 0 and int(bbb.ijactot) > 0)
    # get_fnrm: the norm of the serial pandf residual at the final state times sfscal, i.e. a
    # fingerprint of the final state and sfscal, not nksol's own (possibly parallel-RHS) value
    meta["fnrm_final_hex"] = float(bbb.get_fnrm(bbb.dtreal)).hex()

    harness_head, harness_dirty = git_state(HERE)
    meta["provenance"] = {
        "harness_commit": harness_head,
        "harness_dirty": harness_dirty,
        "build": build_identity(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "uedge_ver": bytes(bbb.uedge_ver[0]).decode(errors="replace").strip()
        if hasattr(bbb.uedge_ver, "__getitem__") else str(bbb.uedge_ver),
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "OMP_STACKSIZE": os.environ.get("OMP_STACKSIZE"),
        "Nthreads": int(ppp.Nthreads),
        "OMPParallelJac": int(ppp.OMPParallelJac),
        "OMPParallelPandf1": int(ppp.OMPParallelPandf1),
        "ParallelJac": int(bbb.ParallelJac),
        "ParallelPandf1": int(bbb.ParallelPandf1),
        "OMPJacNchunks": int(ppp.OMPJacNchunks),
        "OMPAutoBalance": int(ppp.OMPAutoBalance),
        "OMPLoopJacNchunk": int(ppp.OMPLoopJacNchunk),
        "OMPlenpfac": int(ppp.OMPlenpfac),
        "ireorder": int(bbb.ireorder),
        "premeth": _text(bbb.premeth),
    }
    for name in DIAGNOSTIC_SWITCHES:
        meta["provenance"][name] = int(getattr(ppp, name))
    meta["provenance"]["openmp_build"] = meta["provenance"]["build"]["openmp_build"]
    np.savez("record.npz", **arrays)
    return meta


def main():
    spec = RunSpec.from_json(open(sys.argv[1]).read())
    try:
        meta = run(spec)
        status = 0
    except BaseException:  # noqa: B902  (SystemExit from the deck counts as a harness error too)
        meta = {"error": traceback.format_exc()}
        status = 2
    # stdout is shared with the Fortran runtime, which can overwrite what Python prints,
    # so results only go to files
    with open("record.json", "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    # a normal exit, so that the Fortran runtime flushes its buffered output to the log
    sys.exit(status)


if __name__ == "__main__":
    main()
