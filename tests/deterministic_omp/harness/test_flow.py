"""Unit tests of the test flow (verdicts, exit codes, scheduling) with fake runs; no UEDGE build needed."""
import json
import os
import sys
import threading
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import cli, flow  # noqa: E402
from harness.config import ARMS, PRESETS, RunSpec  # noqa: E402
from harness.runner import HarnessError  # noqa: E402
from harness.test_harness import FakeRecord, csr  # noqa: E402

M = csr([[1.0, None], [None, 2.0]])


# ---------------------------------------------------------------- verdict logic on report dicts
def rep(kind, agree, section=None):
    sections = {"yldot": {"mismatches": 0, "nonfinite_a": 0, "nonfinite_b": 0, "by_equation": {}, "first": []}}
    if section:
        sections.update(section)
    return {"kind": kind, "agree": agree, "a": "a", "b": "b", "sections": sections}


JAC_TE = {"jacobian:post_exmain": {
    "mismatches": 3, "value": 3, "only_a": 0, "only_b": 0, "nonfinite_a": 0, "nonfinite_b": 0,
    "by_equation_pair": {"te/te": {"value": 2}, "te/ni": {"value": 1}},
    "first": [{"kind": "value", "row": "te(ix=3,iy=18)", "col": "te(ix=3,iy=18)"}]}}
FNRM = {"fnrm_final": {"mismatches": 1, "a": "0x1p+0", "b": "0x1.8p+0"}}


def group(*reports, repeats=2, errors=None):
    g = {"config": "tebox", "arm": "jac", "threads": 4, "repeats": repeats, "reports": list(reports)}
    if errors:
        g["errors"] = errors
    return g


def test_group_pass():
    g = group(rep("agreement (serial vs run0)", True), rep("agreement (serial vs run1)", True),
              rep("determinism (run0 vs run1)", True))
    assert flow.group_verdict(g) == flow.PASS
    assert g["agree_serial"] == "2/2" and g["deterministic"] is True and g["first_mismatch"] == ""


def test_group_fail_localised():
    g = group(rep("agreement (serial vs run0)", False, JAC_TE), rep("agreement (serial vs run1)", True),
              rep("determinism (run0 vs run1)", False, FNRM))
    assert flow.group_verdict(g) == flow.FAIL
    assert g["agree_serial"] == "1/2" and g["deterministic"] is False
    assert g["equations"] == ["te"]
    assert g["failing_sections"] == ["fnrm_final", "jacobian:post_exmain"]
    assert g["first_mismatch"].startswith("jacobian:post_exmain value row te(ix=3,iy=18) col te(ix=3,iy=18)")


def test_group_agrees_but_not_deterministic_fails():
    g = group(rep("agreement (serial vs run0)", True), rep("agreement (serial vs run1)", False, FNRM),
              rep("determinism (run0 vs run1)", False, FNRM))
    assert flow.group_verdict(g) == flow.FAIL
    assert g["first_mismatch"].startswith("fnrm_final: 0x1p+0 vs 0x1.8p+0")


def test_group_error_and_missing_reports():
    assert flow.group_verdict(group(rep("agreement (serial vs run0)", True), errors=["run1: boom"])) == flow.ERROR
    g = group(rep("agreement (serial vs run0)", True))  # repeats=2 but one agreement report
    assert flow.group_verdict(g) == flow.ERROR and "missing reports" in g["errors"]


def test_arm_verdicts_dominance():
    gs = [{"arm": "jac", "verdict": flow.PASS}, {"arm": "jac", "verdict": flow.FAIL},
          {"arm": "jacrhs", "verdict": flow.FAIL}, {"arm": "jacrhs", "verdict": flow.ERROR},
          {"arm": "jacrhs", "verdict": flow.PASS}]
    assert flow.arm_verdicts(gs) == {"jac": flow.FAIL, "jacrhs": flow.ERROR}


