"""tools/make_references.py (AIUE-88, AIUE-94; PRD sections 7.2, 7.3 and 7.6): the child side evaluates d_only in
fresh child processes and writes the same bytes twice, its files open through open_store; a short variant sweep
gives each class as probed, --only keeps every other entry bit for bit, a second run that differs is INVALID
"nondeterministic"; classify on synthetic results; the host side's refusals, the exact git and docker commands of the
Linux path, the host path's preview (release null), the caps, and the manifests in references/ that hold data.
The child tests need the built uedge (in the Runner's children); git, docker, pip and the container are fakes here,
the real Linux run is the ticket's validation.
"""
import hashlib
import json
import os
import shutil
import sys
import tomllib
from argparse import Namespace
from pathlib import Path

import h5py
import numpy as np
import pytest

from yldot.harness import FAMILIES, Result, compare, locality, open_store
from yldot.harness import manifest as mf
from yldot.harness.store import file_sha256

SUITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SUITE / "tools"))

import make_references as mr  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
TAG = "yldot-data-v2"
IMAGE_ID = "sha256:2f833938356ea6ff6419467e99087103d2a32123d2e4a9bf0beab1145d20cf51"


@pytest.fixture(scope="module")
def children(tmp_path_factory):
    """Two child runs of d_only, each with its own build record and output directory."""
    out = []
    for run in ("1", "2"):
        d = tmp_path_factory.mktemp("child" + run)
        (d / "build.json").write_text(json.dumps({"commit": SHA, "compiler": "gfortran (test)",
                                                  "runner_image": "test image"}))
        mr.child(["d_only"], d / "references", d / "build.json", sweep="none")
        out.append(d)
    return out


# the probed classes of d_only (AIUE-94 planning sweep, .claude/work/AIUE-94/probes/full_d_only.txt, and a smoke run)
SWEEP = {"bbb.cfvisx": "SENSITIVE", "bbb.isbcwdt": "SENSITIVE", "bbb.xlinc": "INERT", "bbb.lgvmax": "MARGINAL",
         "bbb.isnion": "INVALID", "bbb.isphiofft": "INVALID", "bbb.methe=33": "EXCLUDED", "bbb.jxsori": "EXCLUDED",
         "com.chgstate_format": "EXCLUDED", "com.geometry": "EXCLUDED"}


def build_record(d):
    (d / "build.json").write_text(json.dumps({"commit": SHA, "compiler": "gfortran (test)",
                                              "runner_image": "test image"}))
    return d / "build.json"


@pytest.fixture(scope="module")
def swept(tmp_path_factory):
    """Two child runs of d_only over the SWEEP variants."""
    out = []
    for run in ("1", "2"):
        d = tmp_path_factory.mktemp("swept" + run)
        mr.child(["d_only"], d / "references", build_record(d), sweep=list(SWEEP))
        out.append(d)
    return out


def tmp_suite(tmp_path, families=("d_only",)):
    """A suite with the named families (input.py and family.toml; sigma.h5 if they have one), tolerances.toml,
    linux/Dockerfile and an empty references/."""
    suite = tmp_path / "tests" / "yldot"
    for name in families:
        d = suite / "families" / name
        d.mkdir(parents=True)
        for f in ("input.py", "family.toml", "sigma.h5"):
            if (FAMILIES / name / f).is_file():
                shutil.copyfile(FAMILIES / name / f, d / f)
    (suite / "references").mkdir()
    (suite / "linux").mkdir()
    shutil.copyfile(SUITE / "tolerances.toml", suite / "tolerances.toml")
    shutil.copyfile(SUITE / "linux" / "Dockerfile", suite / "linux" / "Dockerfile")
    return suite


class FakeRun:
    """run() stand-in for git, docker and gfortran."""

    def __init__(self, diff=0, status="", image=0):
        self.diff, self.status, self.image = diff, status, image
        self.calls = []

    def __call__(self, cmd, cwd=None):
        self.calls.append(cmd)
        if cmd[0] == "git" and cmd[3:5] == ["rev-parse", "--verify"]:
            return 0, SHA + "\n", ""
        if cmd[0] == "git" and cmd[3:5] == ["diff", "--quiet"]:
            return self.diff, "", ""
        if cmd[0] == "git" and cmd[3] == "status":
            return 0, self.status, ""
        if cmd[0] == "git" and cmd[3] in ("archive", "worktree"):
            return 0, "", ""
        if cmd[:3] == ["docker", "image", "inspect"]:
            return self.image, IMAGE_ID + "\n" if self.image == 0 else "", ""
        if cmd[0] == "gfortran":
            return 0, "GNU Fortran (test) 15.0\n", ""
        raise AssertionError(cmd)


class FakeStream:
    """stream() stand-in: the container or the host child 'writes' the files of a real child run."""

    def __init__(self, child_dir, fail=None):
        self.child_dir, self.fail = child_dir, fail
        self.calls = []
        self.envs = []  # the env of each call, in the order of calls

    def __call__(self, cmd, cwd=None, env=None, log=None):
        self.calls.append((cmd, cwd, log))
        self.envs.append(env)
        if self.fail and self.fail in cmd:
            return 1
        out = None
        if cmd[0] == "docker":
            out = Path(cmd[cmd.index("-v", 6) + 1].rsplit(":", 1)[0]) / "references"
        elif "_child" in cmd:
            out = Path(cmd[cmd.index("--out") + 1])
        if out is not None:
            shutil.copytree(self.child_dir / "references", out)
        return 0


