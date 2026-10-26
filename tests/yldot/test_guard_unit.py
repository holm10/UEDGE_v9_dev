"""Unit tests of tools/check_reference_change.py, the reference guard (AIUE-97; PRD section 7.6; owner decisions of
2026-10-22 on the AIUE-97 ticket page): the path classes, the tolerances.toml, overrides.toml, family.toml and manifest
rules, the declarations (including the edited case: the same diff judged again with a new description), the
release-asset and dataset checks, and history. Each test commits a base and a head into a scratch git repository;
the release downloads and gh are fakes. No uedge import, no network.
"""
import hashlib
import itertools
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from yldot.harness import manifest as mf
from yldot.harness import store
from yldot.harness.compare import index_map
from yldot.test_compare_unit import SPEC, make_data

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

import check_reference_change as guard  # noqa: E402
import fetch_data  # noqa: E402

DATA = make_data()
IMAP = index_map(DATA, SPEC)
N = IMAP.neq
LABELS, ROWS, _ = store.blocks(IMAP)
RNG = np.random.default_rng(97)
Y = RNG.standard_normal(N)
YJ = Y.copy()
YJ[[0, 3]] += 1.0
SIGMA = np.full(N, 1e-13)
DIAG = {"resco": np.arange(4.0)}
V1, V2 = "yldot-data-v1", "yldot-data-v2"
G = "tests/yldot/"
STATE = "families/fam/base_state.h5"
APPLIED = {"dtype": "int64", "shape": [], "data": 1}
COUNTER = itertools.count()

TOLERANCES = """[rule]
k = 100.0
rtol_factor = 100.0
rtol_floor = 1e-14
floor_limit = 0.1
floor = "the floor rule"

[rtol]
te = 2.5e-08
ti = 2.5e-08

[sigma.fam]
file = "families/fam/sigma.h5"
sha256 = "aa"
steady = { entries = 30, zero = 3, max = 0.1 }

[owner]
items_raised = 1
items_answered = 1
"""
OVERRIDES = """["bbb.both"]
exclude = true
reason = "base"

["bbb.inert"]
reason = "base"
values = [1, 2]
"""
OVERRIDES_WITHOUT_BOTH = OVERRIDES[OVERRIDES.index('["bbb.inert"]'):]
FAMILY = """[family]
name = "fam"
store = "full"
neq = 30

[evaluation]
w = 1
p = 1

[history]
measured = "2026-10-21"
"""
BASE_VARIABLES = {"fam": {"bbb.sens": ("SENSITIVE", 1), "bbb.inert": ("INERT", None), "bbb.both": ("INERT", None)},
                  "oth": {"bbb.inert": ("SENSITIVE", 2), "bbb.both": ("INERT", None)}}


def variant(seed):
    y = Y.copy()
    y[[seed % N, (7 * seed + 3) % N]] *= 2.0
    return y


def make_ref(where, family, variables, release=V1, default=Y, sigma=SIGMA, diag=DIAG, external=None, applied=None,
             locality=None, kind="full", thresholds=None, weights=None, loc_variants=None):
    """(manifest, .h5 bytes) of a reference (a full store unless kind); variables {id: (class, seed)}, the SENSITIVE
    ones stored; locality: (delta, entries) of a stored locality pattern; thresholds: the tol of a sketch store's
    stored sketch thresholds (default THR: a sketch store always has them and its weights, AIUE-174); weights: its
    stored weights (default 1 / thresholds); loc_variants: {id: (added, dropped)} steady locality differences."""
    p = Path(where) / "{}-{}.h5".format(family, next(COUNTER))
    w = store.create(p, kind, family, DATA, IMAP)
    for config in mf.CONFIG_NAMES:
        w.write_default(config, default, YJ + (default - Y), sigma, diag)
        if kind == "sketch":
            w.write_sketch_thresholds(config, THR if thresholds is None else thresholds, weights)
    if locality is not None:
        w.write_locality("steady", *locality)
    for vid, (cls, seed) in sorted(variables.items()):
        if cls == "SENSITIVE":
            w.write_variant("steady", vid, variant(seed), variant(seed) + (YJ - Y))
    for vid, (added, dropped) in sorted((loc_variants or {}).items()):
        w.write_locality_variant("steady", vid, added, dropped)
    out = w.finish()
    guarded, unguarded = mf.summarize(out["datasets"])
    entries = {}
    for vid, (cls, seed) in variables.items():
        sens = cls == "SENSITIVE"
        entries[vid] = {"class": cls, "reason": "r", "applied": (applied or {}).get(vid), "d": None, "phase": "PRE",
                        "config": "steady", "sha256": mf.variant_sha(out["datasets"], "steady", vid) if sens else None,
                        "block_l2": store.block_l2(variant(seed) - Y, LABELS, ROWS) if sens else {},
                        "jflag_block_l2": {}}
    m = {"schema": mf.SCHEMA, "family": family, "store": kind, "release": release,
         "external": dict({mf.reference_path(family): {"sha256": out["sha256"], "bytes": out["bytes"]}},
                          **(external or {})),
         "datasets": out["datasets"], "guarded": guarded, "unguarded": unguarded,
         "provenance": {k: "x" for k in mf.PROVENANCE}, "variables": entries}
    if kind == "sketch":
        m["sketch"] = {"k": store.K, "seed": store.SEED}
    if out["locality_variants"]:
        m["locality_variants"] = out["locality_variants"]
    mf.validate(m)
    return m, p.read_bytes()


def external(content):
    return {STATE: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}}


class FakeRelease:
    """A download() stand-in serving {tag: {asset: bytes}}."""

    def __init__(self, assets):
        self.assets, self.calls = assets, []

    def __call__(self, tag, names, dest, repo):
        self.calls.append((tag, sorted(names)))
        for a in names:
            if a in self.assets.get(tag, {}):
                (Path(dest) / a).write_bytes(self.assets[tag][a])


class Repo:
    """A scratch git repository holding a minimal tests/yldot, and the data releases its manifests name."""

    def __init__(self, root, scratch):
        self.root, self.scratch = Path(root), Path(scratch)
        self.assets, self.files = {}, {STATE: b"state-1" * 8}
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")
        for family, variables in BASE_VARIABLES.items():
            self.put_ref(family, variables, release=V1)
        for path, text in ((G + "tolerances.toml", TOLERANCES), (G + "overrides.toml", OVERRIDES),
                           (G + "families/fam/family.toml", FAMILY), (G + "families/fam/input.py", "x = 1\n"),
                           (G + "families/fam/sigma.h5", "sigma"), (G + "harness/state.py", "x = 1\n"),
                           (G + "tools/check_reference_change.py", "x = 1\n"), (G + "tools/fetch_data.py", "x = 1\n"),
                           (G + "data/rates.txt", "r\n"), (".github/workflows/build-test-wheel.yml", "on: push\n"),
                           (".github/workflows/reference-guard.yml", "on: pull_request_target\n"),
                           ("README.md", "readme\n")):
            self.write(path, text)
        self.base = self.commit("base")
        self.download = FakeRelease(self.assets)

    def git(self, *args):
        r = subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t", "-c",
                            "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                           capture_output=True, text=True, check=True)
        return r.stdout

    def write(self, path, content):
        p = self.root / path
        if content is None:
            p.unlink()
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)

    def commit(self, message="head"):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def manifest(self, family):
        return mf.loads((self.root / G / "references" / "{}.manifest.json".format(family)).read_text())

    def put_ref(self, family, variables, release=V2, serve=True, edit=None, **kw):
        """Build and commit-ready write a family's reference and manifest; serve its assets under release."""
        if family == "fam":
            kw.setdefault("external", external(self.files[STATE]))
        m, h5 = make_ref(self.scratch, family, variables, release=release, **kw)
        if edit:
            edit(m)
        self.write(G + "references/{}.manifest.json".format(family), mf.dumps(m))
        if serve and release:
            tag = self.assets.setdefault(release, {})
            tag[mf.asset_name(mf.reference_path(family))] = h5
            if family == "fam":
                tag[mf.asset_name(STATE)] = self.files[STATE]
        return m, h5

    def check(self, body="", **kw):
        """(exit code, verdict, output) of check from the base to a new head commit."""
        head = self.commit()
        lines = self.lines = []
        out = self.scratch / "verdict-{}.json".format(next(COUNTER))
        code = guard.check(self.root, self.base, head, body, download=self.download, json_out=out,
                           out=lines.append, **kw)
        verdict = json.loads(out.read_text()) if out.exists() else {}
        return code, verdict, "\n".join(lines)


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo", tmp_path)


def reqs(verdict):
    """The requirements as short names."""
    names = {v: k for k, v in guard.KEYWORDS.items()}
    return {names[r] for r in verdict["required"]}


# ---------------------------------------------------------------- path classes