@pytest.mark.parametrize("jac,jacrhs,gate,code", [
    ("PASS", "PASS", "jac", 0), ("PASS", "FAIL", "jac", 0), ("PASS", "ERROR", "jac", 0),
    ("FAIL", "PASS", "jac", 1), ("FAIL", "ERROR", "jac", 1), ("ERROR", "PASS", "jac", 2),
    ("FAIL", "PASS", "jacrhs", 0), ("PASS", "FAIL", "jacrhs", 1), ("PASS", "ERROR", "jacrhs", 2),
    ("PASS", "PASS", "all", 0), ("FAIL", "PASS", "all", 1), ("PASS", "FAIL", "all", 1), ("FAIL", "ERROR", "all", 2),
    ("FAIL", "FAIL", "none", 0), ("ERROR", "ERROR", "none", 0),
])
def test_exit_code_per_arm(jac, jacrhs, gate, code):
    assert flow.exit_code({"jac": jac, "jacrhs": jacrhs}, gate) == code


def test_exit_code_gate_on_missing_arm():
    assert flow.exit_code({"jac": flow.FAIL}, "all") == 1
    with pytest.raises(ValueError):
        flow.exit_code({"jac": flow.PASS}, "jacrhs")
    with pytest.raises(ValueError):
        flow.exit_code({"jac": flow.PASS}, "bogus")


def test_plan_validation():
    gs = flow.plan(["tebox", "full"], ["jac", "jacrhs"], [2, 4], 3)
    assert len(gs) == 8 and gs[0] == {"config": "tebox", "preset": "tebox", "arm": "jac", "threads": 2, "repeats": 3}
    for bad in [(["nope"], ["jac"], [2], 1), (["tebox"], ["serial"], [2], 1), (["tebox"], ["jac"], [2], 0)]:
        with pytest.raises(ValueError):
            flow.plan(*bad)
    assert list(flow.CONFIGS) == ["tebox", "full", "te", "ti", "ni", "up", "ng", "phi"]
    assert flow.CONFIGS["phi"]["preset"] == flow.PHI_PRESET
    assert all(c["preset"] in PRESETS for c in flow.CONFIGS.values())


# ---------------------------------------------------------------- the whole flow with fake runs
def provenance(spec, **override):
    """What an OpenMP build records when the arm took effect (worker.py provenance keys)."""
    arm = ARMS[spec.arm]
    prov = {"commit": "fake", "Nthreads": spec.threads, "OMP_NUM_THREADS": str(spec.threads),
            "ParallelJac": arm["OMPParallelJac"], "ParallelPandf1": arm["OMPParallelPandf1"], **arm}
    prov.update(override)
    return prov


def fake_runner(behaviour, calls=None, prov=provenance):
    """A stand-in for runner.run_spec that writes a FakeRecord; behaviour(spec, rundir) returns the
    yldot vector, or raises HarnessError to simulate a failed run. prov(spec) gives the provenance."""
    def run_spec(spec, rundir, python=None):
        if calls is not None:
            calls.append((spec, rundir))
        os.makedirs(rundir)
        yldot = behaviour(spec, rundir)
        rec = FakeRecord(spec.label(), M, yldot)
        rec.meta["label"] = spec.label()
        rec.meta["provenance"] = prov(spec)
        np.savez(os.path.join(rundir, "record.npz"), **rec.arrays)
        with open(os.path.join(rundir, "record.json"), "w") as f:
            json.dump(rec.meta, f)
        return rec
    return run_spec


def jac_differs(spec, rundir):
    return [1.0, 2.5] if spec.arm == "jac" else [1.0, 2.0]


def run_cli(tmp_path, monkeypatch, behaviour, *extra, name="out", prov=provenance):
    monkeypatch.setattr(flow, "run_spec", fake_runner(behaviour, prov=prov))
    return cli.main(["flow", "--configs", "tebox,te", "--threads", "2,4", "--out", str(tmp_path / name)] + list(extra))


