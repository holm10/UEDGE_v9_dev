"""The OpenMP test flow (AIUE-52): a configuration matrix over the harness, with per-arm verdicts.

For every configuration (an equation preset), the flow runs ONE serial reference of the build
under test and, for every OpenMP arm and thread count, K fresh-process repeats. Each group
(configuration, arm, threads) is compared with the shared serial reference (agreement) and run 0
with run k (determinism). A group passes when all K runs agree with serial AND with each other.
An arm passes when every group of that arm passes. An OpenMP run that fails (crash, solver error)
while the serial reference of the same configuration ran counts as a FAIL of its group; a failed
serial reference or an unreadable record is a harness ERROR.

    python cli.py flow --python PY --out DIR                    # quick set: tebox, full at 2, 4 threads
    python cli.py flow --configs tebox --python PY --out DIR    # Te box only (< 1 min)
    python cli.py flow --all --python PY --out DIR              # every configuration at 2, 4, 8 threads
    python cli.py flow --list                                   # the configuration table

Exit code (--gate, default jac): 2 if a gated arm has a harness ERROR, else 1 if a gated arm
fails, else 0. The other arms are run and reported but do not
change the exit code. --gate all gates on every arm, --gate none only reports (always 0 once the
flow ran). Setup errors (bad arguments, existing --out) are 2 as well.

Writes in --out: flow.json (settings, provenance, verdicts, every report) and summary.md (the table
printed at the end). Run directories: <config>/serial and <config>/<arm>_t<threads>/run<k>.
"""
import json
import os
import platform
import re
import threading
import time

from harness.compare import compare_records
from harness.config import PRESETS, RunSpec
from harness.runner import HarnessError, Record, run_spec

# The harness preset used for the phi isolation. On v9-develop full_note (full problem with isteon=0)
# fails in serial ("Jacobian row = 0" for phi(ix=11,iy=1)); the preset is being revised in AIUE-49.
PHI_PRESET = "full_note"

# name -> preset, what it isolates, and a relative cost (used only to start expensive runs first)
CONFIGS = {
    "tebox": {"preset": "tebox", "what": "owner's Te box (Te in ix 3..7, iy 18..22; 25 equations)", "cost": 1},
    "full": {"preset": "full", "what": "full problem, all equations as the deck leaves them", "cost": 100},
    "te": {"preset": "te", "what": "Te alone on the whole grid", "cost": 20},
    "ti": {"preset": "ti", "what": "Ti alone on the whole grid", "cost": 20},
    "ni": {"preset": "ni", "what": "ni (all species) alone on the whole grid", "cost": 20},
    "up": {"preset": "up", "what": "up (all species) alone on the whole grid", "cost": 20},
    "ng": {"preset": "ng", "what": "ng (all gas species) alone on the whole grid", "cost": 20},
    # The potential: phi alone fails in serial, so phi is isolated with other equations. The preset is
    # named once, in PHI_PRESET; a configuration whose serial reference fails is a harness ERROR.
    "phi": {"preset": PHI_PRESET, "what": "phi isolation (preset {}; phi alone fails in serial)".format(PHI_PRESET),
            "cost": 80},
}
OMP_ARMS = ["jac", "jacrhs"]
QUICK_CONFIGS = ["tebox", "full"]
QUICK_THREADS = [2, 4]
ALL_THREADS = [2, 4, 8]
GATES = ["jac", "jacrhs", "all", "none"]

PASS, FAIL, ERROR = "PASS", "FAIL", "ERROR"


def _print(*args):
    print(*args, flush=True)  # progress lines appear as runs finish, also when stdout is a file