@pytest.mark.parametrize("path, status, kind", [
    ("README.md", "M", None),
    ("src/uedge/hdf5.py", "M", None),
    (G + "harness/state.py", "M", "loosened"),
    (G + "harness/new.py", "A", "loosened"),
    (G + "conftest.py", "M", "loosened"),
    (G + "__init__.py", "M", "loosened"),
    (G + "test_smoke.py", "M", "loosened"),
    (G + "test_new.py", "A", "loosened"),
    (G + "tools/check_reference_change.py", "M", "loosened"),
    (G + "tools/fetch_data.py", "M", "changed"),
    (G + "families/fam/input.py", "M", "changed"),
    (G + "families/fam/gridue", "M", "changed"),
    (G + "families/fam/sigma.h5", "M", "loosened"),
    (G + "families/new/sigma.h5", "A", "changed"),
    (G + "data/rates.txt", "M", "changed"),
    (G + "linux/Dockerfile", "M", "changed"),
    (G + "mutations/m01.patch", "A", None),
    (G + "mutations/notes.txt", "A", None),
    (G + "mutations/conftest.py", "A", "loosened"),  # pytest loads these: not exempt as additions
    (G + "mutations/test_m.py", "A", "loosened"),
    (G + "mutations/m_test.py", "A", "loosened"),
    (G + "mutations/helper.py", "A", "changed"),
    (G + "mutations/pytest.ini", "A", "loosened"),
    (G + "mutations/tox.ini", "A", "loosened"),
    (G + "mutations/setup.cfg", "A", "loosened"),
    (G + "mutations/pyproject.toml", "A", "loosened"),
    (G + "mutations/extra.cfg", "A", "changed"),
    (G + "mutations/extra.toml", "A", "changed"),
    (G + "mutations/extra.ini", "A", "changed"),
    (G + "families/fam/conftest.py", "M", "loosened"),
    (G + "families/fam/test_fam.py", "M", "loosened"),
    (G + "families/fam/fam_test.py", "A", "loosened"),
    (G + "pytest.ini", "M", "loosened"),
    (G + ".pytest.ini", "M", "loosened"),
    (G + "families/fam/.pytest.ini", "A", "loosened"),
    (G + "mutations/.pytest.ini", "A", "loosened"),
    (".pytest.ini", "M", "loosened"),
    ("tests/.pytest.ini", "A", "loosened"),
    ("tests/.pytest.ini", "D", "loosened"),
    ("src/.pytest.ini", "M", None),
    ("tests/other/.pytest.ini", "M", None),
    (G + "pytest.toml", "M", "loosened"),
    (G + "families/fam/pytest.toml", "A", "loosened"),
    (G + "mutations/pytest.toml", "A", "loosened"),
    ("pytest.toml", "M", "loosened"),
    ("tests/pytest.toml", "A", "loosened"),
    ("tests/pytest.toml", "D", "loosened"),
    ("src/pytest.toml", "M", None),
    ("tests/other/pytest.toml", "M", None),
    (G + ".pytest.toml", "M", "loosened"),
    (G + "families/fam/.pytest.toml", "A", "loosened"),
    (G + "mutations/.pytest.toml", "A", "loosened"),
    (".pytest.toml", "M", "loosened"),
    ("tests/.pytest.toml", "A", "loosened"),
    ("tests/.pytest.toml", "D", "loosened"),
    ("src/.pytest.toml", "M", None),
    ("tests/other/.pytest.toml", "M", None),
    (G + "families/fam/tox.ini", "M", "loosened"),
    (G + "setup.cfg", "M", "loosened"),
    (G + "families/fam/pyproject.toml", "M", "loosened"),
    ("conftest.py", "M", "loosened"),
    ("tests/conftest.py", "A", "loosened"),
    ("pytest.ini", "M", "loosened"),
    ("tests/tox.ini", "M", "loosened"),
    ("tox.ini", "A", "loosened"),
    (".pytest.ini", "M", "loosened"),
    ("tests/pytest.ini", "D", "loosened"),
    ("pyproject.toml", "M", "pytestcfg"),
    ("setup.cfg", "M", "pytestcfg"),
    ("tests/pyproject.toml", "M", "pytestcfg"),
    ("tests/setup.cfg", "M", "pytestcfg"),
    ("src/conftest.py", "M", None),
    ("docs/pytest.ini", "M", None),
    (G + "mutations/m01.patch", "M", "changed"),
    (G + "mutations/m01.patch", "D", "loosened"),
    (G + "families/fam/input.py", "D", "loosened"),
    (G + "references/fam.manifest.json", "M", "manifest"),
    (G + "references/fam.manifest.json", "D", "manifest"),
    (G + "tolerances.toml", "M", "tolerances"),
    (G + "overrides.toml", "M", "overrides"),
    (G + "families/fam/family.toml", "M", "family"),
    (".github/workflows/reference-guard.yml", "M", "loosened"),
    (".github/workflows/build-test-wheel.yml", "M", "changed"),
    (".github/workflows/nightly-tests.yml", "A", "changed"),
    (".github/workflows/regenerate-references.yml", "M", "changed"),
    (".github/workflows/build-test-omp.yml", "M", None),
    # test_smoke.py's collection-separation check refuses node ids naming the AIUE-8 suite, hence the id
    pytest.param("tests/deterministic_omp/harness/serial_check.py", "M", None, id="AIUE-8-suite-not-guarded"),
])
def test_path_class(path, status, kind):
    assert guard.path_class(path, status) == kind


def test_nothing_guarded(repo):
    repo.write("README.md", "changed\n")
    code, v, text = repo.check()
    assert code == 0 and v["required"] == [] and "nothing guarded" in text


def test_guarded_file_needs_changed(repo):
    repo.write(G + "tools/fetch_data.py", "x = 2\n")
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"changed"} and v["missing"] == ["Test criteria: changed"]
    assert repo.check("Test criteria: changed — a new tool option")[0] == 0


def test_harness_and_guard_are_loosenings(repo):
    repo.write(G + "harness/state.py", "x = 2\n")
    repo.write(G + "tools/check_reference_change.py", "x = 2\n")
    code, v, text = repo.check("Test criteria: changed: harness refactor")
    assert code == 1 and reqs(v) == {"changed", "loosened"} and v["codeowner_approval"]
    assert guard.CODEOWNER in text
    code, v, _ = repo.check("Test criteria: changed: harness refactor\nTest criteria: loosened: reviewed by the owner")
    assert code == 0 and v["codeowner_approval"]


def test_workflows(repo):
    repo.write(".github/workflows/build-test-wheel.yml", "on: pull_request\n")
    assert reqs(repo.check()[1]) == {"changed"}
    repo.write(".github/workflows/reference-guard.yml", "on: pull_request\n")
    assert reqs(repo.check()[1]) == {"changed", "loosened"}


def test_new_mutation_is_not_guarded(repo):
    repo.write(G + "mutations/m01.patch", "diff\n")
    code, v, _ = repo.check()
    assert code == 0 and v["required"] == []


def test_deleted_guarded_file_is_a_loosening(repo):
    repo.write(G + "families/fam/input.py", None)
    assert reqs(repo.check()[1]) == {"changed", "loosened"}


# ---------------------------------------------------------------- TOML rules


def tol(text=TOLERANCES, **edits):
    import tomllib

    t = tomllib.loads(text)
    for path, value in edits.items():
        sec, key = path.split("__")
        if value is None:
            t[sec].pop(key)
        else:
            t.setdefault(sec, {})[key] = value
    return t


@pytest.mark.parametrize("edits, want", [
    ({"rule__k": 200.0}, {"loosened"}),
    ({"rule__k": 50.0}, {"changed"}),
    ({"rule__rtol_floor": 1e-13}, {"loosened"}),
    ({"rule__rtol_factor": 10.0}, {"changed"}),
    ({"rule__floor_limit": 0.05}, {"loosened"}),
    ({"rule__floor": "another rule"}, {"loosened"}),
    ({"rule__m_cls": 3.0}, {"loosened"}),  # a key the guard does not know
    ({"rtol__te": 3e-08}, {"loosened"}),
    ({"rtol__te": 2e-08}, {"changed"}),
    ({"rtol__te": None}, {"loosened"}),
    ({"rtol__phi": 1e-08}, {"changed"}),
    ({"owner__items_raised": 2}, {"changed"}),
    ({"builds__x": {"sha256": "bb"}}, {"changed"}),
    ({"margins__m_loc": 2}, {"loosened"}),  # an unknown section
])
def test_tolerances_rules(edits, want):
    assert {req for req, _ in guard.diff_tolerances(tol(), tol(**edits))} == want


def test_tolerances_sigma_rules():
    base = tol()
    sha = tol()
    sha["sigma"]["fam"]["sha256"] = "bb"
    record = tol()
    record["sigma"]["fam"]["steady"] = {"entries": 30, "zero": 4, "max": 0.1}
    removed = tol()
    removed["sigma"].pop("fam")
    added = tol()
    added["sigma"]["new"] = {"file": "families/new/sigma.h5", "sha256": "cc"}
    assert {r for r, _ in guard.diff_tolerances(base, sha)} == {"loosened"}
    assert {r for r, _ in guard.diff_tolerances(base, record)} == {"changed"}
    assert {r for r, _ in guard.diff_tolerances(base, removed)} == {"loosened"}
    assert {r for r, _ in guard.diff_tolerances(base, added)} == {"changed"}


