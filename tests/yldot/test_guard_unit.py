"""Unit tests of tools/check_reference_change.py, the reference guard (AIUE-97; PRD section 7.6; owner decisions of
2026-10-22 on the AIUE-97 ticket page): the path classes, the tolerances.toml, overrides.toml, family.toml and manifest
rules, the declarations (including the edited case: the same diff judged again with a new description), the
release-asset and dataset checks, and history. Each test commits a base and a head into a scratch git repository;
the release downloads and gh are fakes. No uedge import, no network.
"""
import hashlib
import itertools
import json
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


def make_ref(where, family, variables, release=V1, default=Y, sigma=SIGMA, diag=DIAG, external=None, applied=None):
    """(manifest, .h5 bytes) of a full-store reference; variables {id: (class, seed)}, the SENSITIVE ones stored."""
    p = Path(where) / "{}-{}.h5".format(family, next(COUNTER))
    w = store.create(p, "full", family, DATA, IMAP)
    for config in mf.CONFIG_NAMES:
        w.write_default(config, default, YJ + (default - Y), sigma, diag)
    for vid, (cls, seed) in sorted(variables.items()):
        if cls == "SENSITIVE":
            w.write_variant("steady", vid, variant(seed), variant(seed) + (YJ - Y))
    out = w.finish()
    guarded, unguarded = mf.summarize(out["datasets"])
    entries = {}
    for vid, (cls, seed) in variables.items():
        sens = cls == "SENSITIVE"
        entries[vid] = {"class": cls, "reason": "r", "applied": (applied or {}).get(vid), "d": None, "phase": "PRE",
                        "config": "steady", "sha256": mf.variant_sha(out["datasets"], "steady", vid) if sens else None,
                        "block_l2": store.block_l2(variant(seed) - Y, LABELS, ROWS) if sens else {},
                        "jflag_block_l2": {}}
    m = {"schema": mf.SCHEMA, "family": family, "store": "full", "release": release,
         "external": dict({mf.reference_path(family): {"sha256": out["sha256"], "bytes": out["bytes"]}},
                          **(external or {})),
         "datasets": out["datasets"], "guarded": guarded, "unguarded": unguarded,
         "provenance": {k: "x" for k in mf.PROVENANCE}, "variables": entries}
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
        return json.loads((self.root / G / "references" / "{}.manifest.json".format(family)).read_text())

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
        lines = []
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
    ("tests/deterministic_omp/harness/serial_check.py", "M", None),
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