# ------------------------------------------------------------------------ verdicts (no UEDGE needed)
def group_verdict(group):
    """Fill in the verdict of one group dict, from its "reports" (each with "kind" and "agree"),
    "run_failures" (OpenMP runs that failed while the serial reference ran: a FAIL) and "errors"
    (harness errors: ERROR). Returns the verdict."""
    reports = group.get("reports", [])
    failures = group.get("run_failures", [])
    agreement = [r for r in reports if r["kind"].startswith("agreement")]
    determinism = [r for r in reports if r["kind"].startswith("determinism")]
    repeats = group.get("repeats", len(agreement) + len(failures))
    group["agree_serial"] = "{}/{}".format(sum(r["agree"] for r in agreement), repeats)
    group["deterministic"] = all(r["agree"] for r in determinism) if determinism else None
    failing = [r for r in reports if not r["agree"]]
    group["first_mismatch"] = first_mismatch(failing[0]) if failing else ""
    if failures and not group["first_mismatch"]:
        group["first_mismatch"] = "failed {}".format(failures[0])
    group["equations"] = sorted(set().union(*[mismatch_equations(r) for r in failing])) if failing else []
    group["failing_sections"] = sorted({name for r in failing for name, sec in r["sections"].items()
                                        if _section_fails(sec)} | ({"run failed"} if failures else set()))
    if group.get("errors"):
        group["verdict"] = ERROR
    elif len(agreement) + len(failures) != repeats:
        group["verdict"] = ERROR
        group.setdefault("errors", []).append("missing reports")
    else:
        group["verdict"] = PASS if not (failing or failures) else FAIL
    return group["verdict"]


def failure_reason(error, rundir=None):
    """One line for a failed run: the last line of the error without the run directory, plus the
    last '***' line UEDGE wrote to run.log when the exception itself says nothing."""
    lines = [ln.strip() for ln in str(error).strip().splitlines() if ln.strip()]
    reason = re.sub(r"run in \S+ ", "", lines[-1] if lines else str(error))
    if rundir and reason in ("RuntimeError", "RuntimeError:"):
        try:
            with open(os.path.join(rundir, "run.log"), "rb") as f:
                log = f.read().replace(b"\x00", b"").decode(errors="replace")
            stars = [ln.strip() for ln in log.splitlines() if "***" in ln and "isimpon=7" not in ln]
            if stars:
                reason += " " + " ".join(stars[-1].split())
        except OSError:
            pass
    return reason


def arm_verdicts(groups):
    """{arm: PASS|FAIL|ERROR} over all groups of each arm; ERROR dominates FAIL dominates PASS."""
    out = {}
    rank = {PASS: 0, FAIL: 1, ERROR: 2}
    for g in groups:
        v = g["verdict"]
        if g["arm"] not in out or rank[v] > rank[out[g["arm"]]]:
            out[g["arm"]] = v
    return out


def gated_arms(gate, arms):
    if gate == "none":
        return []
    if gate == "all":
        return list(arms)
    return [gate] if gate in arms else []


def exit_code(verdicts, gate):
    """2 if a gated arm has an ERROR, 1 if a gated arm FAILs, else 0 (other arms are report-only)."""
    if gate not in GATES:
        raise ValueError("unknown gate {!r}; known: {}".format(gate, GATES))
    if gate in OMP_ARMS and gate not in verdicts:
        raise ValueError("--gate {} but the {} arm was not run".format(gate, gate))
    gated = [verdicts[a] for a in gated_arms(gate, verdicts)]
    if ERROR in gated:
        return 2
    if FAIL in gated:
        return 1
    return 0


def _section_fails(sec):
    return bool(sec.get("mismatches", 0) or sec.get("nonfinite_a", 0) or sec.get("nonfinite_b", 0)
                or sec.get("error"))


