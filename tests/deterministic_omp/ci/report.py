"""Summarise the OpenMP CI flows (AIUE-57) and name the first mismatch.

  python report.py --set pr --gate jac --gate-mode bitwise --wall 812 OUT/tebox OUT/full

Each positional argument is the --out directory of one `cli.py flow` run (it holds flow.json and
summary.md). The script

* prints one line per gated failure: configuration, arm, threads, equation and cell of the first
  mismatch, plus the raw first-mismatch text of the flow;
* prints one FIRST MISMATCH line for the whole job, taken preferably from a one-evaluation flow
  (settings.itermx null): there the post-exmain Jacobian is in natural order, so its first mismatch is
  the real defect cell. Under --itermx N the post-exmain Jacobian is the permuted psetnk one, compared by
  position only; such a group cites the one-evaluation group of the same configuration/arm/threads for
  the location, and otherwise the first cell-mapped entry it has (which may be downstream of the defect);
* checks that every serial reference of an --itermx N flow made N Newton iterations (exit 2 if not);
* writes OUT/summary.md (the combined summary; OUT is the parent of the first flow directory) and,
  when GITHUB_STEP_SUMMARY is set, appends the same text to it;
* on GitHub Actions (GITHUB_ACTIONS=true) emits ::error:: annotations for the gated arm(s) and
  ::warning:: annotations for the report-only arm(s).

Exit code: the largest flow exit code (2 harness error > 1 mismatch > 0 clean); 2 when a flow left
no readable flow.json (the flow itself stopped before writing it) or an --itermx N serial reference
iterated fewer than N times.
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


def first_localised(group):
    """(equation, cell, section) of the first mismatch that is mapped to a cell, scanning the group's
    failing comparison reports in compare order; (None, None, None) if there is none. Needed when the
    first failing section is a permuted post-exmain Jacobian (psetnk, ireorder=1), which the harness
    compares by position ('position 12') and does not map to cells."""
    for rep in group.get("reports", []):
        if rep.get("agree") or rep.get("errors"):
            continue
        for name, sec in rep.get("sections", {}).items():
            for f in sec.get("first") or []:
                for key in ("row", "at"):
                    eq, cell = locate("{} {}".format(key, f.get(key, "")))
                    if eq:
                        return eq, cell, name
    return None, None, None


def failed_reports(group):
    return any(not r.get("agree") and not r.get("errors") for r in group.get("reports", []))


def load_flow(path):
    try:
        with open(os.path.join(path, "flow.json")) as f:
            return json.load(f)
    except (OSError, ValueError) as err:
        return {"_error": "{}: no readable flow.json ({})".format(path, err)}


def problem_lines(name, flow, located=None):
    """[{gated, line, eq, cell, direct}] for every group that is not PASS, in summary order. `located`
    maps (config, arm, threads) to (eq, cell, flow name) from one-evaluation flows; direct is True when
    the cell is the location of the group's own first mismatch."""
    located = located or {}
    gated = set(flow.get("gated", []))
    out = []
    for g in flow.get("groups", []):
        if g.get("verdict") == "PASS":
            continue
        key = (g.get("config"), g.get("arm"), g.get("threads"))
        where = "configuration {}, arm {}, threads {}".format(*key)
        eq = cell = None
        direct = False
        if g.get("verdict") == "ERROR":
            text = "ERROR (cannot judge): " + "; ".join(g.get("errors", []))[:400]
        else:
            first = g.get("first_mismatch", "")
            agree = g.get("agree_serial", "?")
            eq, cell = locate(first)
            if eq:
                direct = True
                text = "FAIL: first mismatch in equation {}, cell ({}); {} runs agree with serial; {}".format(
                    eq, cell, agree, first)
            elif failed_reports(g):  # first failing section has no cell map (permuted post-exmain Jacobian)
                text = "FAIL: first mismatch at permuted Jacobian positions (not mapped to cells)"
                if key in located:
                    eq, cell, src = located[key]
                    direct = True
                    text += "; located by the one-evaluation group [{}]: equation {}, cell ({})".format(src, eq, cell)
                else:
                    deq, dcell, sec = first_localised(g)
                    if deq:
                        eq, cell = deq, dcell
                        text += ("; first cell-mapped differing entry (may be downstream of the defect): "
                                 "equation {}, cell ({}) [{}]").format(deq, dcell, sec)
                    else:
                        text += "; no cell-mapped section differs"
                text += "; {} runs agree with serial; {}".format(agree, first)
            else:  # every failing run stopped (crash, solver stop, timeout): nothing to localise
                text = "FAIL: no comparable mismatch, the OpenMP run(s) failed; {} runs agree with serial; {}".format(
                    agree, first)
            if g.get("run_failures") and (eq or failed_reports(g)):
                text += "; plus {} failed run(s)".format(len(g["run_failures"]))
        out.append({"gated": g.get("arm") in gated, "line": "[{}] {}: {}".format(name, where, text),
                    "where": where, "flow": name, "eq": eq, "cell": cell, "direct": direct,
                    "one_eval": flow.get("settings", {}).get("itermx") is None})
    return out


