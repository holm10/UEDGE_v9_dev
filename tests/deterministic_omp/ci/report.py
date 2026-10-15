"""Summarise the OpenMP CI flows (AIUE-57) and name the first mismatch.

  python report.py --set pr --gate jac --gate-mode bitwise --wall 812 OUT/tebox OUT/full

Each positional argument is the --out directory of one `cli.py flow` run (it holds flow.json and
summary.md). The script

* prints one line per gated failure: configuration, arm, threads, equation and cell of the first
  mismatch, plus the raw first-mismatch text of the flow;
* writes OUT/summary.md (the combined summary; OUT is the parent of the first flow directory) and,
  when GITHUB_STEP_SUMMARY is set, appends the same text to it;
* on GitHub Actions (GITHUB_ACTIONS=true) emits ::error:: annotations for the gated arm(s) and
  ::warning:: annotations for the report-only arm(s).

Exit code: the largest flow exit code (2 harness error > 1 mismatch > 0 clean); 2 when a flow left
no readable flow.json (the flow itself stopped before writing it).
"""
import argparse
import json
import os
import re
import sys

CELL = re.compile(r"(?:row|at) ([A-Za-z_]+(?:\[\d+\])?)\(ix=(\d+),iy=(\d+)\)")


def locate(text):
    """('te', 'ix=4,iy=18') from a flow first-mismatch string, or (None, None) if it names no cell."""
    m = CELL.search(text or "")
    if not m:
        return None, None
    return m.group(1), "ix={},iy={}".format(m.group(2), m.group(3))


def load_flow(path):
    try:
        with open(os.path.join(path, "flow.json")) as f:
            return json.load(f)
    except (OSError, ValueError) as err:
        return {"_error": "{}: no readable flow.json ({})".format(path, err)}


def problem_lines(name, flow):
    """[(gated, line)] for every group that is not PASS, in summary order."""
    gated = set(flow.get("gated", []))
    out = []
    for g in flow.get("groups", []):
        if g.get("verdict") == "PASS":
            continue
        where = "configuration {}, arm {}, threads {}".format(g.get("config"), g.get("arm"), g.get("threads"))
        if g.get("verdict") == "ERROR":
            text = "ERROR (cannot judge): " + "; ".join(g.get("errors", []))[:400]
        else:
            first = g.get("first_mismatch", "")
            eq, cell = locate(first)
            if eq:
                text = "FAIL: first mismatch in equation {}, cell ({}); {} runs agree with serial; {}".format(
                    eq, cell, g.get("agree_serial", "?"), first)
            else:  # every failing run stopped (crash, solver stop, timeout): nothing to localise
                text = "FAIL: no comparable mismatch, the OpenMP run(s) failed; {} runs agree with serial; {}".format(
                    g.get("agree_serial", "?"), first)
            if g.get("run_failures") and eq:
                text += "; plus {} failed run(s)".format(len(g["run_failures"]))
        out.append((g.get("arm") in gated, "[{}] {}: {}".format(name, where, text)))
    return out


def annotate(kind, title, message):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # GitHub workflow command; newlines must be escaped
        message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::{} title={}::{}".format(kind, title, message), flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("flows", nargs="+", help="flow --out directories")
    p.add_argument("--set", default="pr", help="name of the CI set (pr, nightly, custom)")
    p.add_argument("--gate", default="jac")
    p.add_argument("--gate-mode", default="bitwise", help="bitwise, or the tolerance passed to the flow")
    p.add_argument("--wall", default=None, help="wall time of the flows in s (from run_omp_ci.sh)")
    p.add_argument("--codes", default=None, help="comma list of the flows' exit codes as run_omp_ci.sh saw them")
    args = p.parse_args(argv)

    seen = [int(c) for c in args.codes.split(",")] if args.codes else []
    code = max(seen) if seen else 0
    blocks, gated_lines, report_lines, timing = [], [], [], []
    for path in args.flows:
        name = os.path.basename(os.path.normpath(path))
        flow = load_flow(path)
        if "_error" in flow:
            code = 2
            gated_lines.append("[{}] ERROR: {}".format(name, flow["_error"]))
            continue
        code = max(code, int(flow.get("exit_code", 2)))
        for is_gated, line in problem_lines(name, flow):
            (gated_lines if is_gated else report_lines).append(line)
        t = flow.get("timing", {})
        s = flow.get("settings", {})
        timing.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            name, ",".join(s.get("configs", [])), ",".join(str(x) for x in s.get("threads", [])),
            s.get("repeats"), s.get("itermx"), t.get("runs_wall_s"), t.get("total_wall_s")))
        try:
            with open(os.path.join(path, "summary.md")) as f:
                body = f.read().replace("# OpenMP test flow", "").strip()
        except OSError:
            body = "(no summary.md)"
        blocks.append("### Flow `{}`\n\n{}\n".format(name, body))

    verdict = {0: "PASS", 1: "FAIL", 2: "ERROR"}.get(code, "ERROR")
    head = ["## OpenMP determinism CI: {} (set {}, gate {}, {})".format(verdict, args.set, args.gate,
                                                                        args.gate_mode), ""]
    if gated_lines:
        head += ["**Gated failures (first mismatch per group):**", ""] + ["- " + ln for ln in gated_lines] + [""]
    if report_lines:
        head += ["Report-only arm(s), not gating:", ""] + ["- " + ln for ln in report_lines] + [""]
    head += ["| flow | configurations | threads | repeats | itermx | runs wall s | total wall s |",
             "|---|---|---|---|---|---|---|"] + timing + [""]
    if args.wall is not None:
        head += ["Wall time of all flows (run_omp_ci.sh): {} s".format(args.wall), ""]
    text = "\n".join(head + blocks)

    for line in gated_lines:
        print("GATED " + line, flush=True)
        annotate("error", "OpenMP {} arm ({})".format(args.gate, args.set), line)
    for line in report_lines:
        print("REPORT-ONLY " + line, flush=True)
        annotate("warning", "OpenMP report-only arm ({})".format(args.set), line)
    print("OMP CI RESULT: {} (exit {})".format(verdict, code), flush=True)

    out_dir = os.path.dirname(os.path.normpath(os.path.abspath(args.flows[0])))
    with open(os.path.join(out_dir, "summary.md"), "w") as f:
        f.write(text + "\n")
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a") as f:
            f.write(text + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
