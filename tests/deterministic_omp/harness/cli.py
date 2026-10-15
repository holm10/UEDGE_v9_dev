"""Command line for the OpenMP determinism harness.

  python tests/deterministic_omp/harness/cli.py run     --preset tebox --arm jac --threads 4 --out DIR
  python tests/deterministic_omp/harness/cli.py compare DIR_A DIR_B [--rhs-signed-zero-equal yes|no|auto]
  python tests/deterministic_omp/harness/cli.py check   --preset tebox --arm jac --threads 4 --out DIR [--repeats K]

`check` runs a serial reference and K OpenMP runs of the same build (each in a fresh process)
and compares every OpenMP run with the reference (agreement) and with the first OpenMP run
(determinism). `--python` selects the interpreter of the build under test (default: this one).
Every command writes JSON next to its runs and prints a short summary.

Exit codes: 0 everything agrees, 1 at least one mismatch, 2 harness error.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.compare import compare_records, format_report  # noqa: E402
from harness.config import RunSpec  # noqa: E402
from harness.runner import HarnessError, Record, run_spec  # noqa: E402


def _spec(args, arm=None, threads=None):
    ppp = json.loads(args.ppp) if args.ppp else {}
    return RunSpec(preset=args.preset, arm=arm or args.arm, threads=threads or args.threads,
                   itermx=args.itermx, omp_stacksize=args.omp_stacksize, ppp=ppp).validate()


def _signed_zero(value):
    return {"yes": True, "no": False, "auto": None}[value]


def cmd_run(args):
    record = run_spec(_spec(args), args.out, python=args.python)
    print("{}: neq {}, fnrm {}, {} s".format(record.label, record.meta["neq"],
                                             [i["fnrm_printed"] for i in record.meta["iterations"]],
                                             record.meta["elapsed_s"]))
    return 0


def cmd_compare(args):
    report = compare_records(Record(args.a), Record(args.b), _signed_zero(args.rhs_signed_zero_equal))
    print(format_report(report))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1, default=str)
    return 0 if report["agree"] else 1


def cmd_check(args):
    os.makedirs(args.out, exist_ok=False)
    ref = run_spec(_spec(args, arm="serial", threads=1), os.path.join(args.out, "serial"), python=args.python)
    runs = [run_spec(_spec(args), os.path.join(args.out, "run{}".format(k)), python=args.python)
            for k in range(args.repeats)]
    reports = []
    for k, run in enumerate(runs):
        rep = compare_records(ref, run, _signed_zero(args.rhs_signed_zero_equal))
        rep["kind"] = "agreement with serial"
        reports.append(rep)
        if k > 0:
            rep = compare_records(runs[0], run, _signed_zero(args.rhs_signed_zero_equal))
            rep["kind"] = "determinism (run0 vs run{})".format(k)
            reports.append(rep)
    for rep in reports:
        print("[{}] {}".format(rep["kind"], format_report(rep)))
    agree = all(r["agree"] for r in reports)
    summary = {"agree": agree, "spec": json.loads(_spec(args).to_json()), "repeats": args.repeats,
               "provenance": runs[0].meta.get("provenance") if runs else None, "reports": reports}
    with open(os.path.join(args.out, "check.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    print("CHECK {}: {}".format(_spec(args).label(), "AGREE" if agree else "MISMATCH"))
    return 0 if agree else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "check"):
        s = sub.add_parser(name)
        s.add_argument("--preset", default="tebox")
        s.add_argument("--arm", default="jac", choices=["serial", "jac", "jacrhs"])
        s.add_argument("--threads", type=int, default=4)
        s.add_argument("--itermx", type=int, default=None, help="Newton iterations (default: one evaluation)")
        s.add_argument("--omp-stacksize", default="512M")
        s.add_argument("--ppp", default=None, help='extra ppp settings as JSON, e.g. \'{"OMPJacNchunks": -1}\'')
        s.add_argument("--python", default=None, help="interpreter of the build under test")
        s.add_argument("--out", required=True, help="new directory for the run(s)")
        s.add_argument("--rhs-signed-zero-equal", default="auto", choices=["yes", "no", "auto"])
        if name == "check":
            s.add_argument("--repeats", type=int, default=2)
    s = sub.add_parser("compare")
    s.add_argument("a")
    s.add_argument("b")
    s.add_argument("--rhs-signed-zero-equal", default="auto", choices=["yes", "no", "auto"])
    s.add_argument("--json", default=None)
    args = p.parse_args(argv)
    if getattr(args, "arm", None) == "serial":
        args.threads = 1
    try:
        return {"run": cmd_run, "compare": cmd_compare, "check": cmd_check}[args.cmd](args)
    except (HarnessError, ValueError, OSError, KeyError) as err:
        print("HARNESS ERROR: {}".format(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