def first_mismatch(report):
    """'jacobian:post_exmain row te(ix=3,iy=18) col te(ix=3,iy=18) [run0 vs serial]' for the first
    mismatching section of a report (sections in compare order: Jacobians, vectors, fnrm)."""
    where = " [{}]".format(report.get("kind", ""))
    for name, sec in report["sections"].items():
        if "error" in sec:
            return "{}: {}{}".format(name, sec["error"], where)
        if not _section_fails(sec):
            continue
        first = sec.get("first") or []
        if first and "row" in first[0]:
            return "{} {} row {} col {}{}".format(name, first[0]["kind"], first[0]["row"], first[0]["col"], where)
        if first and "at" in first[0]:
            return "{} at {}{}".format(name, first[0]["at"], where)
        if first == [] and ("nonfinite_a" in sec):
            return "{}: non-finite values{}".format(name, where)
        return "{}: {} vs {}{}".format(name, sec.get("a"), sec.get("b"), where)
    return ""


def mismatch_equations(report):
    """Row equations of all localised mismatches in a report (Jacobian rows and vector entries)."""
    eqs = set()
    for sec in report["sections"].values():
        for pair in sec.get("by_equation_pair", {}):
            eqs.add(pair.split("/")[0])
        eqs.update(sec.get("by_equation", {}))
    return eqs


def summary_table(groups, verdicts, gate):
    gated = gated_arms(gate, verdicts)
    lines = ["| configuration | arm | threads | verdict | agree with serial | deterministic | mismatch rows | "
             "failing sections | first mismatch |", "|---|---|---|---|---|---|---|---|---|"]
    for g in groups:
        det = {True: "yes", False: "no", None: "n/a"}[g.get("deterministic")]
        first = g.get("first_mismatch", "")
        agree = g.get("agree_serial", "")
        if g["verdict"] == ERROR:
            first = "ERROR " + "; ".join(g.get("errors", []))[:300]
            agree = "-"
        sections = ",".join(s.replace("jacobian:", "jac:") for s in g.get("failing_sections", []))
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            g["config"], g["arm"], g["threads"], g["verdict"], agree, det,
            ",".join(g.get("equations", [])), sections, first.replace("|", "/").replace("\n", " ")))
    lines.append("")
    for arm, v in sorted(verdicts.items()):
        lines.append("ARM {}: {}{}".format(arm, v, "  (gated)" if arm in gated else "  (report only)"))
    return "\n".join(lines)


# ------------------------------------------------------------------------ plan and run
def plan(configs, arms, threads, repeats):
    """The groups of a flow, in summary order."""
    for c in configs:
        if c not in CONFIGS:
            raise ValueError("unknown configuration {!r}; known: {}".format(c, list(CONFIGS)))
        if CONFIGS[c]["preset"] not in PRESETS:
            raise ValueError("configuration {} names unknown preset {}".format(c, CONFIGS[c]["preset"]))
    for a in arms:
        if a not in OMP_ARMS:
            raise ValueError("unknown OpenMP arm {!r}; known: {}".format(a, OMP_ARMS))
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    if any(t < 1 for t in threads):
        raise ValueError("threads must be >= 1")
    return [{"config": c, "preset": CONFIGS[c]["preset"], "arm": a, "threads": t, "repeats": repeats}
            for c in configs for a in arms for t in threads]


class Job:
    def __init__(self, spec, rundir, cost, name=None):
        self.spec, self.rundir, self.cost = spec, rundir, cost
        self.name = name or rundir
        self.cores = spec.threads
        self.error = None
        self.elapsed = None


