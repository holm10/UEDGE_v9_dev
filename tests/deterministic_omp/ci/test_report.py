"""Unit tests for ci/report.py (no UEDGE build needed): python -m pytest tests/deterministic_omp/ci"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report  # noqa: E402


def _flow(tmp, name, exit_code, groups, gated=("jac",), itermx=3):
    d = tmp / name
    d.mkdir()
    flow = {"exit_code": exit_code, "gated": list(gated), "groups": groups,
            "settings": {"configs": [name], "threads": [2, 4], "repeats": 2, "itermx": itermx},
            "timing": {"runs_wall_s": 1.0, "total_wall_s": 2.0}}
    (d / "flow.json").write_text(json.dumps(flow))
    (d / "summary.md").write_text("# OpenMP test flow\n\n| table |\n")
    return str(d)


FAIL_TE = {"config": "tebox", "arm": "jac", "threads": 2, "verdict": "FAIL", "agree_serial": "0/5",
           "first_mismatch": "jacobian:post_exmain value row te(ix=4,iy=18) col te(ix=4,iy=18) "
                             "[agreement (serial vs run0)]"}
FAIL_RHS = {"config": "tebox", "arm": "jacrhs", "threads": 2, "verdict": "FAIL", "agree_serial": "0/5",
            "first_mismatch": "yldot at te(ix=3,iy=18) [agreement (serial vs run0)]"}
PASS_NI = {"config": "full", "arm": "jac", "threads": 4, "verdict": "PASS", "first_mismatch": ""}


def test_locate():
    assert report.locate(FAIL_TE["first_mismatch"]) == ("te", "ix=4,iy=18")
    assert report.locate("yldot at ni[1](ix=0,iy=3) [x]") == ("ni[1]", "ix=0,iy=3")
    assert report.locate("failed RuntimeError") == (None, None)


def test_gated_failure_names_configuration_arm_equation_cell(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    a = _flow(tmp_path, "tebox", 1, [FAIL_TE, FAIL_RHS])
    b = _flow(tmp_path, "full", 0, [PASS_NI])
    assert report.main(["--codes", "1,0", a, b]) == 1
    out = capsys.readouterr().out
    gated = [ln for ln in out.splitlines() if ln.startswith("GATED ")]
    assert len(gated) == 1
    assert "configuration tebox, arm jac, threads 2" in gated[0]
    assert "equation te, cell (ix=4,iy=18)" in gated[0]
    assert "::error title=" in out and "::warning title=" in out
    assert "REPORT-ONLY [tebox] configuration tebox, arm jacrhs" in out
    assert "OMP CI RESULT: FAIL (exit 1)" in out
    assert (tmp_path / "summary.md").read_text().startswith("## OpenMP determinism CI: FAIL")


def test_report_only_failure_stays_green(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    step = tmp_path / "step.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step))
    a = _flow(tmp_path, "tebox", 0, [dict(FAIL_TE, verdict="PASS"), FAIL_RHS])
    assert report.main([a]) == 0
    out = capsys.readouterr().out
    assert "::" not in out
    assert "OMP CI RESULT: PASS (exit 0)" in out
    assert "PASS (set pr, gate jac, bitwise)" in step.read_text()


def test_missing_flow_json_is_an_error(tmp_path, capsys):
    d = tmp_path / "broken"
    d.mkdir()
    assert report.main(["--codes", "2", str(d)]) == 2
    assert "no readable flow.json" in capsys.readouterr().out


def test_exit_code_is_the_worst_flow(tmp_path):
    a = _flow(tmp_path, "a", 0, [])
    b = _flow(tmp_path, "b", 2, [dict(FAIL_TE, verdict="ERROR", errors=["serial reference failed"])])
    assert report.main([a, b]) == 2


def test_crash_only_group_says_so(tmp_path, capsys):
    crash = {"config": "tebox", "arm": "jac", "threads": 4, "verdict": "FAIL", "agree_serial": "0/5",
             "run_failures": ["run0: exited with -11"], "first_mismatch": "failed run0: exited with -11"}
    a = _flow(tmp_path, "tebox", 1, [crash])
    assert report.main([a]) == 1
    out = capsys.readouterr().out
    assert "configuration tebox, arm jac, threads 4: FAIL: no comparable mismatch" in out
    assert "exited with -11" in out


def test_permuted_first_mismatch_falls_back_to_a_localised_section(tmp_path, capsys):
    rep = {"kind": "agreement (serial vs run0)", "agree": False, "errors": [], "sections": {
        "jacobian:post_exmain (permuted indices)": {"mismatches": 2, "first": [
            {"kind": "value", "row": "position 12", "col": "position 13"}]},
        "yldot": {"mismatches": 1, "first": [{"iv": 4, "at": "te(ix=6,iy=18)", "a": "1", "b": "2"}]}}}
    g = {"config": "tebox", "arm": "jac", "threads": 4, "verdict": "FAIL", "agree_serial": "0/5", "reports": [rep],
         "first_mismatch": "jacobian:post_exmain (permuted indices) value row position 12 col position 13 [x]"}
    a = _flow(tmp_path, "tebox", 1, [g])
    assert report.main([a]) == 1
    out = capsys.readouterr().out
    assert "first mismatch at permuted Jacobian positions" in out
    assert "may be downstream of the defect): equation te, cell (ix=6,iy=18) [yldot]" in out
    assert "FIRST MISMATCH" not in out  # a downstream cell is never the job's headline
    g2 = dict(g, reports=[dict(rep, sections={k: v for k, v in rep["sections"].items() if k != "yldot"})])
    b = _flow(tmp_path, "tebox2", 1, [g2])
    assert report.main([b]) == 1
    assert "no cell-mapped section differs" in capsys.readouterr().out


def test_error_group_from_arm_check_is_exit_2(tmp_path, capsys):
    g = {"config": "tebox", "arm": "jac", "threads": 4, "verdict": "ERROR", "agree_serial": "0/2",
         "errors": ["agreement (serial vs run0): b: ParallelJac = 0, expected > 0 (arm jac did not take effect)"]}
    a = _flow(tmp_path, "tebox", 2, [g])
    assert report.main(["--codes", "2", a]) == 2
    out = capsys.readouterr().out
    assert "ERROR (cannot judge): agreement (serial vs run0): b: ParallelJac = 0" in out
    assert "OMP CI RESULT: ERROR (exit 2)" in out


def test_one_evaluation_group_locates_the_permuted_group_and_heads_the_report(tmp_path, capsys):
    one = {"config": "tebox", "arm": "jac", "threads": 4, "verdict": "FAIL", "agree_serial": "0/3",
           "first_mismatch": "jacobian:post_exmain value row te(ix=4,iy=20) col te(ix=3,iy=21) [x]"}
    rep = {"kind": "agreement", "agree": False, "errors": [], "sections": {
        "yldot": {"mismatches": 25, "first": [{"iv": 1, "at": "te(ix=3,iy=18)"}]}}}
    it3 = {"config": "tebox", "arm": "jac", "threads": 4, "verdict": "FAIL", "agree_serial": "0/5", "reports": [rep],
           "first_mismatch": "jacobian:post_exmain (permuted indices) value row position 1 col position 6 [x]"}
    a = _flow(tmp_path, "tebox", 1, [it3])            # --itermx 3 flow first in run order
    b = _flow(tmp_path, "tebox1", 1, [one], itermx=None)
    assert report.main([a, b]) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == ("FIRST MISMATCH: configuration tebox, arm jac, threads 4, equation te, "
                                   "cell (ix=4,iy=20) (flow tebox1)")
    assert "located by the one-evaluation group [tebox1]: equation te, cell (ix=4,iy=20)" in out
    assert "ix=3,iy=18" not in out


def test_too_few_newton_iterations_in_the_serial_reference_is_exit_2(tmp_path, capsys):
    g = dict(PASS_NI, config="full", serial={"rundir": "full/serial"})
    a = _flow(tmp_path, "full", 0, [g])
    rd = tmp_path / "full" / "full" / "serial"
    rd.mkdir(parents=True)
    (rd / "record.json").write_text(json.dumps({"iterations": [{"iter": 0}, {"iter": 1}]}))
    assert report.main([a]) == 2
    assert "made 1 Newton iteration(s), fewer than --itermx 3" in capsys.readouterr().out
    (rd / "record.json").write_text(json.dumps({"iterations": [{"iter": k} for k in range(4)]}))
    assert report.main([a]) == 0