def test_tolerances_in_a_pr(repo):
    repo.write(G + "tolerances.toml", TOLERANCES.replace("k = 100.0", "k = 200.0"))
    code, v, text = repo.check("Test criteria: changed: k")
    assert code == 1 and reqs(v) == {"changed", "loosened"} and "[rule].k: 100.0 -> 200.0" in text
    repo.write(G + "tolerances.toml", TOLERANCES.replace("k = 200.0", "k = 50.0") + "# a comment\n")
    assert reqs(repo.check()[1]) == {"changed"}


def test_toml_text_only_change(repo):
    repo.write(G + "tolerances.toml", "# reformatted\n" + TOLERANCES)
    code, v, text = repo.check()
    assert reqs(v) == {"changed"} and "text only" in text


def test_overrides_rules():
    import tomllib

    base = tomllib.loads(OVERRIDES)
    new = dict(base, **{"bbb.x": {"reason": "new"}})
    edited = dict(base, **{"bbb.inert": {"reason": "base", "values": [1, 3]}})
    removed = {k: v for k, v in base.items() if k != "bbb.both"}
    assert {r for r, _ in guard.diff_overrides(base, new, set())} == {"changed"}
    assert {r for r, _ in guard.diff_overrides(base, edited, set())} == {"loosened"}
    assert {r for r, _ in guard.diff_overrides(base, removed, set())} == {"loosened"}
    assert {r for r, _ in guard.diff_overrides(base, removed, {"bbb.both"})} == {"changed"}


def test_override_removed_with_its_pruned_variable(repo):
    """Story 10: removing the override of a variable the same PR prunes from every manifest is only a change."""
    for family, variables in BASE_VARIABLES.items():
        repo.put_ref(family, {k: c for k, c in variables.items() if k != "bbb.both"}, release=V1, serve=False)
    repo.write(G + "overrides.toml", OVERRIDES_WITHOUT_BOTH)
    code, v, text = repo.check("Test criteria: changed: bbb.both left the inventory")
    assert code == 0, text
    assert reqs(v) == {"changed"} and "removed with its pruned variable" in text and "prune bbb.both" in text


def test_override_removed_without_prune_is_a_loosening(repo):
    repo.write(G + "overrides.toml", OVERRIDES_WITHOUT_BOTH)
    assert reqs(repo.check()[1]) == {"changed", "loosened"}


def test_family_toml_rules():
    import tomllib

    base = tomllib.loads(FAMILY)
    w = tomllib.loads(FAMILY.replace("w = 1", "w = 2"))
    hist = tomllib.loads(FAMILY.replace("2026-10-21", "2026-10-22"))
    store_kind = tomllib.loads(FAMILY.replace('store = "full"', 'store = "sketch"'))
    neq = tomllib.loads(FAMILY.replace("neq = 30", "neq = 31"))
    unknown = dict(base, extra={"a": 1})
    assert {r for r, _ in guard.diff_family_toml(base, w)} == {"loosened"}
    assert {r for r, _ in guard.diff_family_toml(base, hist)} == {"changed"}
    assert {r for r, _ in guard.diff_family_toml(base, store_kind)} == {"loosened"}
    assert {r for r, _ in guard.diff_family_toml(base, neq)} == {"changed"}
    assert {r for r, _ in guard.diff_family_toml(base, unknown)} == {"loosened"}


LOCALITY = {"delta_loc": 1e-5, "m_loc": 100.0, "calibration": "record", "causes": {"none": "bit-identical"}}


@pytest.mark.parametrize("a, b, want", [
    (None, LOCALITY, {"changed"}),  # a new criterion
    (LOCALITY, None, {"loosened"}),
    (LOCALITY, dict(LOCALITY, m_loc=50.0), {"changed"}),  # a smaller margin
    (LOCALITY, dict(LOCALITY, m_loc=200.0), {"loosened"}),
    (LOCALITY, dict(LOCALITY, m_loc="100"), {"loosened"}),  # not a number
    (LOCALITY, dict(LOCALITY, delta_loc=1e-6), {"loosened"}),  # non-monotone, either way
    (LOCALITY, dict(LOCALITY, delta_loc=1e-4), {"loosened"}),
    (LOCALITY, dict(LOCALITY, calibration="new record"), {"changed"}),
    (LOCALITY, dict(LOCALITY, causes={"nonog": "x"}), {"changed"}),
    (LOCALITY, dict(LOCALITY, extra=1), {"loosened"}),  # a key the guard does not know
    (LOCALITY, {k: v for k, v in LOCALITY.items() if k != "m_loc"}, {"loosened"}),
])
def test_family_toml_locality_rules(a, b, want):
    import tomllib

    base = tomllib.loads(FAMILY)
    f0 = dict(base, locality=a) if a is not None else base
    f1 = dict(base, locality=b) if b is not None else base
    assert {r for r, _ in guard.diff_family_toml(f0, f1)} == want


SPECIAL = dict(LOCALITY, columns="special", variants="meth", sample=300, seed=1)
ALL = dict(LOCALITY, columns="all", variants="all")


@pytest.mark.parametrize("a, b, want", [
    (LOCALITY, ALL, {"changed"}),  # the AIUE-101 keys added: every column (as before), variant patterns new
    (ALL, dict(ALL, columns="special", sample=300, seed=1), {"loosened"}),  # fewer columns
    (SPECIAL, dict(SPECIAL, columns="all", sample=None, seed=None), {"changed"}),  # every column: sample/seed go
    (ALL, dict(ALL, variants="listed"), {"loosened"}),
    (dict(ALL, variants="meth"), dict(ALL, variants="listed"), {"changed"}),
    (ALL, dict(ALL, variants="some"), {"loosened"}),  # unknown value
    (SPECIAL, dict(SPECIAL, sample=200), {"loosened"}),
    (SPECIAL, dict(SPECIAL, sample=400), {"changed"}),
    (SPECIAL, dict(SPECIAL, sample=True), {"loosened"}),
    (SPECIAL, dict(SPECIAL, seed=2), {"changed"}),
    (ALL, dict(ALL, excluded={"bbb.a": "why"}), {"loosened"}),  # an owner exclusion: CODEOWNER approval
    (dict(ALL, excluded={"bbb.a": "why"}), dict(ALL, excluded={"bbb.a": "better why"}), {"changed"}),
    (dict(ALL, excluded={"bbb.a": "why"}), ALL, {"changed"}),  # back in scope
])
def test_family_toml_locality_scope_rules(a, b, want):
    import tomllib

    base = tomllib.loads(FAMILY)
    strip = lambda t: {k: v for k, v in t.items() if v is not None}  # noqa: E731
    assert {r for r, _ in guard.diff_family_toml(dict(base, locality=strip(a)), dict(base, locality=strip(b)))} == want


def test_new_family_toml_is_a_change(repo):
    repo.write(G + "families/new/family.toml", FAMILY.replace("fam", "new"))
    repo.write(G + "families/new/sigma.h5", "sigma")
    assert reqs(repo.check()[1]) == {"changed"}


# ---------------------------------------------------------------- manifest rules


def test_addition_needs_no_declaration(repo):
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.new": ("SENSITIVE", 5), "bbb.off": ("INERT", None)}))
    code, v, text = repo.check()
    assert code == 0, text
    assert v["required"] == [] and "addition: variants ['bbb.new', 'bbb.off']" in text
    assert repo.download.calls == [(V2, sorted(mf.asset_name(p) for p in (mf.reference_path("fam"), STATE)))]


def test_first_references_of_an_external_only_manifest_are_an_addition(repo):
    """An owner family before AIUE-88: only external files; its first references add guarded keys."""
    m = {"schema": mf.SCHEMA, "family": "own", "store": "sketch", "release": V1, "external": {}}
    repo.write(G + "references/own.manifest.json", mf.dumps(m))
    repo.base = repo.commit("external-only manifest")
    repo.put_ref("own", {"bbb.a": ("SENSITIVE", 3)})
    code, v, text = repo.check()
    assert code == 0, text
    assert "addition: guarded" in text and v["required"] == []


def test_prune_of_entries_inert_everywhere(repo):
    for family, variables in BASE_VARIABLES.items():
        repo.put_ref(family, {k: c for k, c in variables.items() if k != "bbb.both"}, release=V1, serve=False)
    code, v, text = repo.check()
    assert code == 0 and v["required"] == [] and "prune bbb.both (INERT in every family)" in text
    assert repo.download.calls == []  # neither the data nor the release changed


def test_prune_refused_when_sensitive_elsewhere(repo):
    variables = {k: c for k, c in BASE_VARIABLES["fam"].items() if k != "bbb.inert"}
    repo.put_ref("fam", variables, release=V1, serve=False)
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"default"} and v["items"] == ["fam:bbb.inert"]


def test_rename_with_identical_data(repo):
    variables = {k: c for k, c in BASE_VARIABLES["fam"].items() if k != "bbb.sens"}
    repo.put_ref("fam", dict(variables, **{"bbb.renamed": ("SENSITIVE", 1)}))
    code, v, text = repo.check()
    assert code == 0, text
    assert "rename bbb.sens -> bbb.renamed (identical data)" in text


