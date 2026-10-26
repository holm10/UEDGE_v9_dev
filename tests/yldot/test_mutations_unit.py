"""Unit tests of the mutation set and run_mutations.py (epic AIUE-9, PRD sections 7.8 and 7.11 (c); AIUE-90).

The committed patches: every header is valid, every diff changes the one line its Source names, every patch applies
to this tree (git apply --check; owner, 2026-10-22, AIUE-90 Q7: a change to a mutated line fails here until the patch
is refreshed), and the set has PRD 7.8's composition. Then the verdict and the four coverage-matrix gates on synthetic
results. No build, no uedge import; the families and blocks are read from the stored references.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SUITE / "tools"))

import run_mutations as rm  # noqa: E402

ROOT = SUITE.parents[1]
PATCHES = rm.mutation_paths()


@pytest.fixture(scope="module")
def stores():
    return rm.store_facts(rm.referenced())


def test_set_is_valid(stores):
    """Every header and diff, against the stored references, and the set's composition (27; PRD 7.8)."""
    ms = rm.load_set(stores=stores)
    assert len(ms) == 27


@pytest.mark.parametrize("patch", PATCHES, ids=[p.stem for p in PATCHES])
def test_patch_applies(patch):
    """The patch applies to this tree's source (git apply skips the header)."""
    r = subprocess.run(["git", "-C", str(ROOT), "apply", "--check", str(patch)], capture_output=True, text=True)
    assert r.returncode == 0, "{} no longer applies: refresh it at the mutated line ({})".format(
        patch.name, r.stderr.strip())


# ---------------------------------------------------------------- parsing and checks on synthetic patches

DIFF = """diff --git a/bbb/f.m b/bbb/f.m
index 1111111..2222222 100644
--- a/bbb/f.m
+++ b/bbb/f.m
@@ -10,3 +10,3 @@ subroutine x
       a = 1
-      b = c - d
+      b = c + d
       e = 2
"""


def header(**over):
    keys = {"Mutation": "m", "Kind": "physics", "Equation": "te", "Fault": "sign", "Check": "yldot",
            "Configs": "steady, timestep", "Blocks": "d_only: primary te[1]\n ortho: primary te[1]",
            "Intermediate": "resee", "Families": "d_only, ortho", "Source": "bbb/f.m:11 (at 8a67572)",
            "Description": "a test"}
    keys.update(over)
    return "\n".join("{}: {}".format(k, v) for k, v in keys.items() if v is not None) + "\n\n"


def write(tmp_path, text, name="m"):
    p = tmp_path / "{}.patch".format(name)
    p.write_text(text)
    return rm.load(p)


def test_synthetic_patch_is_valid(tmp_path, stores):
    m = write(tmp_path, header() + DIFF)
    assert rm.problems(m, stores) == []
    assert m.blocks == {"d_only": {"primary": ["te[1]"], "coupled": []}, "ortho": {"primary": ["te[1]"],
                                                                               "coupled": []}}
    assert rm.diff_line(DIFF) == ("bbb/f.m", 11)