def run_jobs(jobs, cores, python, max_jobs=None, log=_print):
    """Run jobs concurrently within a budget of `cores` (a job of t threads takes t cores; a job
    wider than the budget runs alone) and at most `max_jobs` at a time (memory: a full-problem
    run peaks at ~1.4 GB). Jobs start in list order, smaller ones backfilling."""
    max_jobs = max_jobs or len(jobs) or 1
    lock = threading.Condition()
    state = {"free": cores, "running": 0}
    pending = list(jobs)

    def work(job):
        start = time.time()
        try:
            run_spec(job.spec, job.rundir, python=python)
        except (HarnessError, OSError, ValueError) as err:
            job.error = str(err)
        except Exception as err:  # noqa: B902  a bug in the harness must not hang the scheduler
            job.error = "{}: {}".format(type(err).__name__, err)
        job.elapsed = round(time.time() - start, 2)
        log("  {:<36s} {:7.1f} s  {}".format(job.name, job.elapsed,
                                             "FAILED " + failure_reason(job.error, job.rundir) if job.error else "ok"))
        with lock:
            state["free"] += job.cores
            state["running"] -= 1
            lock.notify_all()

    threads = []
    with lock:
        while pending or state["running"]:
            started = True
            while started:
                started = False
                for job in pending:
                    if state["running"] >= max_jobs:
                        break
                    if job.cores <= state["free"] or (state["running"] == 0 and job.cores > cores):
                        pending.remove(job)
                        state["free"] -= job.cores
                        state["running"] += 1
                        t = threading.Thread(target=work, args=(job,), daemon=True)
                        threads.append(t)
                        t.start()
                        started = True
                        break
            if pending or state["running"]:
                lock.wait()
    for t in threads:
        t.join()


def _load(rundir):
    try:
        return Record(rundir), None
    except (HarnessError, OSError, KeyError, ValueError) as err:
        return None, str(err)


def compare_group(group, serial_record, serial_error, run_dirs, run_errors, rhs_signed_zero_equal,
                  serial_dir=None):
    """Fill group["reports"]: agreement of every run with serial, and determinism (the first run that
    succeeded vs every later one). An OpenMP run that fails while the serial reference of the same
    build and configuration ran is a finding (run_failures, FAIL); a failed serial reference or an
    unreadable record is a harness error (errors, ERROR)."""
    group["reports"], group["errors"], group["run_failures"] = [], [], []
    if serial_error:
        group["errors"].append("serial reference failed: " + failure_reason(serial_error, serial_dir))
    for k, e in enumerate(run_errors):
        if e:
            (group["errors"] if serial_error else group["run_failures"]).append(
                "run{}: {}".format(k, failure_reason(e, run_dirs[k])))
    first = None
    for k, d in enumerate(run_dirs):
        if run_errors[k] or serial_error:
            continue
        rec, err = _load(d)
        if err:
            group["errors"].append("run{}: {}".format(k, failure_reason(err)))
            continue
        try:
            rep = compare_records(serial_record, rec, rhs_signed_zero_equal)
            rep["kind"] = "agreement (serial vs run{})".format(k)
            group["reports"].append(rep)
            if first is None:
                first = (k, rec)
            else:
                rep = compare_records(first[1], rec, rhs_signed_zero_equal)
                rep["kind"] = "determinism (run{} vs run{})".format(first[0], k)
                group["reports"].append(rep)
        except (KeyError, ValueError) as err:
            group["errors"].append("compare run{}: {}".format(k, err))
    return group_verdict(group)