def test_rename_refused_when_the_applied_value_differs(repo):
    variables = {k: c for k, c in BASE_VARIABLES["fam"].items() if k != "bbb.sens"}
    repo.put_ref("fam", dict(variables, **{"bbb.renamed": ("SENSITIVE", 1)}), applied={"bbb.renamed": APPLIED})
    code, v, text = repo.check()
    assert code == 1 and v["items"] == ["fam:bbb.sens"]


def test_runs_form_alone_is_no_change_and_a_changed_value_in_it_is_named(repo):
    """AIUE-190: a base manifest with its applied values as data lists (written before the runs form) and the same
    manifest through mf.dumps (runs) are the same manifest; a changed value inside a runs form names its variant."""
    long = {"dtype": "float64", "shape": [2, 50], "data": [2.86] * 99 + [-0.0]}
    m = repo.manifest("fam")
    m["variables"]["bbb.inert"]["applied"] = m["variables"]["bbb.both"]["applied"] = long
    repo.write(G + "references/fam.manifest.json", json.dumps(m, indent=2, sort_keys=True) + "\n")
    repo.base = repo.commit("base with data lists")
    text = mf.dumps(m)
    assert text.count('"runs": [[2.86, 99], [-0.0, 1]]') == 2 and '"data": [2.86' not in text
    repo.write(G + "references/fam.manifest.json", text)
    code, v, out = repo.check()
    assert code == 0 and v["required"] == [], out
    m["variables"]["bbb.both"]["applied"] = dict(long, data=[2.86] * 98 + [3.0, -0.0])
    repo.write(G + "references/fam.manifest.json", mf.dumps(m))
    code, v, out = repo.check()
    assert code == 1 and reqs(v) == {"default"} and v["items"] == ["fam:bbb.both"], out
    assert "variant bbb.both changed: applied" in out


LOC = (1e-5, {"column": np.array([0, 2]), "row": np.array([1, 3]), "mismatch": np.array([1e-6, -2e-6]),
              "dfull": np.array([1e-3, 2e-3])})


def test_new_locality_pattern_is_an_addition(repo):
    repo.put_ref("fam", BASE_VARIABLES["fam"], locality=LOC)
    code, v, text = repo.check()
    assert code == 0, text
    assert v["required"] == [] and "addition: guarded ['locality/steady']" in text


def test_changed_locality_pattern_is_a_default_change(repo):
    """PRD 7.6: a changed locality pattern needs Default results: changed, judged through guarded locality/steady."""
    repo.put_ref("fam", BASE_VARIABLES["fam"], locality=LOC, release=V1, serve=False)
    repo.base = repo.commit("locality pattern")
    changed = (LOC[0], dict(LOC[1], mismatch=LOC[1]["mismatch"] * 2))
    repo.put_ref("fam", BASE_VARIABLES["fam"], locality=changed)
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"default"} and v["items"] == ["fam:locality/steady"], text
    assert not any("/locality/" in item for item in v["items"])  # the datasets are judged through guarded


def test_removed_locality_pattern_is_a_default_change(repo):
    repo.put_ref("fam", BASE_VARIABLES["fam"], locality=LOC, release=V1, serve=False)
    repo.base = repo.commit("locality pattern")
    repo.put_ref("fam", BASE_VARIABLES["fam"])
    code, v, text = repo.check()
    assert code == 1 and v["items"] == ["fam:locality/steady"] and "guarded locality/steady removed" in text


LV_ADDED = {"column": np.array([2]), "row": np.array([4]), "mismatch": np.array([3e-6]), "dfull": np.array([0.0])}
LV_NONE = {"column": np.zeros(0, int), "row": np.zeros(0, int)}
LV = {"bbb.inert": (LV_ADDED, LV_NONE)}  # an INERT variable of BASE_VARIABLES["fam"] with a locality pattern


def test_locality_variant_rules(repo):
    """AIUE-101: a new variant locality pattern is a new criterion, a changed one a default change of that variant
    (not of the packed guarded key), a removed one a loosening."""
    assert BASE_VARIABLES["fam"]["bbb.inert"][0] == "INERT"
    repo.put_ref("fam", BASE_VARIABLES["fam"], locality=LOC, release=V1, serve=False)
    repo.base = repo.commit("locality pattern")
    repo.put_ref("fam", BASE_VARIABLES["fam"], locality=LOC, loc_variants=LV)
    code, v, text = repo.check()
    assert reqs(v) == {"changed"} and "new locality patterns of variants ['bbb.inert']" in text, text
    repo.base = repo.commit("variant pattern")
    moved = {"bbb.inert": (dict(LV_ADDED, mismatch=np.array([6e-6])), LV_NONE)}
    repo.put_ref("fam", BASE_VARIABLES["fam"], locality=LOC, loc_variants=moved)
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"default"} and v["items"] == ["fam:bbb.inert"], text
    repo.put_ref("fam", BASE_VARIABLES["fam"], locality=LOC)
    code, v, text = repo.check()
    assert reqs(v) == {"changed", "loosened"} and "[loosened]" in text and \
        "locality pattern of variant bbb.inert removed" in text, text


def test_check_h5_locality_slices(tmp_path):
    m, h5 = make_ref(tmp_path, "fam", BASE_VARIABLES["fam"], locality=LOC, loc_variants=LV)
    p = tmp_path / "x.h5"
    p.write_bytes(h5)
    assert guard.check_h5(p, m) == []
    other = dict(m, locality_variants={"bbb.inert": dict(m["locality_variants"]["bbb.inert"], sha256="0" * 64)})
    assert any("slices differ" in x and "bbb.inert" in x for x in guard.check_h5(p, other))


THR = np.linspace(1e-9, 1e-7, N)


def without(prefix_end, other_thresholds=False):
    """A put_ref edit: the manifest without the datasets ending in prefix_end (a store from before they existed);
    other_thresholds: also another SHA for every sketch threshold dataset (an unweighted store's, as in v6)."""
    def edit(m):
        for name in [n for n in m["datasets"] if n.endswith(prefix_end) or prefix_end + "/" in n]:
            del m["datasets"][name]
        if other_thresholds:
            for name in [n for n in m["datasets"] if "/sketch_threshold/" in n]:
                m["datasets"][name] = hashlib.sha256(name.encode()).hexdigest()
        m["guarded"], m["unguarded"] = mf.summarize(m["datasets"])
    return edit


def test_new_sketch_thresholds_are_an_addition(repo):
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", release=V1, serve=False,
                 edit=lambda m: (without("/sketch_threshold")(m), without("/sketch_weight")(m)))
    repo.base = repo.commit("a sketch store")
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", thresholds=THR)
    code, v, text = repo.check()
    assert code == 0, text
    assert v["required"] == [] and "addition: guarded ['steady/sketch_threshold', 'steady/sketch_weight', " \
        "'timestep/sketch_threshold', 'timestep/sketch_weight']" in text


def test_weights_added_to_an_unweighted_store(repo):
    """AIUE-174, the v6 -> v7 step: weights are an addition, the weighted thresholds a loosening (changed)."""
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", release=V1, serve=False,
                 edit=without("/sketch_weight", other_thresholds=True))
    repo.base = repo.commit("an unweighted sketch store")
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch")
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"changed", "loosened"}, text
    assert "addition: guarded ['steady/sketch_weight', 'timestep/sketch_weight']" in text
    assert "stored sketch thresholds steady/sketch_threshold changed" in text
    assert not any("sketch_weight" in item for item in v["items"])


def test_changed_sketch_weights_are_a_default_change(repo):
    """AIUE-174: a weight change changes what every variant sketch means, so it is judged like the defaults."""
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", release=V1, serve=False)
    repo.base = repo.commit("a sketch store")
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", weights=2.0 / THR)
    code, v, text = repo.check()
    assert code == 1 and "default" in reqs(v), text
    assert "guarded steady/sketch_weight changed" in text
    assert {"oth:steady/sketch_weight", "oth:timestep/sketch_weight"} <= set(v["items"])
    assert not any(item.endswith("/default/sketch_weight") for item in v["items"])  # judged through guarded only


def test_removed_sketch_weights_are_a_default_change(repo):
    """Review I1-m1: removing the weights (a manifest without them) is judged like a removed default."""
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", release=V1, serve=False)
    repo.base = repo.commit("a sketch store")
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", edit=without("/sketch_weight"))
    code, v, text = repo.check(no_download=True)
    assert code == 1 and "default" in reqs(v), text
    assert "guarded steady/sketch_weight removed" in text and "guarded timestep/sketch_weight removed" in text
    assert {"oth:steady/sketch_weight", "oth:timestep/sketch_weight"} <= set(v["items"])


def test_changed_sketch_thresholds_are_a_loosening(repo):
    """AIUE-92: the manifest cannot show changed sketch thresholds to be smaller, so any change is a loosening (like a
    changed sigma), judged through guarded <config>/sketch_threshold, not per dataset."""
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", thresholds=THR, release=V1, serve=False)
    repo.base = repo.commit("sketch thresholds")
    repo.put_ref("oth", BASE_VARIABLES["oth"], kind="sketch", thresholds=0.5 * THR, weights=1.0 / THR)  # same weights
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"changed", "loosened"}, text  # a loosening also needs the changed line
    assert "stored sketch thresholds steady/sketch_threshold changed" in text
    assert not any("sketch_threshold/" in item for item in v["items"])


