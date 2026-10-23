"""Unit tests for ci/report.py (no UEDGE build needed): python -m pytest tests/deterministic_omp/ci"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report  # noqa: E402


def _bound_for(groups, tol=1e-6, run_pass=True, worst=0.0):
    """A bound.json body with a judged entry for every run of every jac group (as ci/jac_bound.py writes)."""
    out = {"tol": tol, "matrix": "post_exmain", "exit_code": 0 if run_pass else 1, "groups": {}}
    for g in groups:
        if g.get("arm") != "jac":
            continue
        runs = [os.path.basename(r["rundir"]) for r in g.get("runs", [])] or ["run0"]
        out["groups"]["{}/jac_t{}".format(g["config"], g["threads"])] = {"error": None, "runs": {
            r: {"pass": run_pass, "worst_ratio": 1.0, "worst_dev": worst, "over": 0 if run_pass else 1,
                "differ": 0, "permuted": False, "raw": [], "problems": [] if run_pass else
                ["post_exmain: 1 entries exceed 1e-06 x serial row max (worst 3.000e-06; 1 entries differ)"]}
            for r in runs}}
    return out


def _flow(tmp, name, exit_code, groups, gated=("jac",), itermx=3, bound="auto", ppp=None):
    d = tmp / name
    d.mkdir()
    flow = {"exit_code": exit_code, "gated": list(gated), "groups": groups,
            "settings": {"configs": [name], "threads": [2, 4], "repeats": 2, "itermx": itermx, "ppp": ppp or {}},
            "timing": {"runs_wall_s": 1.0, "total_wall_s": 2.0}}
    (d / "flow.json").write_text(json.dumps(flow))
    (d / "summary.md").write_text("# OpenMP test flow\n\n| table |\n")
    if bound == "auto":
        bound = _bound_for(groups)
    if bound is not None:
        (d / "bound.json").write_text(json.dumps(bound))
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
    assert "made 1 Newton iteration(s), fewer than --itermx 3\n" in capsys.readouterr().out
    # a record that says why nksol stopped (AIUE-169) gets it in the message
    (rd / "record.json").write_text(json.dumps({"iterations": [{"iter": 0}], "iterm": 3}))
    assert report.main([a]) == 2
    assert "made 0 Newton iteration(s), fewer than --itermx 3 (nksol iterm=3)" in capsys.readouterr().out
    # an overshoot past itermx (nkstop's stale-preconditioner path) is not exactly N either
    (rd / "record.json").write_text(json.dumps({"iterations": [{"iter": k} for k in range(5)], "iterm": 2}))
    assert report.main([a]) == 2
    assert "made 4 Newton iteration(s), more than --itermx 3 (nksol iterm=2)" in capsys.readouterr().out
    (rd / "record.json").write_text(json.dumps({"iterations": [{"iter": k} for k in range(4)], "iterm": 4}))
    assert report.main([a]) == 0


# ---- AIUE-57 rework: C1 bound backstop, tolerance mode, common-block code, chunk counts ----

RUNS3 = [{"rundir": "tebox/jac_t4/run{}".format(k)} for k in range(3)]
JAC_ONLY = {"config": "tebox", "arm": "jac", "threads": 4, "verdict": "FAIL", "agree_serial": "0/3",
            "deterministic": True, "failing_sections": ["jacobian:post_exmain"], "runs": RUNS3,
            "first_mismatch": "jacobian:post_exmain value row te(ix=4,iy=20) col te(ix=3,iy=21) [x]"}
PASS_T4 = {"config": "tebox", "arm": "jac", "threads": 4, "verdict": "PASS", "agree_serial": "3/3",
           "deterministic": True, "failing_sections": [], "runs": RUNS3, "first_mismatch": ""}


def _tol(*paths, tol="1e-6", extra=()):
    return report.main(["--gate-mode", "tolerance", "--tol", tol] + list(extra) + list(paths))


def test_bitwise_failure_line_carries_the_bound_result(tmp_path, capsys):
    a = _flow(tmp_path, "tebox1", 1, [JAC_ONLY], itermx=None, bound=_bound_for([JAC_ONLY], worst=5.6e-10))
    assert report.main([a]) == 1
    out = capsys.readouterr().out
    assert "C1 bound (tol 1e-06): within, worst |a-b|/base 5.6e-10" in out
    assert "OMP CI RESULT: FAIL (exit 1)" in out


def test_bound_fail_on_a_bitwise_pass_group_is_a_gated_failure(tmp_path, capsys):
    a = _flow(tmp_path, "tebox1", 0, [PASS_T4], itermx=None, bound=_bound_for([PASS_T4], run_pass=False))
    assert report.main([a]) == 1
    out = capsys.readouterr().out
    assert "FAIL: the flow passed bitwise, but C1 bound (tol 1e-06): EXCEEDED in 3/3 runs" in out
    assert "OMP CI RESULT: FAIL (exit 1)" in out


def test_tolerance_accepts_jacobian_only_deterministic_within_bound(tmp_path, capsys):
    a = _flow(tmp_path, "tebox1", 1, [JAC_ONLY], itermx=None)
    assert _tol(a, extra=["--codes", "1"]) == 0
    out = capsys.readouterr().out
    assert "TOLERATED [tebox1] configuration tebox, arm jac, threads 4: PASS (within tolerance 1e-06)" in out
    assert "GATED" not in out and "FIRST MISMATCH" not in out
    assert "OMP CI RESULT: PASS (exit 0)" in out
    assert (tmp_path / "summary.md").read_text().startswith(
        "## OpenMP determinism CI: PASS (set pr, gate jac, tolerance 1e-06)")


def test_tolerance_i_bound_fail_stays_fail(tmp_path, capsys):
    a = _flow(tmp_path, "tebox1", 1, [JAC_ONLY], itermx=None, bound=_bound_for([JAC_ONLY], run_pass=False))
    assert _tol(a) == 1
    out = capsys.readouterr().out
    assert "EXCEEDED" in out and "not within tolerance 1e-06 (C1 bound)" in out
    assert "OMP CI RESULT: FAIL (exit 1)" in out


def test_tolerance_ii_missing_bound_is_exit_2_never_a_pass(tmp_path, capsys):
    a = _flow(tmp_path, "nob", 1, [JAC_ONLY], itermx=None, bound=None)
    assert _tol(a) == 2
    assert "no readable bound.json" in capsys.readouterr().out
    b = _flow(tmp_path, "nogroup", 1, [JAC_ONLY], itermx=None, bound={"tol": 1e-6, "groups": {}})
    assert _tol(b) == 2
    assert "no entry for group tebox/jac_t4" in capsys.readouterr().out
    partial = _bound_for([JAC_ONLY])
    del partial["groups"]["tebox/jac_t4"]["runs"]["run2"]
    c = _flow(tmp_path, "norun", 1, [JAC_ONLY], itermx=None, bound=partial)
    assert _tol(c) == 2
    assert "no entry for run2 of group tebox/jac_t4" in capsys.readouterr().out


def test_missing_bound_is_exit_2_in_bitwise_mode_too(tmp_path):
    a = _flow(tmp_path, "nob", 0, [PASS_T4], itermx=None, bound=None)
    assert report.main([a]) == 2


def test_tolerance_rejects_non_jacobian_sections_nondeterminism_and_failed_runs(tmp_path, capsys):
    yld = dict(JAC_ONLY, failing_sections=["jacobian:post_exmain (permuted indices)", "yldot", "fnrm_final"])
    nondet = dict(JAC_ONLY, deterministic=False)
    crashed = dict(JAC_ONLY, run_failures=["run1: exited with -11"])
    for name, g in (("yld", yld), ("nondet", nondet), ("crash", crashed)):
        a = _flow(tmp_path, name, 1, [g], itermx=None)
        assert _tol(a) == 1, name
        assert "a non-Jacobian section differs, a run failed or the group is not deterministic" in \
            capsys.readouterr().out


def test_tolerance_keeps_flow_errors(tmp_path):
    err = dict(JAC_ONLY, verdict="ERROR", errors=["serial reference failed"])
    a = _flow(tmp_path, "e", 2, [err], itermx=None)
    assert _tol(a, extra=["--codes", "2"]) == 2


def test_bound_tol_mismatch_is_exit_2(tmp_path, capsys):
    a = _flow(tmp_path, "t", 1, [JAC_ONLY], itermx=None)  # bound.json computed at 1e-6
    assert _tol(a, tol="1e-7") == 2
    assert "differs from --tol 1e-07" in capsys.readouterr().out


def test_bound_exit_2_is_exit_2(tmp_path, capsys):
    a = _flow(tmp_path, "t", 0, [PASS_T4], itermx=None)
    assert report.main(["--bound-codes", "0,2", a]) == 2
    assert "ci/jac_bound.py exit codes 0,2" in capsys.readouterr().out


def test_common_block_fail_with_passing_flows_is_a_red_job(tmp_path, capsys):
    a = _flow(tmp_path, "t", 0, [PASS_T4], itermx=None)
    assert report.main(["--common-code", "1", "--codes", "0", a]) == 1
    out = capsys.readouterr().out
    assert "GATED [common-block] FAIL: the /ompcommonscalarcopy/ check (ci/common_check.py) failed" in out
    assert "OMP CI RESULT: FAIL (exit 1)" in out
    assert (tmp_path / "summary.md").read_text().startswith("## OpenMP determinism CI: FAIL")
    assert report.main(["--common-code", "2", a]) == 2
    capsys.readouterr()
    assert report.main(["--common-code", "0", a]) == 0
    assert "COMMON-BLOCK PASS" in capsys.readouterr().out
    assert report.main([a]) == 0
    assert "COMMON-BLOCK skipped" in capsys.readouterr().out


def test_chunk_counts_from_run_logs(tmp_path, capsys):
    a = _flow(tmp_path, "tebox1", 0, [PASS_T4], itermx=None, ppp={"OMPJacMinChunkLen": 1, "OMPJacVerbose": 1})
    for k in range(3):
        rd = tmp_path / "tebox1" / "tebox" / "jac_t4" / "run{}".format(k)
        rd.mkdir(parents=True)
        if k < 2:
            (rd / "run.log").write_text("*OMPJac* Nthreads:   4 NchunksJac:    25 nnzmxperchunk:   36 neq:    25\n")
    assert report.main([a]) == 0
    out = capsys.readouterr().out
    assert "CHUNKS [tebox1] configuration tebox, arm jac, threads 4: NchunksJac 25 (2 of 3 runs printed it)" in out


def test_tolerance_mode_does_not_apply_to_itermx_flows(tmp_path, capsys):
    a = _flow(tmp_path, "tebox", 1, [JAC_ONLY], itermx=3)  # Jacobian-only, deterministic, bound within
    assert _tol(a) == 1
    out = capsys.readouterr().out
    assert "tolerance mode applies to one-evaluation flows only" in out and "TOLERATED" not in out


def test_bound_line_without_te_rows_says_na(tmp_path, capsys):
    b = _bound_for([PASS_T4], run_pass=False)
    for r in b["groups"]["tebox/jac_t4"]["runs"].values():
        r["worst_ratio"] = None
    a = _flow(tmp_path, "t", 0, [PASS_T4], itermx=None, bound=b)
    assert report.main([a]) == 1
    assert "magnitude ratio n/a (no Te rows)" in capsys.readouterr().out
