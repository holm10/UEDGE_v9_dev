"""Inventory tests of the yldot families (PRD section 6; AIUE-83 adds index truth, AIUE-93 adds the input inventory,
AIUE-96 the manifest and source checks).

Per family, from a live evaluation (intake configuration): the idx* inverse is a bijection onto 1..neq that agrees
with igyl, the owner-confirmed [regions] of family.toml fit the live grid and give their recorded cell counts, and
a deliberately permuted map is rejected. Every diagnostic array is placed for the first-difference report.

From the git-tracked files alone (PRD sections 6, 7.2 and 7.6): every manifest holds exactly the variants of the
inventory (variants.plan()), with no stale entry, the inventory's EXCLUDED ones as EXCLUDED, an owner family's too
since its sweep (AIUE-99; owner, 2026-10-24, Q1: D6's "or none" is gone); every EXCLUDED, MARGINAL
and INVALID entry has a reason; every tagged input the harness itself sets (harness/state.py) is EXCLUDED; every
input.py is in normal form (it never sets restart, restores a state or runs exmain); and no file under tests/yldot
skips or xfails a test. Each check is shown failing on a planted defect.
"""
import ast
import copy

import numpy as np
import pytest

from yldot.harness import FAMILIES, INTAKE, inputs, variants
from yldot.harness import manifest as mf
from yldot.harness.compare import (PANDF_ORDER, REGIONS, UNORDERED, IndexTruthError, index_map, load_regions,
                                   region_cells)

FAMILY_NAMES = sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())
SUITE = FAMILIES.parent
STATE = SUITE / "harness" / "state.py"
NEEDS_REASON = ("EXCLUDED", "MARGINAL", "INVALID")
BANNED = {"pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail", "pytest.skip", "pytest.xfail",
          "pytest.importorskip", "unittest.skip", "unittest.skipIf", "unittest.skipUnless", "unittest.expectedFailure"}
NOT_IN_INPUT = ("hdf5_restore", "exmain")  # input.py never loads a state or runs the solver (PRD section 6)


@pytest.fixture(scope="module")
def intake(runner):
    cache = {}

    def get(family):
        if family not in cache:
            res = runner.evaluate(family, config=INTAKE)
            assert res.ok, "{}: {} {}\n{}".format(family, res.status, res.message, res.log_tail)
            cache[family] = res.data
        return cache[family]
    return get


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_index_truth(intake, family):
    data = intake(family)
    regions = load_regions(family)
    imap = index_map(data, regions)
    assert imap.neq == data["neq"]
    counts = region_cells(regions)
    assert counts == {r: int(regions["cells"].get(r, 0)) for r in REGIONS}
    rows_per_region = {r: int((imap.region == r).sum()) for r in REGIONS}
    assert sum(rows_per_region.values()) == imap.neq
    for r in REGIONS:
        assert (rows_per_region[r] > 0) == (counts[r] > 0), (family, r)


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_permuted_map_rejected(intake, family):
    """Two active rows of different cells exchanged in the live idx* arrays (the deliberately permuted map)."""
    data = dict(intake(family))
    idxte = np.array(data["idxte"]).copy()
    cells = np.argwhere(idxte > 0)
    (a, b), (c, d) = cells[0], cells[-1]
    idxte[a, b], idxte[c, d] = idxte[c, d], idxte[a, b]
    data["idxte"] = idxte
    with pytest.raises(IndexTruthError, match="igyl disagrees"):
        index_map(data)


def test_intake_takes_no_variant(runner):
    """The intake check evaluates the unperturbed reference state only."""
    v = next(iter(variants.plan()))
    with pytest.raises(ValueError, match="takes no variant"):
        runner.evaluate("d_only", config=INTAKE, variant=v)


@pytest.mark.parametrize("family", ["d_only", "d_c"])
def test_diagnostics_are_placed(runner, family):
    res = runner.evaluate(family, config="steady", diagnostics=True)
    assert res.ok, "{}: {} {}".format(family, res.status, res.message)
    names = set(res.data["diagnostics"])
    unplaced = sorted(names - set(PANDF_ORDER) - set(UNORDERED))
    assert not unplaced, "diagnostic arrays in neither PANDF_ORDER nor UNORDERED (compare.py): {}".format(unplaced)


# ---------------------------------------------------------------- manifests against the inventory (AIUE-96)


@pytest.fixture(scope="module")
def plan():
    return variants.plan()


