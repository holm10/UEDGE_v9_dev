"""Bitwise fingerprints of one UEDGE exmain(), and of the raw-Jacobian capture hook.

Written for AIUE-47 (bbb.jaccapture, the Jacobian_capture group); generic enough for
later tickets of epic AIUE-8. Three subcommands:

  child    Runs in the current directory (a copy of a case). Executes the deck, applies
           --set/--tebox, optionally turns the capture hook on, runs exmain() once and
           prints one line "FINGERPRINT {json}" with SHA-256 digests of the raw bytes of
           yldot, the post-exmain jac/jacj/jaci, sfscal, suscal, get_fnrm() as float.hex,
           and (capture on) per captured slot its metadata and digests plus the check
           that the sfsetnk capture times 1/suscal is bitwise the post-exmain bbb.jac.
           With --capture K>0 the run FAILS unless at least one Jacobian was stored,
           every slot has a caller tag (sfsetnk/psetnk), the allocated slots are
           bounded by the lazy-growth rule, and (ftol=1e20 mode) the identity was
           actually evaluated.
  run      Copies --case to a fresh temporary directory and runs "child" there with the
           given python in a fresh "python -I" process with an empty HOME. Prints the
           fingerprint, the printed nksol fnrm sequence and the capture checks.
  compare  Does "run" with --base and with --new and compares every field bitwise
           (string equality of SHA-256 / float.hex / the printed g26.16 fnrm digits).

Usage examples (exit code 0 = all equal / checks pass, 1 = mismatch, 2 = harness error):

  python capture_check.py compare --case CASE --deck input_mod4.py \
      --base venvs/base-serial/bin/python --new venvs/AIUE-47-serial/bin/python \
      --label repro-ftol1e20
  python capture_check.py compare ... -- --newton 3        # fnrm sequence of 3 iterations
  python capture_check.py compare ... --new-extra "--capture 4"   # hook on in --new only
  python capture_check.py run --case CASE --deck input.py --python PY -- \
      --set bbb.issfon=1 --capture 4 --set ppp.OMPParallelJac=1 --set ppp.OMPlenpfac=20

Arguments after "--" are passed to the child:
  --deck FILE        deck executed with runpy in the case directory (default input.py;
                     normally given before "--" so that it is recorded in the label)
  --set PKG.VAR=VAL  assignment after the deck (VAL is a Python literal); repeatable
  --tebox            the 25-equation "Te box" reduction of the AIUE-46 reproducer
  --newton N         itermx=N with ftol=1e-30 (N Newton iterations) instead of ftol=1e20
  --capture K        bbb.jaccapture=K (keep up to K raw Jacobians); --skip S sets jaccapskip
  --iprint N         com.iprint (default 1, so nksol prints the fnrm sequence)

--add-file PATH copies an extra file into the run directory (e.g. rates/aph/crumpet_nrates.dat
and crumpet_Erates.dat, which the installed package does not ship; the D_mols decks need both).

Environment of the child: HOME is an empty temporary directory; OMP_NUM_THREADS
(--threads, default 1), OMP_STACKSIZE (default 512M) and any --env K=V are set.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

FNRM_RE = re.compile(r"fnrm=\s*(\S+)")


def digest(array):
    return hashlib.sha256(array.tobytes()).hexdigest()


# --------------------------------------------------------------------------- child
def child(argv):
    p = argparse.ArgumentParser(prog="capture_check.py child")
    p.add_argument("--deck", default="input.py")
    p.add_argument("--set", action="append", default=[], dest="sets")
    p.add_argument("--tebox", action="store_true")
    p.add_argument("--newton", type=int, default=0)
    p.add_argument("--capture", type=int, default=0)
    p.add_argument("--skip", type=int, default=0)
    p.add_argument("--iprint", type=int, default=1)
    a = p.parse_args(argv)

    import runpy

    sys.path.insert(0, os.getcwd())
    runpy.run_path(a.deck, run_name="__deck__")
    import numpy as np
    from uedge import bbb, com, ppp

    pkgs = {"bbb": bbb, "com": com, "ppp": ppp}
    if a.tebox:
        bbb.isnion = 0
        bbb.isngon = 0
        bbb.isupon = 0
        bbb.istion = 0
        bbb.isphion = 0
        bbb.isphiofft = 1
        bbb.isteoffxy = 1
        bbb.isteoffxy[3:8, 18:23] = 0
    for s in a.sets:
        name, val = s.split("=", 1)
        pkg, var = name.split(".")
        setattr(pkgs[pkg], var, ast.literal_eval(val))
    com.iprint = a.iprint
    if a.newton > 0:
        bbb.itermx = a.newton
        bbb.ftol = 1e-30
    else:
        bbb.ftol = 1e20
    has_capture = hasattr(bbb, "jaccapture")
    if a.capture > 0:
        if not has_capture:
            raise Exception("this UEDGE build has no bbb.jaccapture (AIUE-47 hook)")
        bbb.jaccapture = a.capture
        bbb.jaccapskip = a.skip
        bbb.jaccapcount = 0
        bbb.jaccapn = 0
    bbb.exmain()

    neq = int(bbb.neq)
    nnz = int(bbb.jaci[neq]) - 1
    out = {
        "neq": neq,
        "nnz": nnz,
        "yldot": digest(bbb.yldot[:neq]),
        "jac": digest(bbb.jac[:nnz]),
        "jacj": digest(bbb.jacj[:nnz]),
        "jaci": digest(bbb.jaci[: neq + 1]),
        "sfscal": digest(bbb.sfscal[:neq]),
        "suscal": digest(bbb.suscal[:neq]),
        "ijactot": int(bbb.ijactot),
    }
    if has_capture:
        out["jaccapture"] = int(bbb.jaccapture)
        out["jaccapcount"] = int(bbb.jaccapcount)
        out["jaccapn"] = int(bbb.jaccapn)
    if has_capture and a.capture > 0:
        su = np.array(bbb.suscal[:neq])
        slots = []
        for k in range(int(bbb.jaccapn)):
            kn = int(bbb.jaccapneq[k])
            knz = int(bbb.jaccapnnz[k])
            v = np.array(bbb.jaccapv[:knz, k])
            j = np.array(bbb.jaccapj[:knz, k])
            i = np.array(bbb.jaccapi[: kn + 1, k])
            slot = {
                "slot": k + 1,
                "seq": int(bbb.jaccapseq[k]),
                "src": {1: "jac_calc", 2: "jac_calc_parallel"}.get(int(bbb.jaccapsrc[k]), int(bbb.jaccapsrc[k])),
                "from": {1: "sfsetnk", 2: "psetnk"}.get(int(bbb.jaccapfrom[k]), int(bbb.jaccapfrom[k])),
                "neq": kn,
                "nnz": knz,
                "ia_last_ok": bool(i[kn] == knz + 1),
                "v": digest(v),
                "j": digest(j),
                "i": digest(i),
            }
            # sfsetnk applies only amudia(1/su) to jac; with ftol=1e20 (no psetnk) the
            # post-exmain bbb.jac must be this capture times 1/suscal, bit for bit.
            if slot["from"] == "sfsetnk" and a.newton == 0 and k == int(bbb.jaccapn) - 1:
                pattern = (kn == neq and knz == nnz
                           and np.array_equal(j, np.array(bbb.jacj[:nnz]))
                           and np.array_equal(i, np.array(bbb.jaci[: neq + 1])))
                slot["check_pattern_equal_bbb_jacj_jaci"] = bool(pattern)
                if pattern:
                    scaled = v * (1.0 / su)[j - 1]
                    jac = np.array(bbb.jac[:nnz])
                    slot["check_raw_times_inv_suscal_bitwise_eq_bbb_jac"] = digest(scaled) == digest(jac)
                    back = jac * su[j - 1]  # "multiplied back" (rounding-level only)
                    den = np.maximum(np.abs(v), np.finfo(float).tiny)
                    slot["check_bbb_jac_times_suscal_max_reldiff"] = float(np.max(np.abs(back - v) / den))
            slots.append(slot)
        out["slots"] = slots
        # Run-level checks (a capture run must actually have captured and checked something).
        nslot = int(bbb.jaccapnslot)
        nstored = int(bbb.jaccapn)
        checks = {
            "captured_at_least_one": nstored > 0,
            "caller_tags_present": all(s["from"] in ("sfsetnk", "psetnk") for s in slots),
            # lazy allocation: slot dimension doubles from what is used, capped at jaccapture
            "alloc_slots_bounded": nstored <= nslot <= min(int(bbb.jaccapture), max(1, 2 * nstored)),
        }
        if a.newton == 0:
            checks["identity_evaluated"] = any(
                "check_raw_times_inv_suscal_bitwise_eq_bbb_jac" in s for s in slots)
        out["capture_run_checks"] = checks
        alloc = {
            "jaccapnslot": nslot,
            "jaccapnnzmx": int(bbb.jaccapnnzmx),
            "jaccapneqp1": int(bbb.jaccapneqp1),
        }
        if nslot > 0:  # the arrays are unallocated before the first capture
            alloc["jaccapv_shape"] = list(np.shape(bbb.jaccapv))
            alloc["bytes"] = int(bbb.jaccapv.nbytes + bbb.jaccapj.nbytes + bbb.jaccapi.nbytes)
        out["capture_alloc"] = alloc
    # get_fnrm last: it re-evaluates the RHS and may overwrite yldot.
    out["fnrm"] = float(bbb.get_fnrm(bbb.dtreal)).hex()
    sys.stdout.flush()
    print("FINGERPRINT " + json.dumps(out, sort_keys=True), flush=True)


# --------------------------------------------------------------------------- parent
def run_one(python, case, deck, child_args, threads, envs, keep, add_files=()):
    work = tempfile.mkdtemp(prefix="capchk_")
    rundir = os.path.join(work, "case")
    shutil.copytree(case, rundir, ignore=shutil.ignore_patterns("__pycache__"))
    for f in add_files:  # e.g. rate files the installed package does not ship
        shutil.copy(f, rundir)
    home = os.path.join(work, "home")
    os.mkdir(home)
    env = dict(os.environ)
    env.update({"HOME": home, "OMP_NUM_THREADS": str(threads), "OMP_STACKSIZE": "512M"})
    for kv in envs:
        k, v = kv.split("=", 1)
        env[k] = v
    cmd = [python, "-I", os.path.abspath(__file__), "child", "--deck", deck] + child_args
    proc = subprocess.run(cmd, cwd=rundir, env=env, capture_output=True, text=True)
    fp = None
    fnrms = []
    for line in proc.stdout.splitlines():
        if line.startswith("FINGERPRINT "):
            fp = json.loads(line[len("FINGERPRINT "):])
        else:
            m = FNRM_RE.search(line)
            if m:
                fnrms.append(m.group(1))
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    if fp is None:
        sys.stderr.write(proc.stdout[-4000:] + "\n" + proc.stderr[-4000:] + "\n")
        raise RuntimeError("child failed (exit %d): %s" % (proc.returncode, " ".join(cmd)))
    fp["fnrm_printed_seq"] = fnrms
    return fp


def capture_checks(label, fp):
    """Print the capture-hook checks of one fingerprint; return True if all pass."""
    ok = True
    for s in fp.get("slots", []):
        print("[%s] slot %d: seq=%d src=%s from=%s neq=%d nnz=%d ia_last_ok=%s sha256(v,j,i)=%s %s %s"
              % (label, s["slot"], s["seq"], s["src"], s["from"], s["neq"], s["nnz"], s["ia_last_ok"],
                 s["v"][:16], s["j"][:16], s["i"][:16]))
        ok &= s["ia_last_ok"]
        for key in sorted(s):
            if key.startswith("check_"):
                print("[%s] slot %d: %s = %s" % (label, s["slot"], key[6:], s[key]))
                if isinstance(s[key], bool):
                    ok &= s[key]
    # Run-level checks exist only for runs with --capture K>0; any False fails the run.
    for key, val in sorted(fp.get("capture_run_checks", {}).items()):
        print("[%s] run: %s = %s" % (label, key, val))
        ok &= bool(val)
    if "capture_alloc" in fp:
        print("[%s] run: allocation %s" % (label, json.dumps(fp["capture_alloc"], sort_keys=True)))
    return ok


def parent(argv):
    p = argparse.ArgumentParser(prog="capture_check.py run|compare")
    p.add_argument("mode", choices=["run", "compare"])
    p.add_argument("--case", required=True, help="case directory (copied, never written)")
    p.add_argument("--deck", default="input.py")
    p.add_argument("--python", help="python for run")
    p.add_argument("--base", help="reference python for compare")
    p.add_argument("--new", help="python under test for compare")
    p.add_argument("--label", default="case")
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--env", action="append", default=[], dest="setenv", metavar="K=V")
    p.add_argument("--keep", action="store_true", help="keep the temporary run directories")
    p.add_argument("--add-file", action="append", default=[], dest="add_files", metavar="PATH",
                   help="extra file copied into the run directory (repeatable)")
    p.add_argument("--new-extra", default="",
                   help="extra child arguments for the --new run only (e.g. '--capture 4', to show "
                        "that turning the hook on does not change results)")
    if "--" in argv:
        cut = argv.index("--")
        argv, child_args = argv[:cut], argv[cut + 1:]
    else:
        child_args = []
    a = p.parse_args(argv)
    case = os.path.abspath(a.case)
    print("[%s] case=%s deck=%s child_args=%s OMP_NUM_THREADS=%d env=%s"
          % (a.label, case, a.deck, " ".join(child_args), a.threads, a.setenv))
    if a.mode == "run":
        fp = run_one(a.python, case, a.deck, child_args, a.threads, a.setenv, a.keep, a.add_files)
        print("[%s] python=%s" % (a.label, a.python))
        print("[%s] FINGERPRINT %s" % (a.label, json.dumps(fp, sort_keys=True)))
        ok = capture_checks(a.label, fp)
        print("RESULT %s: %s" % (a.label, "PASS" if ok else "FAIL"))
        return 0 if ok else 1
    base = run_one(a.base, case, a.deck, child_args, a.threads, a.setenv, a.keep, a.add_files)
    new = run_one(a.new, case, a.deck, child_args + shlex.split(a.new_extra), a.threads,
                  a.setenv, a.keep, a.add_files)
    print("[%s] base=%s" % (a.label, a.base))
    print("[%s] new =%s %s" % (a.label, a.new, a.new_extra))
    ok = True
    keys = sorted(set(base) | set(new))
    for key in keys:
        if key in ("slots", "capture_alloc", "capture_run_checks") or key.startswith("jaccap"):
            continue  # capture-only fields, absent in the reference build
        b, n = base.get(key), new.get(key)
        same = b == n
        ok &= same
        shown = b if not isinstance(b, list) else "n=%d %s" % (len(b), " ".join(b))
        if same:
            print("[%s] %-17s EQUAL  %s" % (a.label, key, shown))
        else:
            print("[%s] %-17s DIFF   base=%s new=%s" % (a.label, key, b, n))
    if "jaccapture" in new:
        print("[%s] new build capture state: jaccapture=%d jaccapcount=%d jaccapn=%d"
              % (a.label, new["jaccapture"], new["jaccapcount"], new["jaccapn"]))
    if not base["fnrm_printed_seq"]:
        print("[%s] WARNING: no printed fnrm lines captured" % a.label)
    ok &= capture_checks(a.label + ":new", new)
    print("RESULT %s: %s" % (a.label, "PASS (bitwise equal)" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "child":
            child(sys.argv[2:])
            sys.exit(0)
        sys.exit(parent(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # harness error
        sys.stderr.write("capture_check: %s\n" % exc)
        sys.exit(2)
