"""The installed UEDGE's build record (uedge/_build_info.json, written by setup.py since AIUE-181), for the tests whose
outcome depends on how UEDGE was compiled (owner, 2026-10-23, AIUE-96 D1, D3 and D4).

    info()            the record of the uedge the children import, found without importing uedge in this process;
                      None if the install has none (built before AIUE-181)
    fma_contraction() whether the record shows a macOS build that may contract a*b+c into one FMA instruction
                      (AIUE-164): darwin, an -O2 or higher level and no -ffp-contract=off. Its round-off differs from
                      the Linux release build's and from -O0, which are authoritative (D1)
"""
import importlib.util
import json
from pathlib import Path

RECORD = "_build_info.json"
MISSING = "no build record (uedge/{}): rebuild with AIUE-181's setup.py".format(RECORD)
CONTRACTING = ("-O2", "-O3", "-Ofast")  # D1's builds; -Os contracts too (gfortran 15, arm64), but D1 does not cover it
# every BuildLimitWarning's message starts so: pytest -W "error:<REPORTED>:UserWarning" turns them into failures
# without importing this module (run_mutations.py's cross-check; -W can't import yldot)
REPORTED = "reported, not failed"


class BuildLimitWarning(UserWarning):
    """A difference the owner has accepted for this kind of build (D1): reported, never a pass in silence."""


def info():
    """The installed package's build record, or None. find_spec locates the package without importing it, so the
    parent never imports uedge (its OpenMP pin, uedge-gotchas.md)."""
    spec = importlib.util.find_spec("uedge")
    if spec is None or not spec.submodule_search_locations:
        return None
    for d in spec.submodule_search_locations:
        p = Path(d) / RECORD
        if p.is_file():
            return json.loads(p.read_text())
    return None


def last_flag(record, prefix, default):
    """The last flag starting with prefix that gfortran gets: Forthon's own flags come first, then --fargs."""
    flags = "{} {}".format(record.get("forthon_fopt") or "", record.get("fargs") or "").split()
    found = [f for f in flags if f.startswith(prefix)]
    return found[-1] if found else default


def fma_contraction(record):
    if record is None:
        return False
    return (record.get("platform") == "darwin" and last_flag(record, "-O", "-O0") in CONTRACTING
            and last_flag(record, "-ffp-contract=", None) != "-ffp-contract=off")
