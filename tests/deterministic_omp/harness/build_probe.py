"""Identify the UEDGE build behind an interpreter:   python -I build_probe.py <out.json>

Run by serial_check.py in a fresh process (empty HOME, empty working directory). Writes
<out.json> with the interpreter, the uedge package location and version, the SHA-256 of every
compiled extension module of the package plus one combined hash, and whether the build is an
OpenMP build. Exit status 0 on success, 2 on error ("error" in the JSON).
"""
import glob
import hashlib
import json
import os
import sys
import traceback

EXT_PATTERNS = ("*.so", "*.pyd", "*.dylib")
# gfortran/gcc emit calls into libgomp (GOMP_*); clang/icx into libomp (__kmpc_*).
OPENMP_MARKERS = (b"GOMP_", b"__kmpc_")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # for "harness"
    from harness.worker import build_identity, has_capture_hook

    import uedge
    from uedge import bbb, ppp  # noqa: F401  (ppp must exist in both build modes)

    pkg = os.path.dirname(os.path.abspath(uedge.__file__))
    exts = sorted({p for pat in EXT_PATTERNS for p in glob.glob(os.path.join(pkg, pat))})
    if not exts:
        raise RuntimeError("no compiled extension modules in {}".format(pkg))
    hashes = {os.path.basename(p): sha256(p) for p in exts}
    combined = hashlib.sha256("".join("{} {}\n".format(k, v) for k, v in sorted(hashes.items())).encode()).hexdigest()
    bbb_ext = [p for p in exts if os.path.basename(p).startswith("bbbpy")]
    if not bbb_ext:
        raise RuntimeError("no bbbpy extension in {}".format(pkg))
    with open(bbb_ext[0], "rb") as f:
        blob = f.read()
    openmp = any(m in blob for m in OPENMP_MARKERS)
    ver = bbb.uedge_ver
    try:
        ver = bytes(ver[0]).decode(errors="replace").strip() if hasattr(ver, "__getitem__") else str(ver)
    except Exception:
        ver = str(ver)
    info = None
    info_path = os.path.join(pkg, "_build_info.json")
    if os.path.exists(info_path):
        with open(info_path) as f:
            info = json.load(f)
    # pip records the source of a local install in <dist-info>/direct_url.json (PEP 610)
    direct_url = None
    try:
        from importlib.metadata import distribution

        text = distribution("uedge").read_text("direct_url.json")
        direct_url = json.loads(text) if text else None
    except Exception:
        direct_url = None
    return {
        "python": sys.executable,
        "prefix": sys.prefix,
        "python_version": sys.version.split()[0],
        "uedge_file": os.path.abspath(uedge.__file__),
        "uedge_ver": ver,
        "build_info": info,
        "direct_url": direct_url,
        "capture_hook": bool(has_capture_hook(bbb)),
        # the identity the workers record in provenance["build"]; serial_check checks every record against it
        "identity": build_identity(),
        "openmp_build": openmp,
        "extensions": hashes,
        "extensions_sha256": combined,
    }


def main():
    out = sys.argv[1]
    try:
        result, status = probe(), 0
    except BaseException:  # noqa: B902
        result, status = {"error": traceback.format_exc()}, 2
    with open(out, "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    sys.exit(status)


if __name__ == "__main__":
    main()