@pytest.mark.parametrize("gate,code", [("jac", 1), ("jacrhs", 0), ("all", 1), ("none", 0)])
def test_cli_flow_exit_codes_per_arm(tmp_path, monkeypatch, gate, code):
    assert run_cli(tmp_path, monkeypatch, jac_differs, "--gate", gate) == code
    out = tmp_path / "out"
    data = json.loads((out / "flow.json").read_text())
    assert data["verdicts"] == {"jac": "FAIL", "jacrhs": "PASS"} and data["exit_code"] == code
    assert len(data["groups"]) == 8 and data["provenance"]["commit"] == "fake"
    g = data["groups"][0]
    assert (g["config"], g["arm"], g["threads"], g["verdict"]) == ("tebox", "jac", 2, "FAIL")
    assert g["equations"] == ["te"] and g["first_mismatch"].startswith("yldot at te(")
    summary = (out / "summary.md").read_text()
    assert "| tebox | jac | 2 | FAIL | 0/2 | yes | te | yldot,yldot_probe | yldot at te(" in summary
    assert "| te | jacrhs | 4 | PASS | 2/2 | yes |" in summary
    # one serial reference per configuration, K runs per group
    assert sorted(os.listdir(out / "tebox")) == ["jac_t2", "jac_t4", "jacrhs_t2", "jacrhs_t4", "serial"]
    assert sorted(os.listdir(out / "tebox" / "jac_t4")) == ["run0", "run1"]


def test_cli_flow_all_agree(tmp_path, monkeypatch):
    assert run_cli(tmp_path, monkeypatch, lambda s, d: [1.0, 2.0], "--gate", "all", "--repeats", "3") == 0


def test_cli_flow_nondeterminism(tmp_path, monkeypatch):
    # run1 of every jacrhs group differs: agreement 1/2 and not deterministic
    def behaviour(spec, rundir):
        return [1.0, 3.0] if spec.arm == "jacrhs" and rundir.endswith("run1") else [1.0, 2.0]

    assert run_cli(tmp_path, monkeypatch, behaviour) == 0
    data = json.loads((tmp_path / "out" / "flow.json").read_text())
    g = [g for g in data["groups"] if g["arm"] == "jacrhs"][0]
    assert g["verdict"] == "FAIL" and g["agree_serial"] == "1/2" and g["deterministic"] is False
    assert run_cli(tmp_path, monkeypatch, behaviour, "--gate", "jacrhs", name="out2") == 1


def test_cli_flow_harness_errors(tmp_path, monkeypatch):
    def rhs_crashes(spec, rundir):
        if spec.arm == "jacrhs" and spec.threads == 4:
            raise HarnessError("run in {} exited with -10".format(rundir))
        return [1.0, 2.0]

    # an OpenMP run that crashes while serial ran is a finding (FAIL), not a harness error
    assert run_cli(tmp_path, monkeypatch, rhs_crashes, "--gate", "jac") == 0
    assert run_cli(tmp_path, monkeypatch, rhs_crashes, "--gate", "all", name="out2") == 1
    assert run_cli(tmp_path, monkeypatch, rhs_crashes, "--gate", "jacrhs", name="out2b") == 1
    summary = (tmp_path / "out" / "summary.md").read_text()
    assert "| tebox | jacrhs | 4 | FAIL | 0/2 | n/a |  | run failed | failed run0: exited with -10 |" in summary

    def run1_crashes(spec, rundir):  # determinism is then checked from the first run that succeeded
        if spec.arm == "jac" and rundir.endswith("run0"):
            raise HarnessError("run in {} exited with -11".format(rundir))
        return [1.0, 2.0]

    assert run_cli(tmp_path, monkeypatch, run1_crashes, "--repeats", "3", name="out4") == 1
    g = json.loads((tmp_path / "out4" / "flow.json").read_text())["groups"][0]
    assert g["agree_serial"] == "2/3" and g["deterministic"] is True and g["verdict"] == "FAIL"
    assert [r["kind"] for r in g["reports"]][-1] == "determinism (run1 vs run2)"

    # a failed serial reference is a harness error for every group of that configuration
    def serial_crashes(spec, rundir):
        if spec.arm == "serial" and spec.preset == "te":
            raise HarnessError("run in {} failed:\nTraceback\nRuntimeError".format(rundir))
        return [1.0, 2.0]

    assert run_cli(tmp_path, monkeypatch, serial_crashes, name="out3") == 2
    assert run_cli(tmp_path, monkeypatch, serial_crashes, "--gate", "none", name="out3b") == 0
    data = json.loads((tmp_path / "out3" / "flow.json").read_text())
    assert [g["verdict"] for g in data["groups"] if g["config"] == "te"] == ["ERROR"] * 4
    assert data["groups"][-1]["errors"][0] == "serial reference failed: RuntimeError"
    assert "| te | jac | 2 | ERROR |" in (tmp_path / "out3" / "summary.md").read_text()