def test_diagnostics_only(repo):
    repo.put_ref("fam", BASE_VARIABLES["fam"], diag={"resco": np.arange(4.0) + 1.0})
    code, v, text = repo.check()
    assert code == 0 and v["required"] == [] and "diagnostics changed (unguarded)" in text


def test_changed_default(repo):
    repo.put_ref("fam", BASE_VARIABLES["fam"], default=Y * (1 + 1e-6))
    code, v, text = repo.check("Default results: changed\nfam:steady/default")
    assert code == 1 and reqs(v) == {"default"}
    assert {"fam:steady/default", "fam:timestep/default", "fam:bbb.sens"} <= set(v["items"])
    assert "fam:steady/default" not in v["missing_items"] and "fam:timestep/default" in v["missing_items"]
    paste = text.split("add:\n", 1)[1]
    assert paste.startswith("Default results: changed\n- fam:bbb.sens\n")


def test_changed_sensitive_entry(repo):
    variables = dict(BASE_VARIABLES["fam"], **{"bbb.sens": ("SENSITIVE", 9)})
    repo.put_ref("fam", variables)
    code, v, _ = repo.check("- **Default results: changed**\n  - fam:bbb.sens.")
    assert code == 0 and v["items"] == ["fam:bbb.sens"]


def test_class_change(repo):
    variables = dict(BASE_VARIABLES["fam"], **{"bbb.inert": ("SENSITIVE", 4)})
    repo.put_ref("fam", variables)
    code, v, text = repo.check()
    assert code == 1 and v["items"] == ["fam:bbb.inert"] and "variant bbb.inert changed: block_l2, class, sha256" \
        in text


def test_changed_owner_state(repo):
    repo.files[STATE] = b"state-2" * 8
    repo.put_ref("fam", BASE_VARIABLES["fam"])
    code, v, _ = repo.check()
    assert code == 1 and v["items"] == ["fam:" + STATE]


def test_removed_manifest(repo):
    repo.write(G + "references/oth.manifest.json", None)
    code, v, _ = repo.check()
    assert reqs(v) == {"default", "changed", "loosened"} and v["items"] == ["oth:*"]


def test_changed_sigma_is_a_loosening(repo):
    repo.put_ref("fam", BASE_VARIABLES["fam"], sigma=SIGMA * 2)
    code, v, text = repo.check()
    assert reqs(v) == {"changed", "loosened"} and "stored sigma steady/sigma changed" in text


def test_store_kind_and_sketch_changes_are_loosenings():
    base = {"store": "sketch", "sketch": {"k": 8, "seed": 1}, "release": V1, "external": {}, "datasets": {},
            "guarded": {}, "unguarded": {}, "variables": {}}
    for head in (dict(base, store="full"), dict(base, sketch={"k": 4, "seed": 1})):
        found, _ = guard.diff_manifest("x", base, head, {})
        assert {f.req for f in found} == {"loosened"}


# ---------------------------------------------------------------- integrity and validity


def test_corrupt_release_asset(repo):
    _, h5 = repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.new": ("SENSITIVE", 5)}))
    bad = bytearray(h5)
    bad[len(bad) // 2] ^= 1
    repo.assets[V2][mf.asset_name(mf.reference_path("fam"))] = bytes(bad)
    code, v, text = repo.check()
    assert code == 1 and any("SHA-256" in e for e in v["errors"]), text


def test_missing_release_asset(repo):
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.new": ("SENSITIVE", 5)}), serve=False)
    code, v, _ = repo.check()
    assert code == 1 and any("not in release yldot-data-v2" in e for e in v["errors"])


def test_manifest_disagreeing_with_its_datasets(repo):
    def tamper(m):
        m["guarded"]["steady/default"] = "0" * 64

    repo.put_ref("fam", BASE_VARIABLES["fam"], edit=tamper)
    code, v, _ = repo.check("Default results: changed\nfam:steady/default")
    assert code == 1 and any("disagrees with its datasets" in e for e in v["errors"])


def test_dataset_sha_not_matching_the_file(repo):
    """The file is the published one, but the head manifest claims other data for one of its datasets."""
    def tamper(m):
        m["datasets"]["/index/block"] = "0" * 64

    repo.put_ref("fam", BASE_VARIABLES["fam"], edit=tamper)
    code, v, _ = repo.check("Default results: changed\nfam:index")
    assert code == 1 and any("/index/block" in e and "differs from the manifest" in e for e in v["errors"])


def test_null_release_with_changed_files(repo):
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.new": ("SENSITIVE", 5)}), release=None)
    code, v, _ = repo.check()
    assert code == 1 and any("release is null" in e for e in v["errors"]) and repo.download.calls == []


def test_invalid_tag_refused_before_download(repo):
    def tamper(m):
        m["release"] = "yldot-data-v2; rm -rf /"

    repo.put_ref("fam", BASE_VARIABLES["fam"], edit=tamper)
    code, v, _ = repo.check()
    assert code == 1 and any("release" in e for e in v["errors"]) and repo.download.calls == []


def test_invalid_head_manifest(repo):
    m = repo.manifest("oth")
    del m["provenance"]
    repo.write(G + "references/oth.manifest.json", json.dumps(m))
    code, v, _ = repo.check()
    assert code == 1 and any(e.startswith("oth:") for e in v["errors"])


def test_no_download_skips_the_asset_checks(repo):
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.new": ("SENSITIVE", 5)}))
    code, v, text = repo.check(no_download=True)
    assert code == 0 and "not downloaded (--no-download)" in text and repo.download.calls == []


# ---------------------------------------------------------------- declarations


@pytest.mark.parametrize("line, want", [
    ("Test criteria: changed: why", ("changed", "why")),
    ("- Test criteria: changed — why", ("changed", "why")),
    ("* **Test criteria: loosened** because", ("loosened", "because")),
    ("1. `Test criteria: changed` why", ("changed", "why")),
    ("> Default results: changed", ("default", "")),
    ("  + Default results: changed (see below)", ("default", "(see below)")),
    ("test criteria: changed: why", None),
    ("Test criteria: changedx", None),
    ("We say Test criteria: changed here", None),
])
def test_declaration_line(line, want):
    assert guard.declaration(line) == want


def test_justification_on_the_next_line():
    d = guard.parse_declarations("Test criteria: changed\n\n  the margins were measured again\n")
    assert d["changed"]["justification"] == "the margins were measured again"
    d = guard.parse_declarations("Test criteria: changed\nTest criteria: loosened: k\n")
    assert d["changed"]["justification"] == ""


def test_loosened_needs_changed_and_justifications(repo):
    repo.write(G + "harness/state.py", "x = 2\n")
    code, v, _ = repo.check("Test criteria: loosened: owner review")
    assert code == 1 and v["missing"] == ["Test criteria: changed"]
    code, v, _ = repo.check("Test criteria: changed\nTest criteria: loosened: owner review")
    assert code == 1 and v["missing"] == ["Test criteria: changed (with a justification)"]


def test_unneeded_declaration_is_a_note(repo):
    repo.write(G + "tools/fetch_data.py", "x = 2\n")
    code, v, text = repo.check("Test criteria: changed: tool\nDefault results: changed\n")
    assert code == 0 and "is declared but this change does not need it" in text


def test_items_named_before_the_declaration_do_not_count(repo):
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.sens": ("SENSITIVE", 9)}))
    code, v, _ = repo.check("fam:bbb.sens\nDefault results: changed\n")
    assert code == 1 and v["missing_items"] == ["fam:bbb.sens"]
    code, v, _ = repo.check("Default results: changed\nfam:bbb.sens=2\n")  # a longer id is not the item
    assert code == 1 and v["missing_items"] == ["fam:bbb.sens"]


def test_edited_description_rejudges_the_same_diff(repo, monkeypatch, capsys):
    """pull_request_target 'edited': the diff is unchanged, only PR_BODY differs."""
    repo.write(G + "tools/fetch_data.py", "x = 2\n")
    head = repo.commit()
    argv = ["check_reference_change.py", "check", "--base", repo.base, "--head", head, "--repo", str(repo.root)]
    monkeypatch.setenv("PR_BODY", "A refactor of the fetch tool.")
    assert guard.main(argv) == 1
    assert "missing: Test criteria: changed" in capsys.readouterr().out
    monkeypatch.setenv("PR_BODY", "A refactor of the fetch tool.\n\nTest criteria: changed: new --check output\n")
    assert guard.main(argv) == 0


def test_pr_body_unset(repo, monkeypatch):
    monkeypatch.delenv("PR_BODY", raising=False)
    lines = []
    argv = ["check_reference_change.py", "check", "--base", repo.base, "--head", repo.base, "--repo", str(repo.root)]
    assert guard.main(argv, out=lines.append) == 2 and "PR_BODY is not set" in lines[0]


def test_unknown_revision(repo):
    lines = []
    assert guard.check(repo.root, repo.base, "no-such-rev", "", out=lines.append) == 2
    assert "unknown revision" in lines[0]


def test_summary_and_json(repo, tmp_path):
    repo.write(G + "harness/state.py", "x = 2\n")
    summary = tmp_path / "summary.md"
    code, v, _ = repo.check(summary=summary)
    assert code == 1 and "**" + guard.CODEOWNER + "**" in summary.read_text()
    assert set(v) >= {"required", "present", "missing", "items", "codeowner_approval", "errors", "base", "head"}


# ---------------------------------------------------------------- history


class FakeGh:
    """run() stand-in for gh release list / view."""

    def __init__(self, sizes, fail=False):
        self.sizes, self.fail = sizes, fail

    def __call__(self, cmd):
        if self.fail:
            return 1, "", "HTTP 401"
        if cmd[:3] == ["gh", "release", "list"]:
            return 0, json.dumps([{"tagName": t} for t in self.sizes]), ""
        if cmd[:3] == ["gh", "release", "view"]:
            return 0, json.dumps({"assets": [{"size": s} for s in self.sizes[cmd[3]]]}), ""
        raise AssertionError(cmd)


def test_history(repo):
    lines = []
    gh = FakeGh({V1: [1_000_000, 500_000], V2: [2_000_000], "v8.1.0": [9_000_000_000]})
    assert guard.history(repo.root, repo.base, run=gh, out=lines.append) == 0
    text = "\n".join(lines)
    assert "data releases: 2 (3.50 MB in total" in text
    assert "yldot-data-v2: 2.00 MB (orphan" in text and "yldot-data-v1: 1.50 MB\n" in text + "\n"
    tracked = sum(int(line.split()[3]) for line in repo.git("ls-tree", "-r", "-l", repo.base, "--", G).splitlines())
    assert "{:.2f} MB in the tree".format(tracked / 1e6) in text


def test_history_limits(repo):
    lines = []
    gh = FakeGh({V1: [150_000_000], V2: [60_000_000]})
    assert guard.history(repo.root, repo.base, run=gh, out=lines.append) == 1
    assert any("exceed 200 MB" in line for line in lines)
    assert guard.history(repo.root, repo.base, run=FakeGh({V1: [1]}), git_limit_mb=1e-6, out=lines.append) == 1
    assert guard.history(repo.root, repo.base, run=FakeGh({}, fail=True), out=lines.append) == 2


# ---------------------------------------------------------------- round 1 of the review (AIUE-97)


def test_added_files_pytest_loads_below_mutations(repo):
    repo.write(G + "mutations/conftest.py", "import os\n")
    code, v, _ = repo.check()
    assert code == 1 and reqs(v) == {"changed", "loosened"} and v["codeowner_approval"]
    repo.write(G + "mutations/conftest.py", None)
    repo.write(G + "mutations/m02.patch", "diff\n")
    assert repo.check()[1]["required"] == []


PYPROJECT = '[project]\nname = "{}"\n\n[tool.pytest.ini_options]\naddopts = "{}"\n'
SETUPCFG = "[metadata]\nname = {}\n\n[tool:pytest]\naddopts = {}\n"


@pytest.mark.parametrize("path, base, head, loosened", [
    ("pyproject.toml", PYPROJECT.format("a", "-q"), PYPROJECT.format("b", "-q"), False),  # not a pytest section
    ("pyproject.toml", PYPROJECT.format("a", "-q"), PYPROJECT.format("a", "-x"), True),
    ("pyproject.toml", PYPROJECT.format("a", "-q"), '[project]\nname = "a"\n', True),  # section removed
    ("pyproject.toml", '[project]\nname = "a"\n', '[project]\nname = "a"\n[tool.pytest]\nx = 1\n', True),
    ("pyproject.toml", None, PYPROJECT.format("a", "-q"), True),  # added with a pytest section
    ("pyproject.toml", None, '[project]\nname = "a"\n', False),
    ("pyproject.toml", PYPROJECT.format("a", "-q"), "[project\n", True),  # does not parse
    ("pyproject.toml", "[project\n", PYPROJECT.format("a", "-q"), True),
    ("tests/pyproject.toml", PYPROJECT.format("a", "-q"), PYPROJECT.format("a", "-x"), True),
    ("setup.cfg", SETUPCFG.format("a", "-q"), SETUPCFG.format("b", "-q"), False),
    ("setup.cfg", SETUPCFG.format("a", "-q"), SETUPCFG.format("a", "-x"), True),
    ("setup.cfg", SETUPCFG.format("a", "-q"), "[metadata]\nname = a\n", True),
    ("setup.cfg", SETUPCFG.format("a", "-q"), "name = a\n", True),  # no section header: does not parse
    ("tests/setup.cfg", SETUPCFG.format("a", "-q"), SETUPCFG.format("a", "-x"), True),
])
def test_pytest_config_above_the_suite(repo, path, base, head, loosened):
    if base is not None:
        repo.write(path, base)
        repo.base = repo.commit("pytest config")
    repo.write(path, head)
    code, v, text = repo.check("Test criteria: changed: pytest config\nTest criteria: loosened: owner review")
    assert (reqs(v) == {"changed", "loosened"}) is loosened, text
    assert code == 0 and v["codeowner_approval"] is loosened


@pytest.mark.parametrize("name", ["pytest.toml", ".pytest.toml", ".pytest.ini"])
def test_root_pytest_config_file_is_a_loosening(repo, name):
    repo.write(name, "[pytest]\naddopts = -q\n")
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"changed", "loosened"} and v["codeowner_approval"], text
    assert repo.check("Test criteria: changed: config\nTest criteria: loosened: owner review")[0] == 0


