"""tools/make_references.py (AIUE-88; PRD section 7.6): the child side evaluates d_only in fresh child processes and
writes the same bytes twice, its files open through open_store; the host side's refusals, the exact git and docker
commands of the Linux path, the host path's preview (release null), and the manifests in references/ that hold data.
The child tests need the built uedge (in the Runner's children); git, docker, pip and the container are fakes here,
the real Linux run is the ticket's validation.
"""
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

from yldot.harness import FAMILIES, Result, open_store
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
        mr.child(["d_only"], d / "references", d / "build.json")
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
    a = {"from_commit": "HEAD", "platform": "linux", "release": TAG, "out": None, "write": False, "family": []}
    a.update(kw)
    return Namespace(**a)


def test_child_writes_the_same_bytes_twice(children):
    a, b = (d / "references" for d in children)
    assert file_sha256(a / "d_only.h5") == file_sha256(b / "d_only.h5")
    ja, jb = (json.loads((d / "d_only.json").read_text()) for d in (a, b))
    for j in (ja, jb):
        j["provenance"].pop("date")
    assert ja == jb
    assert ja["provenance"]["commit"] == SHA and ja["provenance"]["flags"] == "--serial" and ja["variables"] == {}


def test_child_files_open_and_hold_the_defaults(tmp_path, children):
    suite = tmp_suite(tmp_path)
    out = children[0]
    mr.install(mr.assemble(SHA, ["d_only"], out, TAG), out, suite)
    m = mf.load("d_only", suite)
    assert m["release"] == TAG and m["store"] == "full"
    assert set(m["guarded"]) == {"steady/default", "steady/sigma", "timestep/default", "timestep/sigma"}
    with h5py.File(FAMILIES / "d_only" / "sigma.h5", "r") as f:
        sig = {c: f[c]["sigma"][()] for c in mf.CONFIG_NAMES}
    with open_store("d_only", suite) as s:
        for c in mf.CONFIG_NAMES:
            assert np.array_equal(s.sigma(c), sig[c])
            assert s.diagnostics(c)
        assert (s.default("timestep") != s.default("steady")).any()  # the time-step term is exercised
        assert not s.jflag("steady").any()  # no flag-gated branch active in steady (family.toml [history])


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


def test_refuses_a_family_with_other_release_assets(tmp_path):
    suite = tmp_suite(tmp_path)
    m = {"schema": 1, "family": "d_only", "store": "full", "release": "yldot-data-v1",
         "external": {"families/d_only/gridue": {"sha256": "0" * 64, "bytes": 1}}}
    mf.dump(m, mf.path("d_only", suite))
    with pytest.raises(mr.Stop, match="AIUE-92"):
        mr.select([], suite)


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


def test_default_families_are_those_with_sigma():
    assert mr.select([], SUITE) == sorted(p.parent.name for p in FAMILIES.glob("*/sigma.h5"))


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
    """Every manifest in references/ that holds reference data: its store is family.toml's, it stores no variants
    yet, a release names its files (previews are never committed) and they were built in the pinned image (owner,
    AIUE-88 D1)."""
    for p in sorted((SUITE / "references").glob("*.manifest.json")):
        m = mf.load(p)
        if "datasets" not in m:
            continue
        with open(FAMILIES / m["family"] / "family.toml", "rb") as f:
            assert m["store"] == tomllib.load(f)["family"]["store"], p.name
        assert m["variables"] == {} and m["provenance"]["flags"] == "--serial", p.name
        assert m["release"] is not None, p.name
        assert m["provenance"]["runner_image"].startswith("yldot-linux:24.04 sha256:"), p.name