def test_failure_reason(tmp_path):
    (tmp_path / "run.log").write_bytes(b" iter= 0\x00\n*** For isimpon=7, set afracs, not afrac ***\n"
                                       b" *** Error: Jacobian row = 0 for eqn iv =      1092\n")
    err = "run in {} failed:\nTraceback (most recent call last):\n  ...\nRuntimeError\n".format(tmp_path)
    assert flow.failure_reason(err, str(tmp_path)) == "RuntimeError *** Error: Jacobian row = 0 for eqn iv = 1092"
    reason = flow.failure_reason("run in /x/y exited with -11 and wrote no record")
    assert reason == "exited with -11 and wrote no record"


def test_cli_flow_setup_errors(tmp_path, monkeypatch):
    assert run_cli(tmp_path, monkeypatch, jac_differs, "--gate", "jacrhs", "--arms", "jac") == 2
    os.makedirs(tmp_path / "exists")
    assert run_cli(tmp_path, monkeypatch, jac_differs, name="exists") == 2
    monkeypatch.setattr(flow, "run_spec", fake_runner(jac_differs))
    assert cli.main(["flow", "--configs", "nope", "--out", str(tmp_path / "x")]) == 2
    assert cli.main(["flow"]) == 2
    assert cli.main(["flow", "--list"]) == 0


def test_scheduler_core_budget(tmp_path, monkeypatch):
    lock = threading.Lock()
    usage = {"now": 0, "max_small": 0, "alone": []}

    def run_spec(spec, rundir, python=None):
        with lock:
            usage["now"] += spec.threads
            if spec.threads <= 6:
                usage["max_small"] = max(usage["max_small"], usage["now"])
            else:
                usage["alone"].append(usage["now"] == spec.threads)
        time.sleep(0.02)
        with lock:
            usage["now"] -= spec.threads

    monkeypatch.setattr(flow, "run_spec", run_spec)
    jobs = [flow.Job(RunSpec(preset="tebox", arm="serial", threads=1), str(tmp_path / "s{}".format(k)), 1)
            for k in range(5)]
    jobs += [flow.Job(RunSpec(preset="tebox", arm="jac", threads=t), str(tmp_path / "j{}".format(t)), 1)
             for t in (2, 4, 4, 8)]
    flow.run_jobs(jobs, cores=6, python=None, log=lambda *a: None)
    assert 2 <= usage["max_small"] <= 6  # concurrent, within the budget
    assert usage["alone"] == [True]  # the 8-thread job is wider than the budget: it runs alone
    assert all(j.error is None and j.elapsed is not None for j in jobs)


def test_scheduler_max_jobs(tmp_path, monkeypatch):
    lock = threading.Lock()
    usage = {"now": 0, "max": 0}

    def run_spec(spec, rundir, python=None):
        with lock:
            usage["now"] += 1
            usage["max"] = max(usage["max"], usage["now"])
        time.sleep(0.02)
        with lock:
            usage["now"] -= 1

    monkeypatch.setattr(flow, "run_spec", run_spec)
    jobs = [flow.Job(RunSpec(preset="tebox", arm="serial", threads=1), str(tmp_path / "s{}".format(k)), 1)
            for k in range(8)]
    flow.run_jobs(jobs, cores=14, python=None, max_jobs=3, log=lambda *a: None)
    assert usage["max"] == 3