@pytest.mark.parametrize("base, head", [
    ("[project\n", "[project\n[x\n"),  # unparsable on both sides: still not comparable
    ("[project\n", '[project]\nname = "a"\n'),  # unparsable side against no pytest section
    ('[project]\nname = "a"\n', "[project\n"),
    ("[project\n", "[project\n"),  # identical and unparsable
])
@pytest.mark.parametrize("path", ["pyproject.toml", "tests/pyproject.toml"])
def test_unparsable_pytest_config_is_a_loosening(repo, path, base, head):
    repo.write(path, base)
    repo.base = repo.commit("config")
    repo.write(path, head if head != base else base + "# touched\n")
    code, v, text = repo.check()
    assert reqs(v) == {"changed", "loosened"} and "does not parse" in text, text


@pytest.mark.parametrize("base, head", [("[metadata]\nname = a\n", "name = a\nx\n"),
                                        ("name = a\n", "name = a\nx\n"),
                                        ("name = a\n", "[metadata]\nname = a\n"),
                                        ("[metadata]\nname = a\n", "name = a\n")])
def test_unparsable_setup_cfg_is_a_loosening(repo, base, head):
    repo.write("setup.cfg", base)
    repo.base = repo.commit("config")
    repo.write("setup.cfg", head)
    code, v, text = repo.check()
    assert reqs(v) == {"changed", "loosened"} and "does not parse" in text, text


def test_only_the_d_of_a_variant_changes(repo):
    d = {"dtype": "float64", "shape": [], "data": 0.5}
    repo.put_ref("fam", BASE_VARIABLES["fam"], release=V1,
                 edit=lambda m: m["variables"]["bbb.sens"].update(d=d))
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"default"} and v["items"] == ["fam:bbb.sens"], text
    assert "variant bbb.sens changed: d" in text
    assert repo.check("Default results: changed\n- fam:bbb.sens")[0] == 0


def test_only_the_datasets_of_a_manifest_change_reverifies_the_externals(repo):
    """Same release, same external entries: a changed dataset set alone still downloads and verifies the reference."""
    m0 = repo.manifest("fam")
    m, _ = repo.put_ref("fam", BASE_VARIABLES["fam"], release=V1, default=Y * (1 + 1e-6),
                 edit=lambda mm: mm["external"].update(m0["external"]))  # the old external entries, new datasets
    assert m["release"] == m0["release"] and m["datasets"] != m0["datasets"]
    code, v, text = repo.check()
    ref = mf.asset_name(mf.reference_path("fam"))
    assert any(ref in e for e in v["errors"]), text  # the served reference is not the one the old entry describes
    assert repo.download.calls and repo.download.calls[0][0] == V1
    assert mf.asset_name(mf.reference_path("fam")) in repo.download.calls[0][1]


def test_stale_base_is_read_at_the_merge_base(repo):
    """The base moved on after the PR branched: its manifests and guarded files are not charged to the PR."""
    root = repo.base
    repo.git("checkout", "-q", "-b", "pr")
    repo.put_ref("fam", BASE_VARIABLES["fam"], release=V1, diag={"resco": np.arange(4.0) + 1.0})
    pr_head = repo.commit("pr: diagnostics only")
    repo.git("checkout", "-q", "main")
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.new": ("SENSITIVE", 5)}), release=V1, serve=False)
    repo.write(G + "tools/fetch_data.py", "x = 3\n")
    tip = repo.commit("base moves on")
    lines = []
    out = repo.scratch / "stale.json"
    assert guard.check(repo.root, tip, pr_head, "", download=repo.download, json_out=out, out=lines.append) == 0, lines
    text = "\n".join(lines)
    assert "base {}, merge base {}".format(tip[:12], root[:12]) in text
    assert json.loads(out.read_text())["required"] == [] and "fetch_data" not in text and "bbb.new" not in text
    assert json.loads(out.read_text())["merge_base"] == root