def args(**kw):
    a = {"from_commit": "HEAD", "platform": "linux", "release": TAG, "out": None, "write": False, "family": [],
         "defaults_only": False, "only": None, "full": False}
    a.update(kw)
    return Namespace(**a)


def test_child_writes_the_same_bytes_twice(children):
    a, b = (d / "references" for d in children)
    assert file_sha256(a / "d_only.h5") == file_sha256(b / "d_only.h5")
    ja, jb = (mf.loads((d / "d_only.json").read_text()) for d in (a, b))
    for j in (ja, jb):
        j["provenance"].pop("date")
    assert ja == jb
    assert ja["provenance"]["commit"] == SHA and ja["provenance"]["flags"] == "--serial" and ja["variables"] == {}


def test_child_files_open_and_hold_the_defaults(tmp_path, children):
    suite = tmp_suite(tmp_path)
    out = children[0]
    mr.install(mr.assemble(SHA, ["d_only"], out, TAG)[0], out, suite)
    m = mf.load("d_only", suite)
    assert m["release"] == TAG and m["store"] == "full"
    assert set(m["guarded"]) == {"steady/default", "steady/sigma", "timestep/default", "timestep/sigma",
                                 "locality/steady"}  # d_only has [locality] (AIUE-100)
    with h5py.File(FAMILIES / "d_only" / "sigma.h5", "r") as f:
        sig = {c: f[c]["sigma"][()] for c in mf.CONFIG_NAMES}
    with open_store("d_only", suite) as s:
        for c in mf.CONFIG_NAMES:
            assert np.array_equal(s.sigma(c), sig[c])
            assert s.diagnostics(c)
        assert (s.default("timestep") != s.default("steady")).any()  # the time-step term is exercised
        assert not s.jflag("steady").any()  # no flag-gated branch active in steady (family.toml [history])
        delta, e = s.locality("steady")
        assert delta == locality.load_config(FAMILIES / "d_only")["delta_loc"] and s.locality("timestep") is None
        tol = tomllib.loads((SUITE / "tolerances.toml").read_text())
        t = compare.tolerances(s.default("steady"), s.sigma("steady"), tol["rtol"], tol["rule"]["k"], s.imap).tol
        assert len(e) and (locality.scores(e, t, locality.rtol_rows(tol["rtol"], s.imap)) > 1).all()  # band entries


def test_generate_linux_commands_and_write(tmp_path, children):
    suite = tmp_suite(tmp_path)
    run = FakeRun(status="?? tests/yldot/references/d_only.h5\n!! tests/yldot/.data/yldot-data-v1/x.h5\n"
                         "!! tests/yldot/families/imp7/gridue.hdf5\n!! tests/yldot/families/d_only/__pycache__/a.pyc\n")
    stream = FakeStream(children[0])
    out = tmp_path / "gen"
    mr.generate(args(out=str(out), write=True), suite, run, stream)
    archive = [c for c in run.calls if c[3:4] == ["archive"]]
    assert archive == [["git", "-C", str(suite.parents[1]), "archive", "--format=tar", "-o", str(out / "src.tar"),
                        SHA]]
    runner_image = "yldot-linux:24.04 {} ({})".format(IMAGE_ID, mr.base_image(SUITE))
    assert runner_image.endswith("(ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55)")
    assert [c for c, _, _ in stream.calls] == [[
        "docker", "run", "--rm", "--platform", "linux/amd64", "-v", "{}:/tests:ro".format(suite.parent),
        "-v", "{}:/out".format(out), "yldot-linux:24.04", "bash", "/tests/yldot/linux/generate.sh", SHA, runner_image,
        "d_only"]]
    m = mf.load("d_only", suite)
    assert m["release"] == TAG
    assert m["external"] == {"references/d_only.h5": {"sha256": file_sha256(out / "references" / "d_only.h5"),
                                                      "bytes": (out / "references" / "d_only.h5").stat().st_size}}
    assert file_sha256(suite / "references" / "d_only.h5") == m["external"]["references/d_only.h5"]["sha256"]


def test_generate_without_write_changes_nothing(tmp_path, children):
    suite = tmp_suite(tmp_path)
    mr.generate(args(out=str(tmp_path / "gen")), suite, FakeRun(), FakeStream(children[0]))
    assert list((suite / "references").iterdir()) == []


def test_generate_replaces_a_fetched_link(tmp_path, children):
    suite = tmp_suite(tmp_path)
    cache = tmp_path / "cache.h5"
    cache.write_bytes(b"fetched")
    (suite / "references" / "d_only.h5").symlink_to(cache)
    mr.generate(args(out=str(tmp_path / "gen"), write=True), suite, FakeRun(), FakeStream(children[0]))
    assert not (suite / "references" / "d_only.h5").is_symlink() and cache.read_bytes() == b"fetched"


