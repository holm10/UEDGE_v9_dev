"""Summarise the OpenMP CI flows (AIUE-57), name the first mismatch, and set the job's exit code.

  python report.py --set pr --gate jac --gate-mode bitwise --tol 1e-6 --common-code 0 --bound-codes 0,0 \
      --wall 812 OUT/tebox OUT/full

Each positional argument is the --out directory of one `cli.py flow` run (it holds flow.json, summary.md and the
bound.json that ci/jac_bound.py wrote). The script

* prints one line per gated failure: configuration, arm, threads, equation and cell of the first
  mismatch, plus the raw first-mismatch text of the flow;
* prints one FIRST MISMATCH line for the whole job, taken preferably from a one-evaluation flow
  (settings.itermx null): there the post-exmain Jacobian is in natural order, so its first mismatch is
  the real defect cell. Under --itermx N the post-exmain Jacobian is the permuted psetnk one, compared by
  position only; such a group cites the one-evaluation group of the same configuration/arm/threads for
  the location, and otherwise the first cell-mapped entry it has (which may be downstream of the defect);
* applies the C1 bound (bound.json) to every gated jac group as a backstop: a group outside the bound is a
  gated failure even when the flow passed it bitwise; a missing bound.json, group or run entry, or a
  bound ERROR is exit 2 (fail closed). The bound judges post_exmain, the LAST Jacobian of each run (in
  --itermx flows the last, permuted one; the flow compares every Jacobian bitwise);
* --gate-mode "tolerance V" (OMP_CI_JAC_TOLERANCE): a gated jac group that FAILed bitwise counts as
  PASS (within tolerance) only if no run failed, it is deterministic, every failing section is a Jacobian
  section, and every run has a bound.json entry within the bound (computed with --tol V). The exit code is
  then recomputed from the adjusted verdicts; flow ERRORs (2), missing flow.json, iteration problems, bound
  and common-block codes are kept;
* --common-code: the result of ci/common_check.py (0 PASS, 1 FAIL, 2 ERROR; omitted = skipped), shown in
  the summary and folded into the exit code, so the verdict line never says PASS for a red job;
* for flows whose ppp sets OMPJacVerbose, lists the NchunksJac values the jac runs printed (run.log);
* checks that every serial reference of an --itermx N flow made N Newton iterations (exit 2 if not);
* writes OUT/summary.md (the combined summary; OUT is the parent of the first flow directory) and,
  when GITHUB_STEP_SUMMARY is set, appends the same text to it;
* on GitHub Actions (GITHUB_ACTIONS=true) emits ::error:: annotations for the gated arm(s) and
  ::warning:: annotations for the report-only arm(s).

Exit code: the largest of the flow exit codes (bitwise mode) or of the adjusted gated verdicts (tolerance
mode), the bound and common-block results (2 harness error > 1 mismatch > 0 clean); 2 when a flow left no
readable flow.json, a bound result is missing, or an --itermx N serial reference iterated fewer than N times.
"""
import argparse
import json
import os
import re
import sys

CELL = re.compile(r"(?:row|at) ([A-Za-z_]+(?:\[\d+\])?)\(ix=(\d+),iy=(\d+)\)")
NCHUNKS = re.compile(r"NchunksJac:\s*(\d+)")
CODE_TEXT = {0: "PASS", 1: "FAIL", 2: "ERROR"}


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


def load_bound(path):
    """The bound.json that ci/jac_bound.py wrote into a flow directory, or {"_error": why}."""
    try:
        with open(os.path.join(path, "bound.json")) as f:
            bound = json.load(f)
    except (OSError, ValueError) as err:
        return {"_error": "no readable bound.json in {} ({})".format(path, err)}
    if not isinstance(bound, dict) or not isinstance(bound.get("groups"), dict):
        return {"_error": "bound.json in {} has no groups".format(path)}
    if bound.get("error"):
        return {"_error": "C1 bound could not run: {}".format(bound["error"])}
    return bound


def bound_status(bound, g):
    """(status, text, complete) of the C1 bound for one jac group: status 'pass', 'fail' or 'error'
    (fail closed: a missing group or run entry is an error); complete is True when every run of the group
    has a judged entry (none skipped because the run left no record)."""
    if "_error" in bound:
        return "error", "C1 bound: " + bound["_error"], False
    key = "{}/jac_t{}".format(g.get("config"), g.get("threads"))
    entry = bound["groups"].get(key)
    if not isinstance(entry, dict):
        return "error", "C1 bound: no entry for group {} in bound.json".format(key), False
    if entry.get("error"):
        return "error", "C1 bound: {}: {}".format(key, entry["error"]), False
    runs = entry.get("runs") or {}
    expected = [os.path.basename(r["rundir"]) for r in g.get("runs", []) if r.get("rundir")]
    missing = [r for r in expected if r not in runs]
    if missing or not runs:
        return "error", "C1 bound: no entry for {} of group {} in bound.json".format(
            ", ".join(missing) or "any run", key), False
    errors = ["{}: {}".format(r, res["error"]) for r, res in sorted(runs.items()) if "error" in res]
    if errors:
        return "error", "C1 bound: " + "; ".join(errors)[:400], False
    judged = {r: res for r, res in runs.items() if "pass" in res}
    complete = len(judged) == len(runs)
    if not judged:
        return "pass", "C1 bound: no run to judge (every run failed)", False
    worst = max(float(res.get("worst_dev", 0.0)) for res in judged.values())
    ratio = max(float(res.get("worst_ratio", 0.0)) for res in judged.values())
    fails = sorted(r for r, res in judged.items() if res.get("pass") is not True)
    tol = bound.get("tol")
    if fails:
        first = judged[fails[0]].get("problems") or ["(no detail)"]
        return "fail", "C1 bound (tol {}): EXCEEDED in {}/{} runs, worst |a-b|/base {:.3g}, magnitude ratio {:.3g}; {}"\
            .format(tol, len(fails), len(judged), worst, ratio, first[0]), complete
    return "pass", "C1 bound (tol {}): within, worst |a-b|/base {:.3g}".format(tol, worst), complete