def test_no_common_ancestor(repo):
    repo.git("checkout", "-q", "--orphan", "other")
    repo.write("README.md", "other\n")
    other = repo.commit("unrelated history")
    lines = []
    assert guard.check(repo.root, repo.base, other, "", out=lines.append) == 2 and "no merge base" in lines[0]


# dataset, rename, release and external rules


def manifest_dict(datasets, **kw):
    return dict({"store": "full", "release": V1, "external": {}, "datasets": datasets, "guarded": {}, "unguarded": {},
                 "variables": {}}, **kw)


def test_changed_unguarded_dataset_is_a_default_result():
    base = manifest_dict({"/index/block": "a", "/other/x": "b", "/steady/default/diagnostics/r": "c",
                          "/steady/variants/v/yldot/index": "d"})
    head = manifest_dict({"/index/block": "A", "/other/x": "B", "/steady/default/diagnostics/r": "C",
                          "/steady/variants/v/yldot/index": "D"})
    found, _ = guard.diff_manifest("fam", base, head, {})
    assert sorted((f.req, f.item) for f in found) == [("default", "fam:/other/x"), ("default", "fam:index")]
    found, _ = guard.diff_manifest("fam", base, manifest_dict({}), {})  # all removed
    assert {f.item for f in found if f.req == "default"} == {"fam:/other/x", "fam:index"}


def test_changed_index_in_a_pr(repo):
    def tamper(m):
        m["datasets"]["/index/block"] = "0" * 64

    repo.put_ref("fam", BASE_VARIABLES["fam"], edit=tamper, release=V1)
    code, v, _ = repo.check("Default results: changed\nfam:index")
    assert v["items"] == ["fam:index"] and v["missing_items"] == []


def two_manifests(tmp_path, seed=1):
    m0, _ = make_ref(tmp_path, "fam", {"bbb.sens": ("SENSITIVE", 1)})
    m1, _ = make_ref(tmp_path, "fam", {"bbb.renamed": ("SENSITIVE", seed)})
    return m0, m1


def same(m0, m1, **edits):
    va, vb = m0["variables"]["bbb.sens"], dict(m1["variables"]["bbb.renamed"], **edits)
    return guard.same_entry(m0, "bbb.sens", va, m1, "bbb.renamed", vb)


@pytest.mark.parametrize("field, value", [
    ("class", "INERT"), ("applied", APPLIED), ("d", 1.0), ("phase", "POST"), ("config", "timestep"),
    ("block_l2", {"x": 1.0}), ("jflag_block_l2", {"x": 1.0})])
def test_rename_needs_every_field_to_agree(tmp_path, field, value):
    m0, m1 = two_manifests(tmp_path)
    assert same(m0, m1) and same(m0, m1, reason="other words", sha256="0" * 64)
    assert not same(m0, m1, **{field: value})


def test_rename_needs_the_same_stored_datasets(tmp_path):
    m0, m1 = two_manifests(tmp_path)
    stored_keys = [k for k in m1["datasets"] if k.startswith("/steady/variants/bbb.renamed/")]
    assert stored_keys
    m1["datasets"][stored_keys[0]] = "0" * 64
    assert not same(m0, m1)


def test_rename_refused_when_the_stored_datasets_differ(repo):
    variables = {k: c for k, c in BASE_VARIABLES["fam"].items() if k != "bbb.sens"}
    repo.put_ref("fam", dict(variables, **{"bbb.renamed": ("SENSITIVE", 7)}))
    code, v, _ = repo.check()
    assert code == 1 and v["items"] == ["fam:bbb.sens"]


def test_release_change_alone_reverifies_every_external(repo):
    repo.put_ref("fam", BASE_VARIABLES["fam"], release=V2)
    code, v, text = repo.check()
    assert code == 0 and v["required"] == [], text
    assert repo.download.calls == [(V2, sorted(mf.asset_name(p) for p in (mf.reference_path("fam"), STATE)))]


def test_new_external_file_is_an_addition_and_verified(repo):
    extra, content = "families/fam/extra.bin", b"extra" * 5
    ext = dict(external(repo.files[STATE]), **{extra: {"sha256": hashlib.sha256(content).hexdigest(),
                                                       "bytes": len(content)}})
    repo.put_ref("fam", BASE_VARIABLES["fam"], release=V1, external=ext)
    repo.assets[V1][mf.asset_name(extra)] = content
    code, v, text = repo.check()
    assert code == 0 and v["required"] == [] and "addition: external {}".format(extra) in text, text
    assert repo.download.calls == [(V1, [mf.asset_name(extra)])]  # the reference and the state are unchanged
    repo.assets[V1][mf.asset_name(extra)] = b"other" * 5  # same size, other bytes
    code, v, _ = repo.check()
    assert code == 1 and any(mf.asset_name(extra) in e and "SHA-256" in e for e in v["errors"])


def test_moved_guarded_file_is_a_delete_and_an_add(repo):
    repo.git("mv", G + "families/fam/input.py", G + "families/fam/input2.py")
    code, v, _ = repo.check()
    got = {(f["path"], f["req"]) for f in v["findings"]}
    assert got == {(G + "families/fam/input.py", "loosened"), (G + "families/fam/input2.py", "changed")}
    assert reqs(v) == {"changed", "loosened"}


def test_fetch_error_is_an_error(repo):
    def failing(tag, names, dest, gh_repo):
        raise fetch_data.FetchError("gh failed: boom")

    repo.download = failing
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.new": ("SENSITIVE", 5)}))
    code, v, _ = repo.check()
    assert code == 1 and any("fam: gh failed: boom" == e for e in v["errors"])


def test_manifest_family_must_be_its_file_name(repo):
    m = {"schema": mf.SCHEMA, "family": "zzz", "store": "sketch", "release": V1, "external": {}}
    assert "names family 'zzz'" in guard.load_manifest(json.dumps(m).encode(), "oth")[1]
    repo.write(G + "references/oth.manifest.json", json.dumps(m))
    code, v, _ = repo.check()
    assert code == 1 and any(e.startswith("oth:") and "names family" in e for e in v["errors"])


@pytest.mark.parametrize("wrong", [b"state-1" * 8 + b"x", b"state-9" * 8])  # a longer file, same size other bytes
def test_external_file_must_match_the_manifest_entry(repo, wrong):
    """The datasets are right, the owner state file served is not: only fetch_data.matches notices."""
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.new": ("SENSITIVE", 5)}))
    repo.assets[V2][mf.asset_name(STATE)] = wrong
    code, v, _ = repo.check()
    assert code == 1 and any(mf.asset_name(STATE) in e and ("bytes" in e or "SHA-256" in e) for e in v["errors"])


def test_external_file_over_the_size_limit_is_refused_before_download(repo):
    def huge(m):
        m["external"][STATE]["bytes"] = 300 * 10**6

    repo.put_ref("fam", BASE_VARIABLES["fam"], edit=huge)
    code, v, _ = repo.check()
    assert code == 1 and any(STATE in e and "over the 200 MB limit" in e for e in v["errors"])
    assert repo.download.calls == [(V2, [mf.asset_name(mf.reference_path("fam"))])]


def test_external_only_reference_entry_is_judged_without_datasets(repo):
    ref = mf.reference_path("own")

    def own(sha):
        return json.dumps({"schema": mf.SCHEMA, "family": "own", "store": "sketch", "release": V1,
                           "external": {ref: {"sha256": sha * 64, "bytes": 1}}})

    repo.write(G + "references/own.manifest.json", own("a"))
    repo.base = repo.commit("external-only manifest")
    repo.write(G + "references/own.manifest.json", own("b"))
    code, v, _ = repo.check(no_download=True)
    assert code == 1 and v["items"] == ["own:" + ref]


# checks of a downloaded reference file


def ref_file(tmp_path, kind):
    p = tmp_path / "{}-{}.h5".format(kind, next(COUNTER))
    w = store.create(p, kind, "fam", DATA, IMAP)
    for config in mf.CONFIG_NAMES:
        w.write_default(config, Y, YJ, SIGMA, DIAG)
        if kind == "sketch":
            w.write_sketch_thresholds(config, THR)
    out = w.finish()
    m = {"family": "fam", "store": kind, "datasets": out["datasets"]}
    if kind == "sketch":
        m["sketch"] = {"k": store.K, "seed": store.SEED}
    return p, m


@pytest.mark.parametrize("kind", ["full", "sketch"])
def test_check_h5_accepts_the_file_it_describes(tmp_path, kind):
    p, m = ref_file(tmp_path, kind)
    assert guard.check_h5(p, m) == []