def test_host_is_a_preview(tmp_path, children):
    suite = tmp_suite(tmp_path)
    run, stream = FakeRun(), FakeStream(children[0])
    out = tmp_path / "gen"
    mr.generate(args(platform="host", release=None, out=str(out), write=True), suite, run, stream)
    assert mf.load("d_only", suite)["release"] is None
    assert json.loads((out / "build.json").read_text())["runner_image"].endswith("(preview)")
    build = [(c, cwd, log) for c, cwd, log in stream.calls if "--no-build-isolation" in c]
    assert build == [([str(out / "venv" / "bin" / "python"), "-m", "pip", "install", "-v", "--no-build-isolation",
                       "--no-deps", ".", "-C", "--build-option=--serial"], out / "src", out / "build.log")]
    # PWD names the scratch tree for the build only (setup.py before AIUE-163 converted in $PWD); the child keeps
    # the caller's
    envs = {("build" if "--no-build-isolation" in c else "child" if "_child" in c else "other"): e
            for (c, _, _), e in zip(stream.calls, stream.envs)}
    assert envs["build"]["PWD"] == str(out / "src")
    assert envs["child"].get("PWD") == os.environ.get("PWD")
    assert run.calls[-1] == ["git", "-C", str(suite.parents[1]), "worktree", "remove", "--force", str(out / "src")]


def test_host_removes_its_worktree_after_a_failed_build(tmp_path, children):
    suite = tmp_suite(tmp_path)
    run = FakeRun()
    with pytest.raises(mr.Stop) as e:
        mr.generate(args(platform="host", release=None, out=str(tmp_path / "gen")), suite, run,
                    FakeStream(children[0], fail="--no-build-isolation"))
    assert e.value.code == 2 and "build failed" in str(e.value)
    assert run.calls[-1][3:5] == ["worktree", "remove"]


@pytest.mark.parametrize("kw, run, code, message", [
    ({"platform": "host"}, FakeRun(), 1, "previews only"),
    ({"release": "v2"}, FakeRun(), 2, "need yldot-data-v<N>"),
    ({}, FakeRun(diff=1), 1, "differs from"),
    ({}, FakeRun(status="?? tests/yldot/families/d_only/new.py\n"), 1, "holds files"),
    ({}, FakeRun(status="!! tests/yldot/families/d_only/stray.h5\n"), 1, "holds files"),
    ({}, FakeRun(status="!! tests/yldot/data/stray.dat\n"), 1, "holds files"),
    ({}, FakeRun(image=1), 1, "docker build --platform linux/amd64 -t yldot-linux:24.04 tests/yldot/linux"),
    ({"family": ["imp7"]}, FakeRun(), 1, "no sigma.h5"),
    ({"family": ["nosuch"]}, FakeRun(), 1, "no such family"),
])
def test_refusals(tmp_path, children, kw, run, code, message):
    suite = tmp_suite(tmp_path, ("d_only", "imp7"))
    (suite / "families" / "imp7" / "sigma.h5").unlink(missing_ok=True)  # imp7 here: a family without sigma.h5
    stream = FakeStream(children[0])
    with pytest.raises(mr.Stop) as e:
        mr.generate(args(out=str(tmp_path / "gen"), **kw), suite, run, stream)
    assert e.value.code == code and message in str(e.value)
    assert not stream.calls


def test_refuses_a_changed_sigma(tmp_path):
    suite = tmp_suite(tmp_path)
    with h5py.File(suite / "families" / "d_only" / "sigma.h5", "a") as f:
        f["steady"]["sigma"][0] += 1.0
    with pytest.raises(mr.Stop, match="differs from tolerances.toml"):
        mr.select([], suite)


def test_refuses_a_family_with_another_familys_release_assets(tmp_path):
    suite = tmp_suite(tmp_path)
    m = {"schema": 1, "family": "d_only", "store": "full", "release": "yldot-data-v1",
         "external": {"families/other/gridue": {"sha256": "0" * 64, "bytes": 1}}}
    mf.dump(m, mf.path("d_only", suite))
    with pytest.raises(mr.Stop, match="release assets of other families"):
        mr.select(["d_only"], suite)


GRID = b"an owner family's grid"


def make_owner(suite, content=GRID):
    """d_only as an owner family (AIUE-92): its manifest names a grid under families/d_only/ as a release asset, and
    the working tree holds that grid with the given content."""
    (suite / "families" / "d_only" / "gridue").write_bytes(content)
    m = {"schema": 1, "family": "d_only", "store": "full", "release": "yldot-data-v1",
         "external": {"families/d_only/gridue": {"sha256": hashlib.sha256(GRID).hexdigest(), "bytes": len(GRID)}}}
    mf.dump(m, mf.path("d_only", suite))


OWNER_IGNORED = "!! tests/yldot/families/d_only/gridue\n!! tests/yldot/families/d_only/sigma.h5\n"