def run_flow(out, configs, arms, threads, repeats, python=None, cores=None, max_jobs=8, gate="jac",
             itermx=None, omp_stacksize="512M", ppp=None, rhs_signed_zero_equal=None, log=_print):
    """Run the flow into the new directory `out`; returns (exit code, flow dict)."""
    if gate in OMP_ARMS and gate not in arms:
        raise ValueError("--gate {} but the {} arm is not in --arms".format(gate, gate))
    if gate not in GATES:
        raise ValueError("unknown gate {!r}; known: {}".format(gate, GATES))
    groups = plan(configs, arms, threads, repeats)
    cores = cores or os.cpu_count() or 1
    os.makedirs(out, exist_ok=False)
    ppp = ppp or {}

    def spec(preset, arm, t):
        return RunSpec(preset=preset, arm=arm, threads=t, itermx=itermx, omp_stacksize=omp_stacksize,
                       ppp=dict(ppp)).validate()

    serial_jobs = {c: Job(spec(CONFIGS[c]["preset"], "serial", 1), os.path.join(out, c, "serial"),
                          CONFIGS[c]["cost"], name="{}/serial".format(c)) for c in configs}
    omp_jobs = {}
    for g in groups:
        gdir = os.path.join(out, g["config"], "{}_t{}".format(g["arm"], g["threads"]))
        omp_jobs[id(g)] = [Job(spec(g["preset"], g["arm"], g["threads"]), os.path.join(gdir, "run{}".format(k)),
                               CONFIGS[g["config"]]["cost"], name=os.path.relpath(gdir, out) + "/run{}".format(k))
                           for k in range(repeats)]
        for d in (os.path.join(out, g["config"]), gdir):
            os.makedirs(d, exist_ok=True)
    # serial references first (cheap in cores, the longest runs), expensive configurations first
    order = sorted(serial_jobs.values(), key=lambda j: -j.cost)
    order += sorted([j for js in omp_jobs.values() for j in js], key=lambda j: (-j.cost, -j.cores))
    log("FLOW {} configuration(s) x {} arm(s) x threads {} x {} repeat(s): {} runs on {} cores".format(
        len(configs), len(arms), threads, repeats, len(order), cores))
    start = time.time()
    run_jobs(order, cores, python, max_jobs=max_jobs, log=log)
    run_wall = round(time.time() - start, 1)

    log("comparing ...")
    for c in configs:
        sj = serial_jobs[c]
        serial_record, serial_error = (None, sj.error) if sj.error else _load(sj.rundir)
        for g in groups:
            if g["config"] != c:
                continue
            js = omp_jobs[id(g)]
            compare_group(g, serial_record, serial_error, [j.rundir for j in js], [j.error for j in js],
                          rhs_signed_zero_equal, serial_dir=sj.rundir)
            g["runs"] = [{"rundir": os.path.relpath(j.rundir, out), "elapsed_s": j.elapsed, "error": j.error}
                         for j in js]
            g["serial"] = {"rundir": os.path.relpath(sj.rundir, out), "elapsed_s": sj.elapsed, "error": sj.error}
        del serial_record

    verdicts = arm_verdicts(groups)
    code = exit_code(verdicts, gate)
    provenance = None
    for sj in serial_jobs.values():
        rec_json = os.path.join(sj.rundir, "record.json")
        if not sj.error and os.path.exists(rec_json):
            with open(rec_json) as f:
                provenance = json.load(f).get("provenance")
            break
    flow = {
        "settings": {"configs": configs, "arms": arms, "threads": threads, "repeats": repeats, "gate": gate,
                     "cores": cores, "max_jobs": max_jobs, "itermx": itermx, "omp_stacksize": omp_stacksize,
                     "ppp": ppp, "rhs_signed_zero_equal": rhs_signed_zero_equal, "python": python,
                     "configurations": {c: CONFIGS[c] for c in configs}},
        "provenance": provenance, "driver_platform": platform.platform(),
        "timing": {"runs_wall_s": run_wall, "total_wall_s": round(time.time() - start, 1),
                   "serial_s": {c: j.elapsed for c, j in serial_jobs.items()}},
        "verdicts": verdicts, "gated": gated_arms(gate, verdicts), "exit_code": code, "groups": groups,
    }
    with open(os.path.join(out, "flow.json"), "w") as f:
        json.dump(flow, f, indent=1, default=str)
    table = summary_table(groups, verdicts, gate)
    with open(os.path.join(out, "summary.md"), "w") as f:
        f.write("# OpenMP test flow\n\n{}\n\nruns {} s wall, total {} s, exit code {} (gate {})\n".format(
            table, run_wall, flow["timing"]["total_wall_s"], code, gate))
    log(table)
    log("runs {} s wall, total {} s; exit code {} (gate {}); {}".format(
        run_wall, flow["timing"]["total_wall_s"], code, gate, os.path.join(out, "summary.md")))
    return code, flow