def test_check_h5_dataset_set(tmp_path):
    p, m = ref_file(tmp_path, "full")
    extra = dict(m, datasets={k: v for k, v in m["datasets"].items() if k != "/index/block"})
    missing = dict(m, datasets=dict(m["datasets"], **{"/zzz/not_in_the_file": "0" * 64}))
    assert any("not in the manifest ['/index/block']" in x for x in guard.check_h5(p, extra))
    assert any("not the file ['/zzz/not_in_the_file']" in x for x in guard.check_h5(p, missing))
    wrong = dict(m, datasets=dict(m["datasets"], **{"/index/block": "0" * 64}))
    assert any("SHA-256 differs" in x and "/index/block" in x for x in guard.check_h5(p, wrong))


def test_check_h5_root_attributes(tmp_path):
    p, m = ref_file(tmp_path, "full")
    for edit in ({"family": "zzz"}, {"store": "sketch", "sketch": {"k": store.K, "seed": store.SEED}}):
        assert any("root attributes" in x for x in guard.check_h5(p, dict(m, **edit)))


def test_check_h5_sketch_parameters(tmp_path):
    p, m = ref_file(tmp_path, "sketch")
    for sketch in ({"k": store.K + 1, "seed": store.SEED}, {"k": store.K, "seed": store.SEED + 1}, None):
        bad = dict(m, sketch=sketch)
        assert any("k/seed" in x for x in guard.check_h5(p, bad)), sketch


# the numeric and text rules


@pytest.mark.parametrize("a, b, want", [
    (3.0, 2.0, "changed"), (3.0, 3.5, "loosened"), (None, 3.0, "changed"), (3.0, None, "loosened"),
    (3.0, math.nan, "loosened"), (math.nan, 3.0, "loosened"), (3.0, math.inf, "loosened"),
    (math.inf, 3.0, "loosened"), (None, math.nan, "loosened"), (3.0, "x", "loosened"), (True, 2.0, "loosened")])
def test_monotone(a, b, want):
    assert guard.monotone(a, b) == want


def test_non_finite_tolerance_is_a_loosening():
    assert {r for r, _ in guard.diff_tolerances(tol(), tol(rule__k=math.nan))} == {"loosened"}
    assert {r for r, _ in guard.diff_tolerances(tol(), tol(rtol__te=math.inf))} == {"loosened"}


def test_strip_noise():
    s = guard.strip_noise
    assert s("a\n<!--\nTest criteria: changed: x\n-->\nb") == "a\n\nb"
    assert s("a <!-- one --> b <!-- two --> c") == "a  b  c"
    assert s("a\n<!-- never closed\nTest criteria: changed: x") == "a"
    assert s("a\n```\nTest criteria: changed: x\n```\nb") == "a\nb"
    assert s("a\n~~~sh\nTest criteria: changed: x\n~~~\nb") == "a\nb"
    assert s("a\n````\n```\nTest criteria: changed: x\n````\nb") == "a\nb"  # a shorter fence does not close
    assert s("a\n```\nTest criteria: changed: x") == "a"  # never closed
    assert s("a\n  ```\nx\n  ```\nb") == "a\nb"
    assert s("keep `inline` code and ``` mid-line") == "keep `inline` code and ``` mid-line"


@pytest.mark.parametrize("body", [
    "<!--\nTest criteria: changed: because\n-->",
    "```\nTest criteria: changed: because\n```",
    "~~~\nTest criteria: changed: because\n~~~",
    "<!-- Test criteria: changed: because -->",
    "```\nunclosed fence\nTest criteria: changed: because"])
def test_declarations_in_comments_and_fences_do_not_count(repo, body):
    repo.write(G + "tools/fetch_data.py", "x = 2\n")
    code, v, _ = repo.check(body)
    assert code == 1 and v["missing"] == ["Test criteria: changed"]


def test_declaration_after_a_comment_counts(repo):
    repo.write(G + "tools/fetch_data.py", "x = 2\n")
    assert repo.check("<!-- template hint -->\n\nTest criteria: changed: really\n")[0] == 0


def test_items_in_a_comment_do_not_count(repo):
    repo.put_ref("fam", dict(BASE_VARIABLES["fam"], **{"bbb.sens": ("SENSITIVE", 9)}))
    code, v, _ = repo.check("Default results: changed\n<!-- fam:bbb.sens -->\n```\nfam:bbb.sens\n```")
    assert code == 1 and v["missing_items"] == ["fam:bbb.sens"]


# control characters


def test_control_characters_are_escaped(repo):
    assert guard.clean("a\nb\r\x1b[0m\x7f\x00 ok\t") == "a\\x0ab\\x0d\\x1b[0m\\x7f\\x00 ok\\x09"
    repo.write(G + "data/a\n::warning::x.txt", "1")
    code, v, text = repo.check()
    assert code == 1 and all("\n" not in line and "\r" not in line for line in repo.lines)
    assert "a\\x0a::warning::x.txt" in text and not any(line.startswith("::") for line in repo.lines)


def test_control_characters_in_the_summary():
    v = guard.judge([guard.Finding("default", "p", "w", "fam:a\n::warning::b")], ["bad\n::error::x"], "Default results: changed")
    md = guard.summary_md(v)
    assert not any(line.startswith("::") for line in md.splitlines()) and "a\\x0a::warning::b" in md
    assert "bad\\x0a::error::x" in md


# an invalid manifest at the base


def invalid_oth(repo):
    m = repo.manifest("oth")
    del m["provenance"]
    repo.write(G + "references/oth.manifest.json", json.dumps(m))
    repo.base = repo.commit("oth is invalid at the base")


def test_invalid_base_manifest_does_not_fail_other_prs(repo):
    invalid_oth(repo)
    repo.put_ref("fam", BASE_VARIABLES["fam"], release=V1, diag={"resco": np.arange(4.0) + 1.0})
    code, v, text = repo.check()
    assert code == 0 and v["errors"] == [] and v["required"] == [], text


def test_pr_repairing_an_invalid_base_manifest_declares_it(repo):
    invalid_oth(repo)
    repo.put_ref("oth", BASE_VARIABLES["oth"], release=V1)
    code, v, text = repo.check()
    assert code == 1 and reqs(v) == {"default"} and v["items"] == ["oth:*"] and v["errors"] == []
    assert "base manifest is invalid" in text
    assert repo.check("Default results: changed\noth:*")[0] == 0


# history


def test_history_counts_every_blob_of_the_history(repo):
    for byte in (b"a", b"b", b"c"):
        repo.write(G + "data/big.bin", byte * 1_000_000)
        head = repo.commit("big " + byte.decode())
    lines = []
    assert guard.history(repo.root, head, run=FakeGh({V1: [1]}), out=lines.append) == 0
    tree = sum(int(x.split()[3]) for x in repo.git("ls-tree", "-r", "-l", head, "--", G).splitlines())
    first = sum(int(x.split()[3]) for x in repo.git("ls-tree", "-r", "-l", repo.base, "--", G).splitlines())
    want = first + 3_000_000  # every other file once, plus the three versions of big.bin
    text = "\n".join(lines)
    assert "{:.2f} MB in the tree".format(tree / 1e6) in text
    assert "{:.2f} MB of blobs in its history".format(want / 1e6) in text
    assert "{:.2f}".format(tree / 1e6) != "{:.2f}".format(want / 1e6)


def test_history_git_cap_is_30_mb(repo):
    repo.write(G + "data/big.bin", b"\0" * 29_000_000)
    ok = repo.commit("29 MB")
    assert guard.history(repo.root, ok, run=FakeGh({V1: [1]}), out=[].append) == 0
    repo.write(G + "data/big.bin", b"\0" * 31_000_000)
    over = repo.commit("31 MB")
    lines = []
    assert guard.history(repo.root, over, run=FakeGh({V1: [1]}), out=lines.append) == 1
    assert any("exceeds 30 MB" in line for line in lines)


def test_history_of_a_rev_without_suite_files(repo):
    repo.git("checkout", "-q", "--orphan", "bare")
    repo.git("rm", "-rfq", ".")
    repo.write("README.md", "bare\n")
    bare = repo.commit("no tests/yldot")
    lines = []
    assert guard.history(repo.root, bare, run=FakeGh({V1: [1]}), out=lines.append) == 0
    text = "\n".join(lines)
    assert "0.00 MB of blobs" in text and "orphan" in text


def test_history_invalid_manifest_makes_orphans_uncertain(repo):
    invalid_oth(repo)
    lines = []
    gh = FakeGh({V1: [1_000_000], V2: [2_000_000]})
    assert guard.history(repo.root, repo.base, run=gh, out=lines.append) == 1
    text = "\n".join(lines)
    assert "error: manifest at {} is invalid: oth:".format(repo.base[:12]) in text
    assert "yldot-data-v2: 2.00 MB (uncertain" in text and "orphan" not in text


def test_history_output_is_escaped(repo):
    lines = []

    def failing(cmd):
        return 1, "", "HTTP 401\n::error::injected"

    assert guard.history(repo.root, repo.base, run=failing, out=lines.append) == 2
    assert lines == ["error: gh release list failed: HTTP 401\\x0a::error::injected"]