# ---------------------------------------------------------------- the arm must have taken effect (review I1-B1)
class Rec:
    def __init__(self, prov):
        self.meta = {"provenance": prov}


@pytest.mark.parametrize("arm,threads", [("serial", 1), ("jac", 4), ("jacrhs", 2)])
def test_check_arm_ok(arm, threads):
    spec = RunSpec(preset="tebox", arm=arm, threads=threads)
    assert flow.check_arm(Rec(provenance(spec)), spec) == []


@pytest.mark.parametrize("arm,override,bad", [
    ("jac", {"ParallelJac": 0}, "ParallelJac"),             # serial build: switch set, parallel Jacobian off
    ("jacrhs", {"ParallelPandf1": 0}, "ParallelPandf1"),
    ("jac", {"Nthreads": 1}, "Nthreads"),                  # clamped by OMP_GET_MAX_THREADS
    ("jac", {"OMP_NUM_THREADS": "1"}, "OMP_NUM_THREADS"),
    ("jac", {"OMPParallelJac": 0}, "OMPParallelJac"),
    ("serial", {"ParallelJac": 1}, "ParallelJac"),
    ("serial", {"OMPParallelPandf1": 1}, "OMPParallelPandf1"),
])
def test_check_arm_problems(arm, override, bad):
    spec = RunSpec(preset="tebox", arm=arm, threads=4 if arm != "serial" else 1)
    problems = flow.check_arm(Rec(provenance(spec, **override)), spec)
    assert problems and any(p.startswith(bad) for p in problems)


def test_check_arm_missing_provenance():
    spec = RunSpec(preset="tebox", arm="jac", threads=4)
    assert flow.check_arm(Rec({}), spec)
    prov = provenance(spec)
    del prov["ParallelJac"]
    assert any("missing" in p for p in flow.check_arm(Rec(prov), spec))


def test_cli_flow_serial_build_is_error(tmp_path, monkeypatch):
    # a serial build: the OpenMP switches are set but the parallel paths never run, so OpenMP == serial
    def serial_build(spec):
        return provenance(spec, ParallelJac=0, ParallelPandf1=0)

    same = lambda s, d: [1.0, 2.0]  # noqa: E731
    assert run_cli(tmp_path, monkeypatch, same, "--arms", "jac", prov=serial_build) == 2
    data = json.loads((tmp_path / "out" / "flow.json").read_text())
    assert data["verdicts"] == {"jac": "ERROR"}
    assert "arm did not take effect: ParallelJac=0" in data["groups"][0]["errors"][0]
    assert run_cli(tmp_path, monkeypatch, same, "--gate", "none", prov=serial_build, name="o2") == 0

    def serial_ref_parallel(spec):  # the serial reference must have both switches off
        return provenance(spec, ParallelJac=1) if spec.arm == "serial" else provenance(spec)

    assert run_cli(tmp_path, monkeypatch, same, prov=serial_ref_parallel, name="o3") == 2
    g = json.loads((tmp_path / "o3" / "flow.json").read_text())["groups"][0]
    assert g["errors"][0].startswith("serial reference failed: serial arm did not take effect: ParallelJac=1")


# ---------------------------------------------------------------- harness-side vs build failures (I1-m2)
@pytest.mark.parametrize("err,harness", [
    (HarnessError("run directory /x already exists"), True),
    (HarnessError("case file missing: /x/b0p1.hdf5"), True),
    (HarnessError("expected the deck's and the caller's nksol output, found 1 block(s)"), True),
    (OSError("disk full"), True),
    (json.JSONDecodeError("Expecting value", "", 0), True),
    (RuntimeError("harness bug"), True),
    (HarnessError("run in /x exited with -11 and wrote no record (see run.log)"), False),
    (HarnessError("run in /x failed:\nTraceback\nRuntimeError:  ** overflow: SVR routine lusol0"), False),
    (HarnessError("run in /x exited with 1"), False),
    (HarnessError("run in /x failed:\nTraceback\nKeyError: 'jac_post'"), True),  # a bug in the worker
    (HarnessError("run in /x timed out after 3600 s"), False),
])
def test_classify_failure(err, harness):
    assert flow.classify_failure(err) is harness