def inventory_problems(manifest, plan):
    """What keeps a manifest's variables from being the inventory: missing and stale ids, and inventory-EXCLUDED
    variants stored in another class or with another reason. Every family, owner families included (AIUE-99)."""
    stored = manifest.get("variables") or {}
    ids = {v.id: v for v in plan}
    out = ["missing: {}".format(vid) for vid in ids if vid not in stored]
    out += ["stale: {}".format(vid) for vid in stored if vid not in ids]
    for vid, v in ids.items():
        e = stored.get(vid)
        if v.excluded and e is not None and (e["class"], e["reason"]) != ("EXCLUDED", v.reason):
            out.append("{}: EXCLUDED in the inventory ({}), stored {} ({})".format(vid, v.reason, e["class"],
                                                                                  e["reason"]))
    return out


def reason_problems(manifest):
    return ["{}: {} without a reason".format(vid, e["class"]) for vid, e in (manifest.get("variables") or {}).items()
            if e["class"] in NEEDS_REASON and not str(e.get("reason") or "").strip()]


@pytest.mark.toml_only
@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_manifest_inventory(plan, family):
    problems = inventory_problems(mf.load(family), plan)
    assert not problems, "{}: the manifest is not the inventory (regenerate with make_references.py): {}".format(
        family, problems[:20])


@pytest.mark.toml_only
@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_reasons(family):
    problems = reason_problems(mf.load(family))
    assert not problems, "{}: {}".format(family, problems[:20])


def test_inventory_detects_removed_entry(plan):
    """Acceptance (AIUE-96): d_only's manifest without one entry, or with one id the inventory lacks, fails."""
    m = mf.load("d_only")
    assert not inventory_problems(m, plan)
    vid = next(iter(m["variables"]))
    cut = copy.deepcopy(m)
    del cut["variables"][vid]
    assert inventory_problems(cut, plan) == ["missing: {}".format(vid)]
    extra = copy.deepcopy(m)
    extra["variables"]["bbb.no_such_input"] = m["variables"][vid]
    assert inventory_problems(extra, plan) == ["stale: bbb.no_such_input"]
    excluded = next(v for v in plan if v.excluded)
    moved = copy.deepcopy(m)
    moved["variables"][excluded.id] = dict(m["variables"][excluded.id], **{"class": "INERT", "reason": ""})
    assert inventory_problems(moved, plan)[0].startswith(excluded.id + ": EXCLUDED in the inventory")
    assert reason_problems(dict(moved, variables={vid: dict(m["variables"][vid], **{"class": "MARGINAL",
                                                                                     "reason": " "})}))


def test_owner_family_must_be_complete(plan):
    """AIUE-99: every owner family's manifest classifies the inventory; an empty one fails like a partial one (D6's
    "or none" ended with the owner sweep)."""
    owners = [f for f in FAMILY_NAMES if mf.owner_family(f)]
    assert owners and all(not inventory_problems(mf.load(f), plan) for f in owners)
    m = mf.load(owners[0])
    for cut in ({}, dict(list(m["variables"].items())[:5])):
        assert any(p.startswith("missing: ") for p in inventory_problems(dict(m, variables=cut), plan))


# ---------------------------------------------------------------- what the harness sets itself


def pinned(source):
    """The package-qualified variables the source assigns as <pkg>.X or <pkg>.X[...] (harness/state.py)."""
    out = set()
    for node in ast.walk(ast.parse(source)):
        targets = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
        for t in targets:
            while isinstance(t, ast.Subscript):
                t = t.value
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in inputs.PACKAGES:
                out.add("{}.{}".format(t.value.id, t.attr))
    return out


def test_pinned_excluded(plan):
    """A tagged input the harness sets in every evaluation (today bbb.restart) cannot be varied: it is EXCLUDED in
    the inventory and in every manifest with variables."""
    keys = pinned(STATE.read_text())
    assert {"bbb.restart", "bbb.issfon", "bbb.ftol", "bbb.dtreal", "bbb.yl"} <= keys, keys
    allvars = inputs.parse()
    ids = {v.id: v for v in plan}
    tagged = sorted(k for k in keys if allvars[k].tagged)
    assert tagged, "no tagged input among the harness's assignments {}: check pinned()".format(sorted(keys))
    for key in tagged:
        assert key in ids and ids[key].excluded, "{}: set by harness/state.py, not EXCLUDED in the inventory".format(
            key)
        for family in FAMILY_NAMES:
            e = (mf.load(family).get("variables") or {}).get(key)
            assert e is None or e["class"] == "EXCLUDED", "{}: {} is {}".format(family, key, e["class"])