def test_owner_families_are_not_default_but_sweep_when_named(tmp_path, children):
    """AIUE-99: an owner family is generated only when named, and then swept like the others (no --defaults-only)."""
    suite = tmp_suite(tmp_path)
    make_owner(suite)
    assert mr.select([], suite) == []
    stream = FakeStream(children[0])
    mr.generate(args(family=["d_only"], out=str(tmp_path / "gen")), suite, FakeRun(status=OWNER_IGNORED), stream)
    (cmd, _, _), = [c for c in stream.calls if c[0][0] == "docker"]
    assert "--sweep" not in cmd and "d_only" in cmd


def test_owner_family_carries_its_assets_and_sigma(tmp_path, children):
    """D6: the new manifest names the reference file, the owner family's assets as recorded and its sigma.h5, all
    under the new release; check_tree lets those ignored files through."""
    suite = tmp_suite(tmp_path)
    make_owner(suite)
    mr.generate(args(family=["d_only"], defaults_only=True, write=True, out=str(tmp_path / "gen")), suite,
                FakeRun(status=OWNER_IGNORED), FakeStream(children[0]))
    m = mf.load("d_only", suite)
    sig = suite / "families" / "d_only" / "sigma.h5"
    assert m["release"] == TAG
    assert set(m["external"]) == {"references/d_only.h5", "families/d_only/gridue", "families/d_only/sigma.h5"}
    assert m["external"]["families/d_only/gridue"] == {"sha256": hashlib.sha256(GRID).hexdigest(), "bytes": len(GRID)}
    assert m["external"]["families/d_only/sigma.h5"] == {"sha256": file_sha256(sig), "bytes": sig.stat().st_size}
    assert mf.family_assets(m) == ["families/d_only/gridue", "families/d_only/sigma.h5"]


def test_owner_assets_refuses_an_absent_sigma(tmp_path):
    """run_mutations.py calls owner_assets without select: an absent sigma.h5 is a refusal, not a traceback."""
    suite = tmp_suite(tmp_path)
    make_owner(suite)
    (suite / "families" / "d_only" / "sigma.h5").unlink()
    with pytest.raises(mr.Stop, match="sigma.h5 is missing") as e:
        mr.owner_assets(["d_only"], suite)
    assert e.value.code == 1


@pytest.mark.parametrize("content, status, message", [
    (b"another grid", OWNER_IGNORED, "differs from its manifest"),
    (GRID, OWNER_IGNORED + "!! tests/yldot/families/d_only/stray.h5\n", "holds files"),
])
def test_owner_family_refusals(tmp_path, children, content, status, message):
    suite = tmp_suite(tmp_path)
    make_owner(suite, content)
    stream = FakeStream(children[0])
    with pytest.raises(mr.Stop, match=message) as e:
        mr.generate(args(family=["d_only"], defaults_only=True, out=str(tmp_path / "gen")), suite, FakeRun(status=status),
                    stream)
    assert e.value.code == 1 and not stream.calls


def test_a_preview_never_writes_over_a_release(tmp_path, children):
    suite = tmp_suite(tmp_path)
    mr.generate(args(out=str(tmp_path / "gen"), write=True), suite, FakeRun(), FakeStream(children[0]))
    stream = FakeStream(children[0])
    with pytest.raises(mr.Stop, match="never replaces released references"):
        mr.generate(args(platform="host", release=None, out=str(tmp_path / "gen2"), write=True), suite, FakeRun(),
                    stream)
    assert not stream.calls and mf.load("d_only", suite)["release"] == TAG


def test_refuses_a_used_out_directory(tmp_path):
    suite = tmp_suite(tmp_path)
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen" / "x").write_text("")
    with pytest.raises(mr.Stop, match="not empty"):
        mr.generate(args(out=str(tmp_path / "gen")), suite, FakeRun(), FakeStream(tmp_path))


def test_default_families_are_the_small_ones():
    """Every family with sigma.h5 that is not an owner family (whose sigma.h5 is a release asset, AIUE-92 D6)."""
    assert mr.select([], SUITE) == sorted(p.parent.name for p in FAMILIES.glob("*/sigma.h5")
                                          if not mf.owner_family(p.parent.name))


def test_child_names_a_failed_evaluation(monkeypatch, tmp_path):
    from yldot.harness.process import Runner

    def failed(self, family, config=None, **kw):
        return Result(status="error", family=family, config=config, mode="spawn", message="boom", log_tail="tail")

    monkeypatch.setattr(Runner, "evaluate", failed)
    (tmp_path / "build.json").write_text(json.dumps({"commit": SHA, "compiler": "c", "runner_image": "r"}))
    with pytest.raises(mr.Stop) as e:
        mr.child(["d_only"], tmp_path / "out", tmp_path / "build.json")
    assert e.value.code == 2 and str(e.value).startswith("d_only steady: error boom")


def test_main_exit_codes(capsys):
    assert mr.main(["make_references.py", "generate", "--from-commit", "HEAD", "--platform", "host", "--release",
                    TAG]) == 1
    assert "previews only" in capsys.readouterr().err


