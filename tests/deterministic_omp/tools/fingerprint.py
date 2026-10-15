"""Bitwise fingerprint of one evaluation of the reproducer case.

Usage (from a directory that holds a copy of the case files):
    OMP_NUM_THREADS=1 python -I fingerprint.py [--tebox] [--omp-jac] [--itermx N]

Runs input_mod4.py from the current directory, then one exmain(). With the default
ftol=1e20 that is one Jacobian (sfsetnk) and the iteration-0 residual; with
--itermx N it is N Newton iterations at ftol=1e-8. Prints, and writes to ./fingerprint.json, one JSON object with
SHA-256 digests of the raw bytes of yldot, the post-exmain jac/jacj/jaci, sfscal
and suscal, plus get_fnrm() as float.hex. Two runs are bitwise equal if and only if
the JSON objects are equal. The harness of AIUE-49 supersedes this script.
"""
import hashlib
import json
import sys

sys.path.insert(0, ".")


def digest(array):
    return hashlib.sha256(array.tobytes()).hexdigest()


def main(argv):
    from input_mod4 import bbb, ppp  # noqa: E402  (runs the deck)

    if "--tebox" in argv:
        bbb.isnion = 0
        bbb.isngon = 0
        bbb.isupon = 0
        bbb.istion = 0
        bbb.isphion = 0
        bbb.isphiofft = 1
        bbb.isteoffxy = 1
        bbb.isteoffxy[3:8, 18:23] = 0
    if "--omp-jac" in argv:
        ppp.OMPParallelJac = 1
        ppp.OMPlenpfac = 20
    if "--itermx" in argv:
        bbb.itermx = int(argv[argv.index("--itermx") + 1])
    else:
        bbb.ftol = 1e20
    bbb.exmain()

    neq = int(bbb.neq)
    nnz = int(bbb.jaci[neq]) - 1
    # yldot first: get_fnrm() evaluates the RHS again (serial pandf) and overwrites it
    yldot = digest(bbb.yldot[:neq])
    out = {
        "neq": neq,
        "nnz": nnz,
        "yldot": yldot,
        "fnrm": float(bbb.get_fnrm(bbb.dtreal)).hex(),
        "jac": digest(bbb.jac[:nnz]),
        "jacj": digest(bbb.jacj[:nnz]),
        "jaci": digest(bbb.jaci[: neq + 1]),
        "sfscal": digest(bbb.sfscal[:neq]),
        "suscal": digest(bbb.suscal[:neq]),
    }
    # Also write a file: when stdout is redirected to a file, the Fortran runtime's
    # buffered output can overwrite lines Python printed to the same file.
    with open("fingerprint.json", "w") as f:
        json.dump(out, f, sort_keys=True)
    print("FINGERPRINT " + json.dumps(out, sort_keys=True), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
