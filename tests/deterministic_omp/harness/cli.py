"""Command line for the OpenMP determinism harness.

  python tests/deterministic_omp/harness/cli.py run     --preset tebox --arm jac --threads 4 --out DIR
  python tests/deterministic_omp/harness/cli.py compare DIR_A DIR_B [--rhs-signed-zero-equal yes|no|auto]
  python tests/deterministic_omp/harness/cli.py check   --preset tebox --arm jac --threads 4 --out DIR [--repeats K]
  python tests/deterministic_omp/harness/cli.py flow    [--configs tebox,full | --all] [--threads 2,4,8] --out DIR
                                                        [--arms jac,jacrhs] [--repeats K] [--gate jac|jacrhs|all|none]

`check` runs a serial reference and K OpenMP runs of the same build (each in a fresh process)
and compares every OpenMP run with the reference (agreement) and with the first OpenMP run
(determinism). `--python` selects the interpreter of the build under test (default: this one).
Every command writes JSON next to its runs and prints a short summary.
`flow` (AIUE-52, harness/flow.py) runs a configuration matrix, one serial reference per configuration,
and gives one verdict per OpenMP arm; `flow --list` prints the configurations.

Exit codes: 0 everything agrees, 1 at least one mismatch, 2 harness error. For `flow` they apply to
the gated arm(s) only (--gate, default jac); the other arm is reported but does not set the code.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import flow  # noqa: E402
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


def exit_code(reports):
    """2 if there is nothing to judge or any report has errors (the comparison can't be trusted),
    1 if any mismatch, else 0."""
    if not reports or any(r.get("errors") for r in reports):
        return 2
    return 0 if all(r["agree"] for r in reports) else 1


def cmd_compare(args):
    report = compare_records(Record(args.a), Record(args.b), _signed_zero(args.rhs_signed_zero_equal))
    print(format_report(report))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1, default=str)
    return exit_code([report])


def cmd_check(args):
    if args.repeats < 1:
        raise ValueError("--repeats must be >= 1")
    if args.arm == "serial":
        print("note: --arm serial compares serial runs with each other (a determinism check of the build)")
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
    code = exit_code(reports)
    agree = code == 0
    summary = {"agree": agree, "exit_code": code, "spec": json.loads(_spec(args).to_json()), "repeats": args.repeats,
               "provenance": runs[0].meta.get("provenance") if runs else None, "reports": reports}
    with open(os.path.join(args.out, "check.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    print("CHECK {}: {}".format(_spec(args).label(), {0: "AGREE", 1: "MISMATCH", 2: "ERROR"}[code]))
    return code


def _int_list(text):
    return [int(t) for t in text.split(",") if t.strip()]


def _name_list(text):
    return [t.strip() for t in text.split(",") if t.strip()]


def cmd_flow(args):
    if args.list:
        for name, c in flow.CONFIGS.items():
            print("{:<10s} preset {:<10s} {}".format(name, c["preset"], c["what"]))
        print("quick set (default): {} at threads {}; --all: every configuration at threads {}".format(
            ",".join(flow.QUICK_CONFIGS), flow.QUICK_THREADS, flow.ALL_THREADS))
        return 0
    if not args.out:
        raise ValueError("flow needs --out")
    configs = list(flow.CONFIGS) if args.all else _name_list(args.configs or ",".join(flow.QUICK_CONFIGS))
    threads = _int_list(args.threads) if args.threads else (flow.ALL_THREADS if args.all else flow.QUICK_THREADS)
    code, _ = flow.run_flow(args.out, configs, _name_list(args.arms), threads, args.repeats, python=args.python,
                            cores=args.cores, max_jobs=args.max_jobs, gate=args.gate, itermx=args.itermx,
                            omp_stacksize=args.omp_stacksize, ppp=json.loads(args.ppp) if args.ppp else {},
                            rhs_signed_zero_equal=_signed_zero(args.rhs_signed_zero_equal))
    return code


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
    s = sub.add_parser("flow", help="configuration matrix with per-arm verdicts (harness/flow.py)")
    s.add_argument("--configs", default=None,
                   help="comma list of configurations (default: the quick set {})".format(",".join(flow.QUICK_CONFIGS)))
    s.add_argument("--all", action="store_true", help="every configuration, threads {} unless --threads".format(
        ",".join(map(str, flow.ALL_THREADS))))
    s.add_argument("--threads", default=None, help="comma list of thread counts (default: {}; --all: {})".format(
        ",".join(map(str, flow.QUICK_THREADS)), ",".join(map(str, flow.ALL_THREADS))))
    s.add_argument("--arms", default=",".join(flow.OMP_ARMS), help="comma list of OpenMP arms (default: jac,jacrhs)")
    s.add_argument("--repeats", type=int, default=2, help="K fresh-process OpenMP runs per group (default 2)")
    s.add_argument("--gate", default="jac", choices=flow.GATES, help="arm(s) that set the exit code (default jac)")
    s.add_argument("--cores", type=int, default=None, help="core budget for concurrent runs (default: all)")
    s.add_argument("--max-jobs", type=int, default=8, help="at most this many runs at a time (default 8)")
    s.add_argument("--itermx", type=int, default=None, help="Newton iterations (default: one evaluation)")
    s.add_argument("--omp-stacksize", default="512M")
    s.add_argument("--ppp", default=None, help="extra ppp settings as JSON for every run")
    s.add_argument("--python", default=None, help="interpreter of the build under test")
    s.add_argument("--out", default=None, help="new directory for the flow")
    s.add_argument("--rhs-signed-zero-equal", default="auto", choices=["yes", "no", "auto"])
    s.add_argument("--list", action="store_true", help="print the configurations and exit")
    s = sub.add_parser("compare")
    s.add_argument("a")
    s.add_argument("b")
    s.add_argument("--rhs-signed-zero-equal", default="auto", choices=["yes", "no", "auto"])
    s.add_argument("--json", default=None)
    args = p.parse_args(argv)
    if getattr(args, "arm", None) == "serial":
        args.threads = 1
    try:
        return {"run": cmd_run, "compare": cmd_compare, "check": cmd_check, "flow": cmd_flow}[args.cmd](args)
    except (HarnessError, ValueError, OSError, KeyError) as err:
        print("HARNESS ERROR: {}".format(err), file=sys.stderr)
        return 2
    except Exception:  # anything unexpected is a harness error, never a "mismatch"
        import traceback

        print("HARNESS ERROR (unexpected):\n{}".format(traceback.format_exc()), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