def test_manifests_with_data():
    """Every manifest in references/ that holds reference data: its store is family.toml's, it classifies exactly the
    inventory's variants (an owner family too, since AIUE-99), a release names its
    files (previews are never committed) and they were built in the pinned image (owner, AIUE-88 D1)."""
    from yldot.harness import variants

    ids = {v.id for v in variants.plan()}
    for p in sorted((SUITE / "references").glob("*.manifest.json")):
        m = mf.load(p)
        if "datasets" not in m:
            continue
        with open(FAMILIES / m["family"] / "family.toml", "rb") as f:
            assert m["store"] == tomllib.load(f)["family"]["store"], p.name
        assert set(m["variables"]) == ids, p.name
        assert m["provenance"]["flags"] == "--serial", p.name
        assert m["release"] is not None, p.name
        assert m["provenance"]["runner_image"].startswith("yldot-linux:24.04 sha256:"), p.name


# ---------------------------------------------------------------- the variant sweep (AIUE-94)


def test_sweep_classes_as_probed(swept):
    ref = swept[0] / "references"
    m = mf.loads((ref / "d_only.json").read_text())
    assert {vid: e["class"] for vid, e in m["variables"].items()} == SWEEP
    v = m["variables"]
    assert v["bbb.isnion"]["reason"] == "neq 420 -> 300"
    assert v["bbb.isphiofft"]["reason"].startswith("error: RuntimeError: *** isphion.ne.0 while isphiofft.ne.0")
    assert v["bbb.methe=33"]["reason"] == "not applicable in d_only: value equals d"
    assert v["bbb.jxsori"]["reason"] == "not applicable in d_only: no valid index (bound 1)"
    assert v["com.chgstate_format"]["reason"] == "not applicable in d_only: unallocated"
    assert v["bbb.isbcwdt"]["config"] == "timestep" and v["bbb.cfvisx"]["phase"] == "PRE"
    assert v["bbb.lgvmax"]["block_l2"] and v["bbb.lgvmax"]["sha256"] is None  # MARGINAL: norms, no data
    assert v["bbb.xlinc"]["block_l2"] == {} and v["bbb.xlinc"]["applied"] is not None
    assert json.loads((ref / "d_only.findings.json").read_text()) == []
    assert (ref / "d_only.summary").read_text() == (
        "d_only: 10 variants: 2 sensitive, 1 inert, 1 marginal, 2 invalid, 4 excluded; 0 nondeterministic\n")
    cost = json.loads((ref / "d_only.cost.json").read_text())
    assert cost["evaluations"] == 2 + 9 + 2  # the defaults, all but com.geometry, the SENSITIVE ones again
    with np.load(ref / "samples" / "d_only.npz") as z:
        # plan (inventory) order: bbb.isbcwdt is at bbb/bbb.v:179, bbb.cfvisx at :331
        assert z["ids"].tolist() == ["bbb.isbcwdt", "bbb.cfvisx"] and z["configs"].tolist() == ["timestep", "steady"]
        assert z["yldot"].shape == (2, 420) and z["tol_steady"].shape == (420,)


def test_sweep_writes_the_same_bytes_twice_and_opens(tmp_path, swept):
    a, b = (d / "references" for d in swept)
    assert file_sha256(a / "d_only.h5") == file_sha256(b / "d_only.h5")
    ja, jb = (mf.loads((d / "d_only.json").read_text()) for d in (a, b))
    for j in (ja, jb):
        j["provenance"].pop("date")
    assert ja == jb
    suite = tmp_suite(tmp_path)
    manifests, findings = mr.assemble(SHA, ["d_only"], swept[0], TAG)
    assert findings == []
    mr.install(manifests, swept[0], suite)
    with open_store("d_only", suite) as s:
        assert s.variants("steady") == ["bbb.cfvisx"] and s.variants("timestep") == ["bbb.isbcwdt"]


def test_only_keeps_every_other_entry(tmp_path, swept):
    """--only bbb.cfvisx against the installed sweep: the same file, bit for bit (every other variant copied)."""
    suite = tmp_suite(tmp_path)
    mr.install(mr.assemble(SHA, ["d_only"], swept[0], TAG)[0], swept[0], suite)
    d = tmp_path / "only"
    mr.child(["d_only"], d / "references", build_record(tmp_path), sweep=list(SWEEP), only=["bbb.cfvisx"],
             full=True, suite=suite)
    assert file_sha256(d / "references" / "d_only.h5") == file_sha256(swept[0] / "references" / "d_only.h5")
    new, old = (mf.loads((x / "references" / "d_only.json").read_text()) for x in (d, swept[0]))
    assert new["variables"] == old["variables"]
    cost = json.loads((d / "references" / "d_only.cost.json").read_text())
    assert cost["evaluations"] == 2 + 2  # the defaults, cfvisx twice
    with np.load(d / "references" / "full" / "d_only.bbb.cfvisx.npz") as z:
        assert z["yldot"].shape == z["default"].shape == (420,) and len(z["labels"]) == 420


def test_only_refuses_a_changed_default(tmp_path, swept, monkeypatch):
    suite = tmp_suite(tmp_path)
    mr.install(mr.assemble(SHA, ["d_only"], swept[0], TAG)[0], swept[0], suite)
    monkeypatch.setattr(mr, "default_shas", lambda data, sig: {})
    with pytest.raises(mr.Stop) as e:
        mr.child(["d_only"], tmp_path / "only", build_record(tmp_path), sweep=list(SWEEP), only=["bbb.cfvisx"],
                 suite=suite)
    assert e.value.code == 3 and "regenerate in full" in str(e.value)


