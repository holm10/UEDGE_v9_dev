"""Pre-flight check of the flows' ppp fields against the build (AIUE-57 CI): every key must exist in uedge.ppp.

  python -I ppp_keys.py "name|configs|threads|K|arms|itermx|ppp;..."

A ppp key the build does not have (a pre-AIUE-61 build has no OMPJacMinChunkLen; a later rename) would otherwise
surface only as Forthon's generic "no such attribute" in every run. Run from run_omp_ci.sh after the smoke test
(empty HOME, so no .uedgerc). Exit 0 all keys exist (or no flow sets ppp), 2 a missing key or a field that is not
a JSON object, naming the flow and the key.
"""
import json
import sys


def flow_ppp(flows):
    """[(flow name, {key: value})] for every flow spec with a non-empty 7th field; ValueError on bad JSON."""
    out = []
    for spec in [s for s in flows.split(";") if s.strip()]:
        fields = spec.split("|")
        text = fields[6].strip() if len(fields) > 6 else ""
        if not text:
            continue
        try:
            value = json.loads(text)
        except ValueError as err:
            raise ValueError("flow {}: ppp field is not JSON ({}): {}".format(fields[0], err, text))
        if not isinstance(value, dict):
            raise ValueError("flow {}: ppp field is not a JSON object: {}".format(fields[0], text))
        out.append((fields[0], value))
    return out


def missing(flows, ppp):
    """['flow X: ppp.KEY'] for every key the ppp package lacks."""
    return ["flow {}: ppp.{}".format(name, key) for name, keys in flow_ppp(flows) for key in keys
            if not hasattr(ppp, key)]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    flows = argv[0] if argv else ""
    try:
        specs = flow_ppp(flows)
    except ValueError as err:
        print("ppp_keys: ERROR: {}".format(err))
        return 2
    if not specs:
        print("ppp_keys: no flow sets ppp")
        return 0
    from uedge import ppp
    gone = missing(flows, ppp)
    if gone:
        print("ppp_keys: ERROR: the build has no such ppp variable: {} (exit 2)".format("; ".join(gone)))
        return 2
    print("ppp_keys: OK ({})".format(", ".join(sorted({k for _, keys in specs for k in keys}))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