def one_eval_locations(flows):
    """(config, arm, threads) -> (eq, cell, flow name) of the first mismatch of failing groups in
    one-evaluation flows whose first mismatch is cell-mapped."""
    located = {}
    for name, flow in flows:
        if flow.get("settings", {}).get("itermx") is not None:
            continue
        for g in flow.get("groups", []):
            if g.get("verdict") != "FAIL":
                continue
            eq, cell = locate(g.get("first_mismatch", ""))
            key = (g.get("config"), g.get("arm"), g.get("threads"))
            if eq and key not in located:
                located[key] = (eq, cell, name)
    return located


def iteration_problems(path, flow):
    """Serial references of an --itermx N flow that made fewer than N Newton iterations (the record's
    largest `iterations[].iter`): such a configuration does not test what the CI set claims."""
    itermx = flow.get("settings", {}).get("itermx")
    if not itermx:
        return []
    out, seen = [], set()
    for g in flow.get("groups", []):
        rundir = (g.get("serial") or {}).get("rundir")
        if not rundir or rundir in seen:
            continue
        seen.add(rundir)
        try:
            with open(os.path.join(path, rundir, "record.json")) as f:
                its = json.load(f).get("iterations", [])
        except (OSError, ValueError):
            continue  # a failed serial reference is already an ERROR of the flow
        done = max([int(i.get("iter", 0)) for i in its] or [0])
        if done < int(itermx):
            out.append("serial reference {} made {} Newton iteration(s), fewer than --itermx {}".format(
                rundir, done, itermx))
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
    blocks, gated, report_only, timing, loaded = [], [], [], [], []
    for path in args.flows:
        name = os.path.basename(os.path.normpath(path))
        flow = load_flow(path)
        if "_error" in flow:
            code = 2
            gated.append({"line": "[{}] ERROR: {}".format(name, flow["_error"]), "direct": False})
            continue
        loaded.append((path, name, flow))
    located = one_eval_locations([(n, f) for _, n, f in loaded])
    for path, name, flow in loaded:
        code = max(code, int(flow.get("exit_code", 2)))
        for problem in iteration_problems(path, flow):
            code = 2
            gated.append({"line": "[{}] ERROR (cannot judge): {}".format(name, problem), "direct": False})
        for entry in problem_lines(name, flow, located):
            (gated if entry["gated"] else report_only).append(entry)
        t = flow.get("timing", {})
        s = flow.get("settings", {})
        timing.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            name, ",".join(s.get("configs", [])), ",".join(str(x) for x in s.get("threads", [])),
            s.get("repeats"), s.get("itermx") or "one evaluation", t.get("runs_wall_s"), t.get("total_wall_s")))
        try:
            with open(os.path.join(path, "summary.md")) as f:
                body = f.read().replace("# OpenMP test flow", "").strip()
        except OSError:
            body = "(no summary.md)"
        blocks.append("### Flow `{}`\n\n{}\n".format(name, body))

    # the job's headline: a cell-mapped first mismatch, one-evaluation flows first
    headline = None
    ranked = sorted([e for e in gated if e.get("direct")], key=lambda e: not e.get("one_eval"))
    if ranked:
        e = ranked[0]
        headline = "FIRST MISMATCH: {}, equation {}, cell ({}) (flow {})".format(e["where"], e["eq"], e["cell"],
                                                                                 e["flow"])
    gated_lines = [e["line"] for e in gated]
    report_lines = [e["line"] for e in report_only]

    verdict = {0: "PASS", 1: "FAIL", 2: "ERROR"}.get(code, "ERROR")
    head = ["## OpenMP determinism CI: {} (set {}, gate {}, {})".format(verdict, args.set, args.gate,
                                                                        args.gate_mode), ""]
    if headline:
        head += ["**{}**".format(headline), ""]
    if gated_lines:
        head += ["**Gated failures (first mismatch per group):**", ""] + ["- " + ln for ln in gated_lines] + [""]
    if report_lines:
        head += ["Report-only arm(s), not gating:", ""] + ["- " + ln for ln in report_lines] + [""]
    head += ["| flow | configurations | threads | repeats | itermx | runs wall s | total wall s |",
             "|---|---|---|---|---|---|---|"] + timing + [""]
    if args.wall is not None:
        head += ["Wall time of all flows (run_omp_ci.sh): {} s".format(args.wall), ""]
    text = "\n".join(head + blocks)

    if headline:
        print(headline, flush=True)
        annotate("error", "OpenMP first mismatch ({})".format(args.set), headline)
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