def test_only_on_a_sketch_store(tmp_path):
    """AIUE-99: --only against an installed sketch store (large_dd2c, two variants) passes the defaults' check, whose
    stored sketch weights and thresholds are kept or derived, and reproduces the file bit for bit."""
    sweep = ["bbb.cfvisx", "bbb.fdtnixy"]
    first = tmp_path / "first"
    mr.child(["large_dd2c"], first / "references", build_record(tmp_path), sweep=sweep)
    suite = tmp_suite(tmp_path, ("large_dd2c",))
    mr.install(mr.assemble(SHA, ["large_dd2c"], first, TAG)[0], first, suite)
    d = tmp_path / "only"
    mr.child(["large_dd2c"], d / "references", build_record(tmp_path), sweep=sweep, only=["bbb.cfvisx"], suite=suite)
    assert file_sha256(d / "references" / "large_dd2c.h5") == file_sha256(first / "references" / "large_dd2c.h5")
    assert mr.SKETCH_DEFAULT_RE.search("/steady/default/sketch_weight")
    assert mr.SKETCH_DEFAULT_RE.search("/timestep/default/sketch_threshold/cell_m")
    assert not mr.SKETCH_DEFAULT_RE.search("/steady/default/yldot")


def test_only_needs_every_other_entry(tmp_path, swept):
    suite = tmp_suite(tmp_path)
    mr.install(mr.assemble(SHA, ["d_only"], swept[0], TAG)[0], swept[0], suite)
    with pytest.raises(mr.Stop, match="bbb.yinc has none"):
        mr.child(["d_only"], tmp_path / "only", build_record(tmp_path), sweep=list(SWEEP) + ["bbb.yinc"],
                 only=["bbb.cfvisx"], suite=suite)


def test_a_second_run_that_differs_is_nondeterministic(tmp_path, monkeypatch):
    from yldot.harness.process import Runner

    real, seen = Runner.evaluate, []

    def flaky(self, family, **kw):
        r = real(self, family, **kw)
        v = kw.get("variant")
        if v is not None:
            seen.append(v.id)
            if seen.count(v.id) == 2:
                r.data["yldot"][7] += 1.0
        return r

    monkeypatch.setattr(Runner, "evaluate", flaky)
    d = tmp_path / "flaky"
    mr.child(["d_only"], d / "references", build_record(tmp_path), sweep=["bbb.cfvisx"])
    m = mf.loads((d / "references" / "d_only.json").read_text())
    e = m["variables"]["bbb.cfvisx"]
    assert e["class"] == "INVALID" and e["reason"] == "nondeterministic: 1 rows differ between two processes"
    assert json.loads((d / "references" / "d_only.findings.json").read_text()) == [
        {"id": "bbb.cfvisx", "finding": "nondeterministic: 1 rows differ; file a bugfix ticket"}]
    _, findings = mr.assemble(SHA, ["d_only"], d, TAG)
    assert findings == ["d_only bbb.cfvisx: nondeterministic: 1 rows differ; file a bugfix ticket"]


def data(neq=4, y=(1.0, 2.0, 3.0, 4.0)):
    from yldot.harness.state import INDEX_ARRAYS, MASK_ARRAYS

    y = np.array(y)
    d = {"neq": neq, "yldot": y, "yldot_J": y.copy(), "masks": {n: np.ones(3, np.int32) for n in MASK_ARRAYS}}
    d.update({n: np.arange(neq) for n in INDEX_ARRAYS})
    return d


def result(d, status="ok", message="", applied="applied"):
    if d is not None:
        d["variant"] = {"PRE": {"status": applied, "d": None, "applied": None}, "POST": None}
    return Result(status=status, family="fam", config="steady", mode="spawn", data=d, message=message)


TOL = np.full(4, 1e-3)


@pytest.mark.parametrize("change, want", [
    (lambda d: None, ("INERT", "")),
    (lambda d: d["yldot"].__setitem__(1, 2.0 + 0.2), ("SENSITIVE", "max |diff|/tol = 200")),
    (lambda d: d["yldot_J"].__setitem__(1, 2.0 + 0.05), ("MARGINAL", None)),
    (lambda d: d["yldot"].__setitem__(0, np.nan), ("INVALID", "non-finite yldot or yldot_J at rows [1]")),
    (lambda d: d.update(neq=5), ("INVALID", "neq 4 -> 5")),
])
def test_classify(change, want):
    d = data()
    change(d)
    cls, reason, finding = mr.classify(result(d), data(), TOL)
    assert finding is None and cls == want[0]
    if want[1] is not None:
        assert reason == want[1]
    if cls == "MARGINAL":
        assert reason.startswith("max |diff|/tol = 50 <= M_cls = 100: treated as EXCLUDED")


def test_classify_a_layout_change_at_the_same_neq_is_invalid():
    """Owner, 2026-10-22 (AIUE-94 D4): like a neq change (bbb.isngon in d_c and d_mols swaps the gas equations)."""
    d = data()
    d["idxg"] = d["idxg"][::-1].copy()
    d["masks"]["isngonxy"] = np.zeros(3, np.int32)
    assert mr.classify(result(d), data(), TOL) == (
        "INVALID", "equation layout changed (idxg, isngonxy) at the same neq", None)