@pytest.mark.parametrize("text, match", [
    ("Mutation: m\n" + DIFF, "no blank line"),
    (" continued\n\n" + DIFF, "continuation"),
    ("mutation: m\n\n" + DIFF, "Key: value"),
    ("Mutation: m\nMutation: n\n\n" + DIFF, "twice"),
])
def test_malformed_header(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        write(tmp_path, text)


@pytest.mark.parametrize("over, match", [
    ({"Check": "flag difference"}, "caught by 'yldot'"),
    ({"Equation": "all"}, "range and flag-gating only"),
    ({"Fault": "typo"}, "Fault"),
    ({"Configs": "steady, transient"}, "Configs"),
    ({"Families": "d_only, nosuch"}, "no family nosuch"),
    ({"Families": "ortho, d_only"}, "same order"),
    ({"Blocks": "d_only: primary te[1]\n ortho: primary ng[2]"}, "not a block of the family's reference"),
    ({"Blocks": "d_only: primary te1\n ortho: primary te[1]"}, "not eq\\[species\\]"),
    ({"Blocks": "d_only: primary te[1]; coupled te[1]\n ortho: primary te[1]"}, "both primary and coupled"),
    ({"Blocks": None}, "Blocks missing"),
    ({"Cells": "d_only: ti[1] (3,1)"}, "not a primary block"),
    ({"Pending": "soon"}, "Pending"),
    ({"Source": "bbb/f.m:12 (at 8a67572)"}, "the diff changes bbb/f.m:11"),
    ({"Mutation": "other"}, "not the file's stem"),
])
def test_problems_found(tmp_path, stores, over, match):
    m = write(tmp_path, header(**over) + DIFF)
    found = rm.problems(m, stores)
    assert any(re.search(match, p) for p in found), found


def test_inner_loop_family_is_smallest(tmp_path, stores):
    m = write(tmp_path, header(Families="slab_phi, d_only",
                               Blocks="slab_phi: primary te[1]\n d_only: primary te[1]") + DIFF)
    assert any("inner-loop family slab_phi" in p for p in rm.problems(m, stores))


@pytest.mark.parametrize("diff, match", [
    (DIFF.replace("       e = 2\n", "-      e = 2\n"), "remove one line"),
    (DIFF + DIFF.replace("bbb/f.m", "bbb/g.m"), "exactly one file"),
    (DIFF + "@@ -20,1 +20,1 @@\n-x\n+y\n", "exactly one hunk"),
])
def test_diff_must_be_single_line(diff, match):
    with pytest.raises(ValueError, match=match):
        rm.diff_line(diff)


def test_composition_detects_a_gap(stores):
    ms = rm.load_set(stores=stores)
    assert rm.composition(ms) == []
    without = [m for m in ms if not (m.equation == "phi" and m.fault == "sign")]
    found = rm.composition(without)
    assert any("kinds" in p for p in found) and any(p.startswith("phi:") for p in found), found


# ---------------------------------------------------------------- verdicts


def mut(tmp_path, **over):
    return write(tmp_path, header(**over) + DIFF)


def result(spec, crash=None):
    """{config: child result}; spec: {(config, part): {block: [[ix, iy], ...]}}."""
    out = {}
    for config in rm.CONFIGS:
        if crash == config:
            out[config] = {"status": "crash", "message": "child exited"}
            continue
        parts = {}
        for part in rm.PARTS:
            cells = spec.get((config, part), {})
            n = sum(len(c) for c in cells.values())
            parts[part] = {"ok": n == 0, "n_fail": n, "max_ratio": 10.0 if n else 0.0, "cells": cells}
        out[config] = {"status": "ok", "parts": parts, "intermediate": "resee" if spec else None}
    return out


TE = {"te[1]": [[3, 1], [4, 2]]}
BOTH = {("steady", "yldot"): TE, ("timestep", "yldot"): TE}


@pytest.mark.parametrize("over, family, spec, crash, want, problem", [
    ({}, "d_only", BOTH, None, "expected", None),
    ({}, "d_only", {}, None, "missed", "nothing fired"),
    ({}, "d_only", {("steady", "yldot"): TE}, None, "unexpected", "timestep yldot: nothing fired"),
    ({}, "d_only", {**BOTH, ("steady", "yldot"): {**TE, "ti[1]": [[3, 1]]}}, None, "unexpected",
     "outside primary and coupled"),
    ({"Blocks": "d_only: primary te[1]; coupled ti[1]\n ortho: primary te[1]"}, "d_only",
     {**BOTH, ("steady", "yldot"): {**TE, "ti[1]": [[3, 1]]}}, None, "expected", None),
    ({"Blocks": "d_only: primary te[1], ti[1]\n ortho: primary te[1]"}, "d_only", BOTH, None, "unexpected",
     "did not fire"),
    ({}, "d_only", {**BOTH, ("timestep", "flag difference"): TE}, None, "unexpected", "not the expected check"),
    ({"Configs": "timestep"}, "d_only", BOTH, None, "unexpected", "not the expected check or configuration"),
    ({"Cells": "d_only: te[1] (3,1)"}, "d_only", BOTH, None, "unexpected", "outside"),
    ({"Cells": "d_only: te[1] (3,1), (4,2)"}, "d_only", BOTH, None, "expected", None),
    ({}, "d_c", {}, None, "quiet", None),
    ({}, "d_c", BOTH, None, "unexpected", "inactive"),
    ({"Pending": "AIUE-100 (locality check)"}, "d_only", BOTH, None, "unexpected", "pending"),
    ({"Pending": "AIUE-100 (locality check)"}, "d_only", {}, None, "quiet", None),
    ({}, "d_only", BOTH, "timestep", "crash", "timestep: crash"),
])
def test_verdict(tmp_path, over, family, spec, crash, want, problem):
    v = rm.verdict(mut(tmp_path, **over), family, result(spec, crash))
    assert v["verdict"] == want, v
    if problem:
        assert any(problem in p for p in v["problems"]), v


def test_intermediate_exception(tmp_path, stores):
    """An owner-approved per-family exception replaces the expected intermediate for that family only."""
    m = mut(tmp_path, Intermediate="resee; ortho: none (owner, 2026-10-22, below the localization threshold)")
    assert (m.intermediate, m.intermediate_by) == ("resee", {"ortho": "none"})
    assert rm.problems(m, stores) == []
    quiet = result(BOTH)
    for config in rm.CONFIGS:
        quiet[config]["intermediate"] = None
    assert rm.verdict(m, "ortho", quiet)["flags"] == []
    assert len(rm.verdict(m, "d_only", quiet)["flags"]) == 2
    assert len(rm.verdict(m, "ortho", result(BOTH))["flags"]) == 2  # named although none was expected
    bad = mut(tmp_path, Intermediate="resee; d_c: none (owner, 2026-10-22, x)")
    assert any("not in Families" in p for p in rm.problems(bad, stores))
    with pytest.raises(ValueError, match="Intermediate exception"):
        mut(tmp_path, Intermediate="resee; ortho: none")


def test_verdict_flags(tmp_path):
    m = mut(tmp_path, Intermediate="resei")
    v = rm.verdict(m, "d_only", result(BOTH), junit={"steady": True, "timestep": False})
    assert v["verdict"] == "expected"
    assert any("first differing intermediate resee, expected resei" in f for f in v["flags"]), v
    assert any("test_default[d_only-timestep] passed while the check fired" in f for f in v["flags"]), v


# ---------------------------------------------------------------- gates


def matrix(entries, families=("d_only", "d_mols")):
    """entries: {mutation: (equation, pending, {family: verdict})}; primary blocks <eq>[1] on every family."""
    muts = {}
    for name, (eq, pending, verdicts) in entries.items():
        blocks = {f: {"primary": ["{}[1]".format(eq)], "coupled": []} for f in verdicts}
        muts[name] = {"header": {"equation": eq, "pending": pending, "blocks": blocks},
                      "results": {f: {"verdict": v, "problems": [], "flags": []} for f, v in verdicts.items()}}
    return {"families": {f: {"neq": 1, "equations": ["te", "ni"]} for f in families}, "mutations": muts}


GOOD = {"a": ("te", None, {"d_only": "expected", "d_mols": "expected"}),
        "b": ("ni", None, {"d_only": "expected", "d_mols": "quiet"}),
        "c": ("tg", "AIUE-92 (x)", {"d_only": "quiet", "d_mols": "quiet"})}


def failing(m):
    return [name.split()[0] for name, ok, _ in rm.gates(m) if not ok]


def test_gates_pass():
    assert failing(matrix(GOOD)) == []
    assert rm.exit_code(matrix(GOOD)) == 0


@pytest.mark.parametrize("change, gate", [
    ({"a": ("te", None, {"d_only": "missed", "d_mols": "missed"})}, "G1"),
    ({"b": ("ni", None, {"d_only": "expected", "d_mols": "unexpected"})}, "G2"),
    ({"c": ("tg", "AIUE-92 (x)", {"d_only": "unexpected", "d_mols": "quiet"})}, "G2"),
    ({"b": ("ni", None, {"d_only": "expected", "d_mols": "not run"})}, "G2"),
    ({"b": ("ni", None, {"d_only": "quiet", "d_mols": "quiet"})}, "G3"),
    ({"a": ("te", None, {"d_only": "expected", "d_mols": "quiet"})}, "G4"),
])
def test_gates_fail(change, gate):
    m = matrix({**GOOD, **change})
    assert gate in failing(m), rm.gates(m)
    assert rm.exit_code(m) == 3


def test_g3_needs_a_mutation_of_the_equation():
    """A mutation of another equation (e.g. the timestep flag-gating, primary in every block) does not satisfy G3."""
    m = matrix({**GOOD, "b": ("ni", None, {"d_only": "quiet", "d_mols": "quiet"}),
                "g": ("all", None, {"d_only": "expected", "d_mols": "expected"})})
    m["mutations"]["g"]["header"]["blocks"] = {f: {"primary": ["ni[1]", "te[1]"], "coupled": []}
                                               for f in ("d_only", "d_mols")}
    assert "G3" in failing(m), rm.gates(m)


def test_partial_run_skips_g3_g4():
    m = matrix({"a": ("te", None, {"d_only": "expected", "d_mols": "quiet"})})
    assert sorted(failing(m)) == ["G3", "G4"]
    m["partial"] = True
    assert failing(m) == []
    assert all("not evaluated" in d for name, _, d in rm.gates(m) if name.startswith(("G3", "G4")))


JUNIT = """<testsuites><testsuite>
<testcase classname="t" name="test_default[d_only-steady]"><failure message="x"/></testcase>
<testcase classname="t" name="test_default[d_only-timestep]"/>
<testcase classname="t" name="test_default[ortho-steady]"><skipped message="s"/></testcase>
<testcase classname="t" name="test_timestep_exercised[d_only]"/>
{}</testsuite></testsuites>"""


def test_parse_junit(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(JUNIT.format(""))
    assert rm.parse_junit(p, ["d_only", "ortho"]) == {"d_only": {"steady": True, "timestep": False}, "ortho": {}}
    p.write_text(JUNIT.format('<testcase classname="t" name="test_default[ortho-steady]"/>'))
    with pytest.raises(rm.Stop, match="collected twice"):
        rm.parse_junit(p, ["d_only", "ortho"])


RANGE = {"Kind": "range", "Equation": "all", "Fault": "loop bound", "Check": "locality", "Configs": "steady",
         "Intermediate": "none", "Blocks": "d_only: primary te[1]\n ortho: primary te[1]"}
LOC = {("steady", "locality"): TE}


@pytest.mark.parametrize("spec, junit_loc, want, problem", [
    (LOC, True, "expected", None),
    ({}, False, "missed", "steady locality: nothing fired"),
    ({**LOC, ("steady", "yldot"): TE}, True, "unexpected", "not the expected check"),  # a range mutation moves yldot
    ({("steady", "locality"): {**TE, "ni[1]": [[2, 1]]}}, True, "unexpected", "outside primary and coupled"),
])
def test_range_verdict(tmp_path, spec, junit_loc, want, problem):
    v = rm.verdict(mut(tmp_path, **RANGE), "d_only", result(spec), junit={"steady": False, "timestep": False},
                   junit_loc=junit_loc)
    assert v["verdict"] == want, v
    assert not v["flags"] or want != "expected", v
    if problem:
        assert any(problem in p for p in v["problems"]), v


def test_range_verdict_flags_test_locality(tmp_path):
    """test_locality.py is the cross-check of the locality part; test_default.py ignores it."""
    v = rm.verdict(mut(tmp_path, **RANGE), "d_only", result(LOC), junit={"steady": False, "timestep": False},
                   junit_loc=False)
    assert v["flags"] == ["test_locality[d_only] passed while the check fired"], v
    v = rm.verdict(mut(tmp_path, **RANGE), "d_only", result({}), junit={"steady": False, "timestep": False},
                   junit_loc=True)
    assert "test_locality[d_only] failed while the check passed" in v["flags"], v


JUNIT_LOC = """<testsuites><testsuite>
<testcase classname="t" name="test_locality[d_only]"><failure message="x"/></testcase>
<testcase classname="t" name="test_locality[ortho]"/>
<testcase classname="t" name="test_locality_configured"/>
<testcase classname="t" name="test_compare_pattern_band[x]"/>
{}</testsuite></testsuites>"""


def test_parse_junit_locality(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(JUNIT_LOC.format(""))
    assert rm.parse_junit_locality(p, ["d_only", "ortho"]) == {"d_only": True, "ortho": False}
    with pytest.raises(rm.Stop, match="no case for"):
        rm.parse_junit_locality(p, ["d_only", "d_c"])
    p.write_text(JUNIT_LOC.format('<testcase classname="t" name="test_locality[ortho]"/>'))
    with pytest.raises(rm.Stop, match="collected twice"):
        rm.parse_junit_locality(p, ["d_only", "ortho"])
    p.write_text(JUNIT_LOC.replace('name="test_locality[ortho]"/>', 'name="test_locality[ortho]"><skipped/>'
                                   '</testcase>').format(""))
    with pytest.raises(rm.Stop, match="skipped"):
        rm.parse_junit_locality(p, ["d_only", "ortho"])


def test_skipped_test_default_is_flagged(tmp_path):
    v = rm.verdict(mut(tmp_path), "d_only", result(BOTH), junit={"steady": True})
    assert any("test_default[d_only-timestep]" in f for f in v["flags"]), v


def test_gate_flag_fails_g2():
    m = matrix(GOOD)
    m["mutations"]["a"]["results"]["d_only"]["flags"] = ["first differing intermediate x"]
    assert failing(m) == ["G2"]


def test_locality_part_not_run_without_locality(monkeypatch):
    """AIUE-92: a family without [locality] has no locality part; it never stops the run. Every family has one
    since AIUE-101, so a family without is faked here."""
    from yldot.harness import locality as L

    assert rm.has_locality("d_only") and rm.has_locality("large_dd2c")
    monkeypatch.setattr(L, "load_config", lambda fdir: None)
    assert not rm.has_locality("large_dd2c")
    assert rm.locality_part(None, "large_dd2c", None, None) == (None, None)


# ---------------------------------------------------------------- a mutation checked through a stored variant (AIUE-96)

VARIANT = {"Kind": "flag-gating", "Equation": "ni", "Fault": "gating", "Check": "flag difference", "Configs": "steady",
           "Intermediate": "none", "Blocks": "d_only: primary ni[1], te[1]", "Families": "d_only",
           "Variant": "bbb.v"}
ENTRY = {"class": "SENSITIVE", "config": "steady", "jflag_block_l2": {"ni[1] core": 1.0, "te[1] sol": 2.0}}


def test_variant_header(tmp_path, stores):
    m = mut(tmp_path, **VARIANT)
    assert m.variant == "bbb.v" and m.summary()["variant"] == "bbb.v"
    assert rm.problems(m, stores) == []
    assert rm.variant_problems(m, {"bbb.v"}, {"d_only": {"bbb.v": ENTRY}}) == []
    assert rm.variant_problems(mut(tmp_path), None, None) == []


@pytest.mark.parametrize("plan_ids, entry, over, match", [
    (set(), ENTRY, {}, "not a variant of the inventory"),
    ({"bbb.v"}, None, {}, "d_only stores no such variant"),
    ({"bbb.v"}, dict(ENTRY, **{"class": "INERT"}), {}, "stores it as INERT"),
    ({"bbb.v"}, dict(ENTRY, jflag_block_l2={}), {}, "need SENSITIVE with some"),
    ({"bbb.v"}, ENTRY, {"Configs": "steady, timestep"}, "checked in steady only"),
    ({"bbb.v"}, ENTRY, {"Blocks": "d_only: primary ni[1], up[1]"}, r"primary \['up\[1\]'\] outside"),
])
def test_variant_problems(tmp_path, plan_ids, entry, over, match):
    m = mut(tmp_path, **{**VARIANT, **over})
    found = rm.variant_problems(m, plan_ids, {"d_only": {} if entry is None else {"bbb.v": entry}})
    assert any(re.search(match, p) for p in found), found


def test_variant_needs_a_full_store(tmp_path):
    """AIUE-99: variant_child compares dense vectors, so a Variant in a sketch-store family is refused."""
    m = mut(tmp_path, **VARIANT)
    assert rm.variant_problems(m, {"bbb.v"}, {"d_only": {"bbb.v": ENTRY}}, {"d_only": "full"}) == []
    found = rm.variant_problems(m, {"bbb.v"}, {"d_only": {"bbb.v": ENTRY}}, {"d_only": "sketch"})
    assert found == ["Variant bbb.v: d_only is a sketch store; a Variant mutation needs a full store"]


def test_ishosor_through_its_variant():
    """The committed ishosor mutation is checked through d_only's stored bbb.ishosor variant (AIUE-96 D7)."""
    m = rm.load(rm.MUTATIONS / "ishosor_flag_gating.patch")
    assert (m.variant, m.families, m.pending) == ("bbb.ishosor", ["d_only"], None)


def variant_result(spec):
    """The child's result for a variant in its configuration only (steady)."""
    return {"steady": result(spec)["steady"]}


FLAG = {("steady", "flag difference"): {"ni[1]": [[3, 1]], "te[1]": [[3, 1]]}}


@pytest.mark.parametrize("spec, junit, want, flag", [
    (FLAG, {"steady": True}, "expected", None),
    ({}, {"steady": False}, "missed", None),
    ({("steady", "flag difference"): {"ni[1]": [[3, 1]]}}, {"steady": True}, "unexpected", None),
    (FLAG, {"steady": False}, "expected", "test_sensitive[d_only-bbb.v] passed while the check fired"),
    (FLAG, {}, "expected", "test_sensitive[d_only-bbb.v] passed while the check fired"),
])
def test_variant_verdict(tmp_path, spec, junit, want, flag):
    """Only the variant's configuration ran: no timestep entry is asked of the cross-check."""
    v = rm.verdict(mut(tmp_path, **VARIANT), "d_only", variant_result(spec), junit=junit)
    assert v["verdict"] == want, v
    assert v["flags"] == ([flag] if flag else []), v


JUNIT_VARIANT = """<testsuites><testsuite>
<testcase classname="t" name="test_sensitive[d_only-bbb.ishosor]"><failure message="x"/></testcase>
<testcase classname="t" name="test_sensitive[d_only-bbb.ishosor=1]"/>
<testcase classname="t" name="test_inert[d_only-bbb.ishosor]"/>
{}</testsuite></testsuites>"""


def test_parse_junit_variant(tmp_path):
    p = tmp_path / "j.xml"
    p.write_text(JUNIT_VARIANT.format(""))
    assert rm.parse_junit_variant(p, ["d_only"], "bbb.ishosor") == {"d_only": {"steady": True}}
    p.write_text(JUNIT_VARIANT.format('<testcase classname="t" name="test_sensitive[d_only-bbb.ishosor]"/>'))
    with pytest.raises(rm.Stop, match="collected twice"):
        rm.parse_junit_variant(p, ["d_only"], "bbb.ishosor")