def tolerable(g):
    """A bitwise FAIL that tolerance mode may accept: no failed run or error, deterministic, and only
    Jacobian sections differ (the bound condition is checked separately)."""
    sections = g.get("failing_sections") or []
    return (g.get("verdict") == "FAIL" and not g.get("run_failures") and not g.get("errors")
            and g.get("deterministic") is True and bool(sections)
            and all(s.startswith("jacobian:") for s in sections))


def problem_lines(name, flow, located=None, bound=None, tolerance=None):
    """[{gated, line, eq, cell, direct, code, tolerated}] for every group that is not PASS, or whose C1 bound
    (gated jac groups) is not a pass, in summary order. `located` maps (config, arm, threads) to (eq, cell,
    flow name) from one-evaluation flows; direct is True when the cell is the location of the group's own
    first mismatch. code is the entry's contribution to the exit code (0 for report-only and tolerated
    entries). tolerance (a float) switches on tolerance mode; bound is the flow's bound.json (None: not
    applied)."""
    located = located or {}
    gated = set(flow.get("gated", []))
    out = []
    for g in flow.get("groups", []):
        is_gated = g.get("arm") in gated
        bs = bound_status(bound, g) if (bound is not None and is_gated and g.get("arm") == "jac") else None
        if g.get("verdict") == "PASS" and (bs is None or bs[0] == "pass"):
            continue
        key = (g.get("config"), g.get("arm"), g.get("threads"))
        where = "configuration {}, arm {}, threads {}".format(*key)
        eq = cell = None
        direct = False
        code = 0
        tolerated = False
        if g.get("verdict") == "PASS":  # bitwise PASS, but the bound backstop objects
            if bs[0] == "error":
                text, code = "ERROR (cannot judge): " + bs[1], 2
            else:
                text, code = "FAIL: the flow passed bitwise, but " + bs[1], 1
        elif g.get("verdict") == "ERROR":
            text, code = "ERROR (cannot judge): " + "; ".join(g.get("errors", []))[:400], 2
        else:
            code = 1
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
            if bs is not None:
                text += "; " + bs[1]
                if bs[0] == "error":
                    code = 2
            if tolerance is not None and is_gated and code == 1:
                if tolerable(g) and bs is not None and bs[0] == "pass" and bs[2]:
                    tolerated, code = True, 0
                    text = ("PASS (within tolerance {:g}): only Jacobian sections differ, deterministic, every run "
                            "within the C1 bound; bitwise: {}").format(tolerance, text)
                else:
                    text += "; not within tolerance {:g} ({})".format(tolerance, "C1 bound" if tolerable(g) else
                                                                      "a non-Jacobian section differs, a run failed "
                                                                      "or the group is not deterministic")
        if not is_gated:
            code = 0
        out.append({"gated": is_gated and not tolerated, "tolerated": tolerated, "code": code,
                    "line": "[{}] {}: {}".format(name, where, text),
                    "where": where, "flow": name, "eq": eq, "cell": cell, "direct": direct and not tolerated,
                    "one_eval": flow.get("settings", {}).get("itermx") is None})
    return out