def test_classify_irregular_results_are_findings():
    d = data(y=(-0.0, 2.0, 3.0, 4.0))
    assert mr.classify(result(d), data(y=(0.0, 2.0, 3.0, 4.0)), TOL)[2].startswith("bitwise differences of size zero")


TOL_NU = 2.0 ** np.array([-10, -3, -10, -17])  # per entry, powers of two: the ratios below are exact


@pytest.mark.parametrize("change, want", [
    # with another entry's tol (TOL_NU[0] for the first, TOL_NU[3] for the second) the two would swap classes
    (lambda d: d["yldot"].__setitem__(3, 4.0 + 200 * 2.0 ** -17), ("SENSITIVE", "max |diff|/tol = 200")),
    (lambda d: d["yldot"].__setitem__(1, 2.0 + 50 * 2.0 ** -3), ("MARGINAL", "max |diff|/tol = 50 <= M_cls")),
    # exactly M_cls * tol_i is not more than M_cls * tol_i: MARGINAL (strict >)
    (lambda d: d["yldot"].__setitem__(0, 1.0 + 100 * 2.0 ** -10), ("MARGINAL", "max |diff|/tol = 100 <= M_cls")),
    (lambda d: d["yldot"].__setitem__(0, 1.0 + 101 * 2.0 ** -10), ("SENSITIVE", "max |diff|/tol = 101")),
    # yldot as the default's, only the yldot_J run differs
    (lambda d: d["yldot_J"].__setitem__(2, 3.0 + 1000 * 2.0 ** -10), ("SENSITIVE", "max |diff|/tol = 1e+03")),
    (lambda d: d["yldot_J"].__setitem__(3, 4.0 + 150 * 2.0 ** -17), ("SENSITIVE", "max |diff|/tol = 150")),
])
def test_classify_uses_the_per_entry_tol(change, want):
    d = data()
    change(d)
    cls, reason, finding = mr.classify(result(d), data(), TOL_NU)
    assert finding is None and cls == want[0] and reason.startswith(want[1])


def test_child_classifies_with_the_variants_config_tol(tmp_path, monkeypatch):
    """Each variant is classified against its configuration's default and that default's tol (d_only: bbb.cfvisx
    steady, bbb.isbcwdt timestep)."""
    tols, seen = {"steady": 1.0, "timestep": 2.0}, []

    def fake_tolerance(fdir, yldot, config, imap, suite=mr.SUITE):
        return np.full(len(yldot), tols[config])

    def fake_classify(res, base, tol, m_cls=mr.M_CLS):
        seen.append((res.config, float(tol[0]), np.asarray(base["yldot"]).copy()))
        return "INERT", "", None

    monkeypatch.setattr(mr, "tolerance", fake_tolerance)
    monkeypatch.setattr(mr, "classify", fake_classify)
    d = tmp_path / "cfg"
    mr.child(["d_only"], d / "references", build_record(tmp_path), sweep=["bbb.cfvisx", "bbb.isbcwdt"])
    assert [(c, t) for c, t, _ in seen] == [("timestep", 2.0), ("steady", 1.0)]  # plan order
    with h5py.File(d / "references" / "d_only.h5", "r") as f:
        for config, _, base in seen:
            assert np.array_equal(base, f["/{}/default/yldot".format(config)][()])
        assert not np.array_equal(f["/steady/default/yldot"][()], f["/timestep/default/yldot"][()])


MIST = """Reading uedge.hdf5-style save-file 'base_state.h5'.
>>> Save read successfully
**** data file mist.dat not found --

**** Data files for various impurities are available;
**** check uedge/in/api or contact authors

**** For UEDGE, the data file must be re-named mist.dat"""
MCRATES = """ ***Impurity file using pre-2012 format is C_rates.strahl
 TARGET MATERIAL IS      GRAPHITE
 *** mcrates could not find za=                    0  zn=                    6
 *** check mcfilenames array

Reading uedge.hdf5-style save-file 'base_state.h5'.
>>> Save read successfully"""
BARE = ("Traceback (most recent call last):\n  File \"state.py\", line 215, in evaluate\n    bbb.exmain()\n"
        "RuntimeError\n")
# slab_phi bbb.ispfbcvsix (AIUE-94 round 1): the informational banner, then the solver's own error report
ILUT = """ UEDGE 8.1.2-beta.0
 **** mhdgeo=-1: cartesian grid generated *****
 iter=   0 fnrm=                   Infinity nfe=      1
  Updating Jacobian, npe =                      1
  Error return from ilut:  ierr =                    -5

    ierr >  0   --> Zero pivot encountered at step number ierr.
    ierr = -1   --> Error. input matrix may be wrong.
    ierr = -5   --> Zero row encountered."""


