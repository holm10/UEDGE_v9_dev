"""Unit tests for ci/report.py (no UEDGE build needed): python -m pytest tests/deterministic_omp/ci"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report  # noqa: E402


def _flow(tmp, name, exit_code, groups, gated=("jac",)):
    d = tmp / name
    d.mkdir()
    flow = {"exit_code": exit_code, "gated": list(gated), "groups": groups,
            "settings": {"configs": [name], "threads": [2, 4], "repeats": 2, "itermx": 3},
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