def chunk_counts(path, name, flow):
    """Informational lines: the NchunksJac values the jac-arm runs printed (flows whose ppp sets
    OMPJacVerbose; ppp/omp_parallel.F90 InitOMPJac)."""
    ppp = flow.get("settings", {}).get("ppp") or {}
    if not ppp.get("OMPJacVerbose"):
        return []
    lines = []
    for g in flow.get("groups", []):
        if g.get("arm") not in ("jac", "jacrhs"):
            continue
        seen, found = set(), 0
        runs = g.get("runs", [])
        for r in runs:
            try:
                with open(os.path.join(path, r.get("rundir", ""), "run.log"), errors="replace") as f:
                    vals = {int(v) for v in NCHUNKS.findall(f.read())}
            except OSError:
                vals = set()
            if vals:
                found += 1
            seen |= vals
        lines.append("[{}] configuration {}, arm {}, threads {}: NchunksJac {} ({} of {} runs printed it)".format(
            name, g.get("config"), g.get("arm"), g.get("threads"),
            ",".join(str(v) for v in sorted(seen)) or "not found", found, len(runs)))
    return lines


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
    p.add_argument("--gate-mode", default="bitwise", choices=["bitwise", "tolerance"],
                   help="bitwise (default), or tolerance (OMP_CI_JAC_TOLERANCE; the value is --tol)")
    p.add_argument("--tol", type=float, default=1e-6,
                   help="the tolerance bound.json was computed with (default 1e-6, the C1 bound)")
    p.add_argument("--common-code", type=int, default=None,
                   help="exit code of ci/common_check.py (0, 1, 2); omitted: the check was skipped")
    p.add_argument("--bound-codes", default=None, help="comma list of ci/jac_bound.py exit codes, one per flow")
    p.add_argument("--wall", default=None, help="wall time of the flows in s (from run_omp_ci.sh)")
    p.add_argument("--codes", default=None, help="comma list of the flows' exit codes as run_omp_ci.sh saw them")
    args = p.parse_args(argv)

    tolerance = args.tol if args.gate_mode == "tolerance" else None
    mode = "bitwise" if tolerance is None else "tolerance {:g}".format(tolerance)
    seen = [min(int(c), 2) for c in args.codes.split(",")] if args.codes else []
    if tolerance is not None:  # a flow's 1 is its bitwise verdict, recomputed below; its 2 stays
        seen = [c for c in seen if c == 2]
    code = max(seen) if seen else 0
    bound_codes = [int(c) for c in args.bound_codes.split(",")] if args.bound_codes else []
    blocks, gated, report_only, tolerated, timing, loaded, chunks = [], [], [], [], [], [], []
    if any(c not in (0, 1) for c in bound_codes):
        code = 2
        gated.append({"line": "[C1 bound] ERROR (cannot judge): ci/jac_bound.py exit codes {}".format(
            args.bound_codes), "direct": False})
    common = {None: "skipped (OMP_CI_GEN_DIR not set)", 0: "PASS", 1: "FAIL", 2: "ERROR"}.get(
        args.common_code, "ERROR (exit {})".format(args.common_code))
    if args.common_code not in (None, 0):
        code = max(code, 1 if args.common_code == 1 else 2)
        gated.append({"line": "[common-block] {}: the /ompcommonscalarcopy/ check (ci/common_check.py) {} "
                              "(see ci.log)".format(common, "failed" if args.common_code == 1 else
                                                    "could not judge"), "direct": False})
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
        flow_code = min(int(flow.get("exit_code", 2)), 2)
        if tolerance is None or flow_code == 2:
            code = max(code, flow_code)
        for problem in iteration_problems(path, flow):
            code = 2
            gated.append({"line": "[{}] ERROR (cannot judge): {}".format(name, problem), "direct": False})
        bound = load_bound(path)
        if "_error" not in bound:
            btol = bound.get("tol")
            if not isinstance(btol, (int, float)) or abs(btol - args.tol) > 1e-12 * abs(args.tol):
                bound = {"_error": "bound.json tol {} differs from --tol {:g}".format(btol, args.tol)}
        for entry in problem_lines(name, flow, located, bound=bound, tolerance=tolerance):
            if entry["tolerated"]:
                tolerated.append(entry)
            elif entry["gated"]:
                gated.append(entry)
                code = max(code, entry["code"])
            else:
                report_only.append(entry)
        chunks += chunk_counts(path, name, flow)
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
    tolerated_lines = [e["line"] for e in tolerated]

    verdict = CODE_TEXT.get(code, "ERROR")
    head = ["## OpenMP determinism CI: {} (set {}, gate {}, {})".format(verdict, args.set, args.gate, mode), ""]
    if headline:
        head += ["**{}**".format(headline), ""]
    if gated_lines:
        head += ["**Gated failures (first mismatch per group):**", ""] + ["- " + ln for ln in gated_lines] + [""]
    if tolerated_lines:
        head += ["Within tolerance (bitwise FAIL accepted by OMP_CI_JAC_TOLERANCE):", ""] + \
            ["- " + ln for ln in tolerated_lines] + [""]
    if report_lines:
        head += ["Report-only arm(s), not gating:", ""] + ["- " + ln for ln in report_lines] + [""]
    head += ["Common-block check (ci/common_check.py): {}".format(common), "",
             "C1 bound (backstop; tol {:g} on the scaled post_exmain Jacobian, the last Jacobian of each run: in "
             "--itermx flows the last, permuted one): problems appear in the gated lines; every flow's bound.json "
             "is in the artifacts".format(args.tol), ""]
    if chunks:
        head += ["Chunk counts (OMPJacVerbose):", ""] + ["- " + ln for ln in chunks] + [""]
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
    for line in tolerated_lines:
        print("TOLERATED " + line, flush=True)
        annotate("warning", "OpenMP within tolerance ({})".format(args.set), line)
    for line in report_lines:
        print("REPORT-ONLY " + line, flush=True)
        annotate("warning", "OpenMP report-only arm ({})".format(args.set), line)
    for line in chunks:
        print("CHUNKS " + line, flush=True)
    print("COMMON-BLOCK " + common, flush=True)
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