def test_cli_flow_harness_side_failure_is_error(tmp_path, monkeypatch):
    def truncated(spec, rundir):
        if spec.arm == "jac" and spec.threads == 2:
            raise json.JSONDecodeError("Expecting value", "", 0)
        return [1.0, 2.0]

    assert run_cli(tmp_path, monkeypatch, truncated, "--gate", "jacrhs") == 0
    assert run_cli(tmp_path, monkeypatch, truncated, "--gate", "jac", name="o2") == 2
    g = json.loads((tmp_path / "o2" / "flow.json").read_text())["groups"][0]
    assert g["verdict"] == "ERROR" and g["runs"][0]["harness_error"] is True


# ---------------------------------------------------------------- input validation (I1-m1)
@pytest.mark.parametrize("extra", [["--configs", ","], ["--threads", ","], ["--arms", ",", "--gate", "none"],
                                   ["--max-jobs", "0"], ["--max-jobs", "-1"], ["--cores", "-1"], ["--cores", "0"],
                                   ["--repeats", "0"], ["--threads", "0"]])
def test_cli_flow_rejects_bad_input_before_running(tmp_path, monkeypatch, extra):
    calls = []
    monkeypatch.setattr(flow, "run_spec", fake_runner(lambda s, d: [1.0, 2.0], calls=calls))
    assert cli.main(["flow", "--configs", "tebox", "--out", str(tmp_path / "o"), "--gate", "all"] + extra) == 2
    assert calls == [] and not (tmp_path / "o").exists()


def test_cli_flow_dedupes(tmp_path, monkeypatch):
    assert run_cli(tmp_path, monkeypatch, lambda s, d: [1.0, 2.0], "--configs", "tebox,tebox",
                   "--threads", "2,2,4", "--arms", "jac,jac") == 0
    data = json.loads((tmp_path / "out" / "flow.json").read_text())
    assert [(g["config"], g["threads"]) for g in data["groups"]] == [("tebox", 2), ("tebox", 4)]
    assert data["settings"]["threads"] == [2, 4] and data["settings"]["configs"] == ["tebox"]


# ---------------------------------------------------------------- scheduler robustness (I1-m3)
def test_scheduler_survives_failing_log(tmp_path, monkeypatch):
    monkeypatch.setattr(flow, "run_spec", lambda spec, rundir, python=None: None)

    def bad_log(*args):
        raise RuntimeError("log broke")

    jobs = [flow.Job(RunSpec(preset="tebox", arm="serial", threads=1), str(tmp_path / "s{}".format(k)), 1)
            for k in range(4)]
    done = threading.Event()
    t = threading.Thread(target=lambda: (flow.run_jobs(jobs, cores=2, python=None, log=bad_log), done.set()))
    t.start()
    t.join(timeout=10)
    assert done.is_set()
    assert all(j.harness_error and "log broke" in j.error for j in jobs)


def test_scheduler_interrupt_terminates_children(tmp_path, monkeypatch):
    seen = []

    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(flow, "_schedule", interrupted)
    monkeypatch.setattr(flow, "_terminate_children", lambda: seen.append(True))
    job = flow.Job(RunSpec(preset="tebox", arm="serial", threads=1), str(tmp_path / "s"), 1)
    with pytest.raises(KeyboardInterrupt):
        flow.run_jobs([job], cores=2, python=None, log=lambda *a: None)
    assert seen == [True]
    monkeypatch.setattr(flow, "run_flow", lambda *a, **k: interrupted())
    assert cli.main(["flow", "--configs", "tebox", "--out", str(tmp_path / "o")]) == 130