def test_pinned_detects():
    assert pinned("bbb.restart = 1\nbbb.yl[3] = 0.\ncom.iprint += 1\nx.restart = 1\nbbb.f(1)\n") == {
        "bbb.restart", "bbb.yl", "com.iprint"}


# ---------------------------------------------------------------- source checks


def normal_form_problems(source):
    """An input.py's departures from normal form (PRD section 6): restart set, a state restored, the solver run."""
    out = []
    for node in ast.walk(ast.parse(source)):
        targets = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
        for t in targets:
            while isinstance(t, ast.Subscript):
                t = t.value
            if isinstance(t, ast.Attribute) and t.attr == "restart":
                out.append("line {}: sets restart".format(node.lineno))
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if name in NOT_IN_INPUT:
                out.append("line {}: calls {}".format(node.lineno, name))
    return out


@pytest.mark.toml_only
@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_input_normal_form(family):
    problems = normal_form_problems((FAMILIES / family / "input.py").read_text())
    assert not problems, "{}/input.py: {}".format(family, problems)


def test_normal_form_detects():
    src = "from uedge import bbb\nbbb.restart = 1\nhdf5_restore('x.h5')\nbbb.exmain()\nprint('bbb.exmain()')\n"
    assert normal_form_problems(src) == ["line 2: sets restart", "line 3: calls hdf5_restore",
                                         "line 4: calls exmain"]


def skip_uses(source):
    """Uses of a banned skip or xfail (BANNED, PRD section 7.6), through import aliases too: 'line N: name'."""
    tree = ast.parse(source)
    alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top in ("pytest", "unittest"):  # import pytest.x binds pytest; import pytest.x as y binds y
                    alias[a.asname or top] = a.name if a.asname else top
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in ("pytest", "unittest"):
            for a in node.names:
                alias[a.asname or a.name] = "{}.{}".format(node.module, a.name)

    def dotted(node):
        if isinstance(node, ast.Name):
            return alias.get(node.id)
        if isinstance(node, ast.Attribute):
            base = dotted(node.value)
            return None if base is None else "{}.{}".format(base, node.attr)
        return None

    return sorted({"line {}: {}".format(n.lineno, dotted(n)) for n in ast.walk(tree)
                   if isinstance(n, (ast.Name, ast.Attribute)) and dotted(n) in BANNED})


def test_no_skips():
    """Nothing under tests/yldot skips or xfails a test (PRD section 7.6): a test passes or fails."""
    files = sorted(p for p in SUITE.rglob("*.py")
                   if not {"__pycache__", ".data"} & set(p.relative_to(SUITE).parts))
    assert len(files) > 20, files
    hits = ["{}: {}".format(p.relative_to(SUITE), h) for p in files for h in skip_uses(p.read_text())]
    assert not hits, hits


@pytest.mark.parametrize("src, expected", [
    ("import pytest\n@pytest.mark.skip\ndef test_a(): pass\n", ["line 2: pytest.mark.skip"]),
    ("import pytest\n@pytest.mark.skipif(True, reason='x')\ndef test_a(): pass\n", ["line 2: pytest.mark.skipif"]),
    ("import pytest\npytestmark = pytest.mark.xfail(strict=True)\n", ["line 2: pytest.mark.xfail"]),
    ("import pytest\ndef test_a():\n    pytest.skip('x')\n", ["line 3: pytest.skip"]),
    ("import pytest as pt\ndef test_a():\n    pt.xfail('x')\n", ["line 3: pytest.xfail"]),
    ("from pytest import skip as s\ndef test_a():\n    s()\n", ["line 3: pytest.skip"]),
    ("from pytest import mark\n@mark.skip\ndef test_a(): pass\n", ["line 2: pytest.mark.skip"]),
    ("import pytest\nnp = pytest.importorskip('numpy')\n", ["line 2: pytest.importorskip"]),
    ("import unittest\n@unittest.skipIf(True, 'x')\ndef test_a(): pass\n", ["line 2: unittest.skipIf"]),
    ("from unittest import skip\n@skip('x')\ndef test_a(): pass\n", ["line 2: unittest.skip"]),
    ("import pytest\ns = 'pytest.mark.skip'\n@pytest.mark.parametrize('a', [1])\ndef test_a(a): pass\n", []),
])
def test_skip_ban_detects(src, expected):
    assert skip_uses(src) == expected