def test_invalid_reasons_carry_the_error_text():
    """Review I1-m1: an xerrab is a RuntimeError without text; its reason takes the '***' message of the log."""
    def reason(message, tail):
        return mr.classify(Result(status="error", family="fam", config="steady", mode="spawn", message=message,
                                  log_tail=tail), data(), TOL)[1]

    assert reason(BARE, MIST) == (
        "error: RuntimeError (log: **** data file mist.dat not found -- / **** Data files for various impurities are "
        "available; / **** check uedge/in/api or contact authors / **** For UEDGE, the data file must be re-named "
        "mist.dat)")
    # the last run of '***' lines only, not an earlier informational one
    assert reason(BARE, MCRATES) == ("error: RuntimeError (log: *** mcrates could not find za= 0 zn= 6 / *** check "
                                     "mcfilenames array)")
    assert reason(BARE, "no marked line") == "error: RuntimeError"
    # an error line after the last '***' run wins over an informational banner; the first one, not the help text
    assert reason(BARE, ILUT) == "error: RuntimeError (log: Error return from ilut: ierr = -5)"
    # an exception with text keeps its text, whatever the log holds
    assert reason(BARE.replace("RuntimeError\n", "RuntimeError: *** isphion.ne.0 ***\n"), MIST) == (
        "error: RuntimeError: *** isphion.ne.0 ***")
    assert len(reason(BARE, "*** " + "x" * 1000)) == len("error: ") + mr.REASON_CHARS


def test_classify_failures_and_noops():
    r = result(None, status="timeout", message="no result after 600 s; child killed")
    assert mr.classify(r, data(), TOL) == ("INVALID", "timeout: no result after 600 s; child killed", None)
    r = result(None, status="error", message="Traceback (most recent call last):\n  ...\nRuntimeError: boom\n")
    assert mr.classify(r, data(), TOL) == ("INVALID", "error: RuntimeError: boom", None)
    for status, why in mr.NOOP.items():
        assert mr.classify(result(data(), applied=status), data(), TOL) == (
            "EXCLUDED", "not applicable in fam: " + why, None)


def test_tolerance_sample_is_seeded_and_keeps_timestep():
    ids = ["bbb.v{:03d}".format(i) for i in range(60)]
    a = mr.tolerance_sample(ids, ["bbb.v059"])
    assert a == mr.tolerance_sample(list(ids), ["bbb.v059"]) and a == sorted(a)  # plan order kept
    assert len(a) in (20, 21) and "bbb.v059" in a
    assert mr.tolerance_sample(ids[:5], []) == ids[:5]


def test_generate_passes_the_sweep_options(tmp_path, swept):
    suite = tmp_suite(tmp_path)
    mr.install(mr.assemble(SHA, ["d_only"], swept[0], TAG)[0], swept[0], suite)
    stream = FakeStream(swept[0])
    mr.generate(args(out=str(tmp_path / "gen"), only=["bbb.cfvisx"], full=True), suite, FakeRun(), stream)
    assert stream.calls[0][0][-4:] == ["d_only", "--only", "bbb.cfvisx", "--full"]
    stream = FakeStream(swept[0])
    mr.generate(args(platform="host", release=None, out=str(tmp_path / "gen2"), defaults_only=True), suite,
                FakeRun(), stream)
    child_cmd = [c for c, _, _ in stream.calls if "_child" in c][0]
    assert child_cmd[child_cmd.index("_child") + 1:][:3] == ["d_only", "--sweep", "none"]
    # the inventory comes from the built commit's .v files, not from this tree's
    assert child_cmd[child_cmd.index("--repo") + 1] == str(tmp_path / "gen2" / "src")


@pytest.mark.parametrize("kw, code, message", [
    ({"full": True}, 2, "--full needs --only"),
    ({"full": True, "only": ["bbb.x"], "write": True}, 2, "drop --write"),
    ({"only": ["bbb.x"], "defaults_only": True}, 2, "together"),
    ({"only": ["bbb.cfvisx"]}, 1, "--only regenerates against the installed references"),
])
def test_sweep_option_refusals(tmp_path, kw, code, message):
    suite = tmp_suite(tmp_path)
    stream = FakeStream(tmp_path)
    with pytest.raises(mr.Stop) as e:
        mr.generate(args(out=str(tmp_path / "gen"), **kw), suite, FakeRun(), stream)
    assert e.value.code == code and message in str(e.value)
    assert not stream.calls


def test_defaults_only_never_writes_over_classified_variants(tmp_path, swept):
    suite = tmp_suite(tmp_path)
    mr.install(mr.assemble(SHA, ["d_only"], swept[0], TAG)[0], swept[0], suite)
    with pytest.raises(mr.Stop, match="would drop the classified variants of d_only"):
        mr.generate(args(out=str(tmp_path / "gen"), defaults_only=True, write=True), suite, FakeRun(),
                    FakeStream(swept[0]))


def test_over_its_cap_is_a_finding_and_nothing_is_written(tmp_path, swept, monkeypatch):
    suite = tmp_suite(tmp_path)
    monkeypatch.setitem(mr.CAPS_MB, "d_only", 0.1)
    with pytest.raises(mr.Stop) as e:
        mr.generate(args(out=str(tmp_path / "gen"), write=True), suite, FakeRun(), FakeStream(swept[0]))
    assert e.value.code == 3 and "over its 0.1 MB cap" in str(e.value)
    assert list((suite / "references").iterdir()) == []
