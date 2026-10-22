"""Generate the yldot suite's default reference files from one commit (epic AIUE-9, PRD section 7.6; AIUE-88).

Usage (from a checkout whose tests/yldot is the commit's, references/ aside):
    python make_references.py generate --from-commit SHA [--platform linux|host] [--release yldot-data-v<N>]
                                       [--out DIR] [--write] [family ...]
    <built python> make_references.py _child family ... --out DIR --build FILE

generate  builds SHA --serial and, per family (default: every family with sigma.h5, the five small ones), evaluates
          the steady and timestep defaults with both Jacobian flags (harness/state.py, PRD section 6) and the
          diagnostics, and writes DIR/references/<family>.h5 (harness/store.py, with the family's sigma_i of
          families/<f>/sigma.h5, AIUE-87) and the manifest with provenance (harness/manifest.py). It prints each file's
          SHA-256 and size. Only with --write does it copy the files to tests/yldot/references/ and write
          references/<family>.manifest.json, then open each through open_store as a check.
            --platform linux (default): a git archive of SHA, built and evaluated in the pinned image yldot-linux:24.04
                (tests/yldot/linux/Dockerfile, AIUE-87) by linux/generate.sh; the manifest's runner_image names the
                image id. The only release-grade references (owner, 2026-10-22, AIUE-88 D1).
            --platform host: a temporary worktree of SHA and a venv with the image's pins, built here. A preview:
                the manifest's release is null, and --release is refused (owner, 2026-10-22, AIUE-88 D2).
          --release names the data release the manifests point to; the files are published with release_data.py.
_child    runs inside the built environment and writes DIR/<family>.h5 and DIR/<family>.json (the manifest without
          release and external), from the build record FILE (JSON: commit, compiler, runner_image).

The container and the host venv run this working tree's harness and families against SHA's UEDGE, so generate
refuses unless tests/yldot (references/ excepted) is exactly SHA's: no difference, no untracked file. It refuses a
family without sigma.h5, whose sigma.h5 differs from tolerances.toml's SHA-256, or whose manifest names release
assets other than its reference file (the owner families' grids and states: AIUE-92). Every evaluation runs in a
fresh child process (harness/process.py). Writing the same results twice gives the same bytes (track_times=False).

Exit codes: 0 done; 1 refused; 2 usage, a failed build or a failed evaluation.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package

import numpy as np  # noqa: E402

from yldot.harness import manifest as mf  # noqa: E402
from yldot.harness.process import family_dir  # noqa: E402
from yldot.harness.store import file_sha256  # noqa: E402

SUITE = Path(__file__).resolve().parents[1]
IMAGE = "yldot-linux:24.04"
PINS = ("setuptools==84.2.1", "forthon==0.10.10", "numpy==2.5.4", "h5py==3.16.0")  # linux/Dockerfile, the image's
FLAGS = "--serial"
TIMEOUT_FACTOR = 5  # x family.toml timeout_s per child: x86 emulation runs slower (measure_roundoff.py)


class Stop(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def run(cmd, cwd=None):
    """(returncode, stdout, stderr) of a git or docker query."""
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def stream(cmd, cwd=None, env=None, log=None):
    """Return code of a long command (build, container), its output to the terminal or to the file log."""
    if log is None:
        return subprocess.run(cmd, cwd=cwd, env=env).returncode
    with open(log, "w") as f:
        return subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode


# ---------------------------------------------------------------- child side


def sigma(fdir, config):
    import h5py

    with h5py.File(fdir / "sigma.h5", "r") as f:
        return f[config]["sigma"][()]


def same_index(a, b):
    from yldot.harness.state import INDEX_ARRAYS, MASK_ARRAYS

    return (a["neq"] == b["neq"] and all(np.array_equal(a[n], b[n]) for n in INDEX_ARRAYS)
            and all(np.array_equal(a["masks"][n], b["masks"][n]) for n in MASK_ARRAYS))


def child(families, out, build):
    """Evaluate and write each family's reference file and manifest fields into out."""
    from yldot.harness import Runner, compare, load_evaluation, store

    rec = json.loads(Path(build).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    for name in families:
        fdir = family_dir(name)
        with open(fdir / "family.toml", "rb") as f:
            kind = tomllib.load(f)["family"]["store"]
        timeout = TIMEOUT_FACTOR * float(load_evaluation(fdir)["timeout_s"])
        data = {}
        for config in mf.CONFIG_NAMES:
            r = runner.evaluate(name, config=config, diagnostics=True, timeout=timeout)
            if not r.ok:
                raise Stop(2, "{} {}: {} {}\n{}".format(name, config, r.status, r.message, r.log_tail))
            data[config] = r.data
        if not same_index(data["steady"], data["timestep"]):
            raise Stop(2, "{}: the steady and timestep runs have different index arrays".format(name))
        imap = compare.index_map(data["steady"], compare.load_regions(fdir))
        w = store.create(out / "{}.h5".format(name), kind, name, data["steady"], imap)
        for config, d in data.items():
            w.write_default(config, d["yldot"], d["yldot_J"], sigma(fdir, config), d["diagnostics"])
        written = w.finish()
        guarded, unguarded = mf.summarize(written["datasets"])
        fields = {"schema": mf.SCHEMA, "family": name, "store": kind, "datasets": written["datasets"],
                  "guarded": guarded, "unguarded": unguarded, "variables": {},
                  "provenance": mf.provenance(rec["commit"], rec["compiler"], FLAGS, rec["runner_image"])}
        if kind == "sketch":
            fields["sketch"] = {"k": store.K, "seed": store.SEED}
        (out / "{}.json".format(name)).write_text(mf.dumps(fields))
        print("{}: {} {} bytes".format(name, written["sha256"], written["bytes"]), flush=True)


# ---------------------------------------------------------------- host side: checks


def resolve(commit, root, run=run):
    rc, out, err = run(["git", "-C", str(root), "rev-parse", "--verify", "{}^{{commit}}".format(commit)])
    if rc != 0:
        raise Stop(1, "--from-commit {}: not a commit ({})".format(commit, err.strip()))
    return out.strip()


def check_tree(sha, root, run=run):
    """tests/yldot in the working tree is sha's, references/ excepted."""
    rc, _, err = run(["git", "-C", str(root), "diff", "--quiet", sha, "--", "tests/yldot",
                      ":(exclude)tests/yldot/references"])
    if rc == 1:
        raise Stop(1, "tests/yldot differs from {} (references/ excepted): commit it, or generate from the commit "
                      "the working tree holds".format(sha[:12]))
    if rc != 0:
        raise Stop(2, "git diff failed: {}".format(err.strip()))
    rc, out, err = run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--",
                        "tests/yldot"])
    if rc != 0:
        raise Stop(2, "git status failed: {}".format(err.strip()))
    extra = [line[3:] for line in out.splitlines() if not line[3:].startswith("tests/yldot/references/")]
    if extra:
        raise Stop(1, "tests/yldot holds files {} does not: {}".format(sha[:12], ", ".join(extra[:10])))


def select(families, suite):
    """The families to generate, checked: sigma.h5 as tolerances.toml records it, no release assets but the
    reference file."""
    fams = suite / "families"
    if not families:
        families = sorted(p.name for p in fams.iterdir() if (p / "sigma.h5").is_file())
    with open(suite / "tolerances.toml", "rb") as f:
        recorded = tomllib.load(f).get("sigma", {})
    problems = []
    for name in families:
        fdir = fams / name
        if not (fdir / "input.py").is_file():
            problems.append("{}: no such family".format(name))
            continue
        if not (fdir / "sigma.h5").is_file():
            problems.append("{}: no sigma.h5 (its round-off is not measured yet: AIUE-92 for the owner families)"
                            .format(name))
            continue
        want = recorded.get(name, {}).get("sha256")
        if file_sha256(fdir / "sigma.h5") != want:
            problems.append("{}: sigma.h5 differs from tolerances.toml's SHA-256 {}".format(name, want))
        if mf.path(name, suite).is_file():
            other = sorted(set(mf.load(name, suite)["external"]) - {mf.reference_path(name)})
            if other:
                problems.append("{}: its manifest names release assets {}; moving them is AIUE-92's".format(
                    name, other))
    if problems:
        raise Stop(1, "; ".join(problems))
    return list(families)


# ---------------------------------------------------------------- host side: builds


def base_image(suite):
    """The FROM line of linux/Dockerfile: the base image by digest."""
    hit = re.search(r"^FROM\s+(\S+)", (suite / "linux" / "Dockerfile").read_text(), re.MULTILINE)
    return hit.group(1)


def build_linux(sha, families, out, suite, root, run=run, stream=stream):
    rc, image_id, _ = run(["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE])
    if rc != 0:
        raise Stop(1, "image {} not found: docker build --platform linux/amd64 -t {} tests/yldot/linux".format(
            IMAGE, IMAGE))
    rc, _, err = run(["git", "-C", str(root), "archive", "--format=tar", "-o", str(out / "src.tar"), sha])
    if rc != 0:
        raise Stop(2, "git archive failed: {}".format(err.strip()))
    runner_image = "{} {} ({})".format(IMAGE, image_id.strip(), base_image(suite))
    cmd = ["docker", "run", "--rm", "--platform", "linux/amd64", "-v", "{}:/tests:ro".format(suite.parent),
           "-v", "{}:/out".format(out), IMAGE, "bash", "/tests/yldot/linux/generate.sh", sha, runner_image] + families
    print(" ".join(cmd), flush=True)
    if stream(cmd) != 0:
        raise Stop(2, "the container failed (build log: {})".format(out / "build.log"))


def build_host(sha, families, out, root, run=run, stream=stream):
    src, venv = out / "src", out / "venv"
    rc, _, err = run(["git", "-C", str(root), "worktree", "add", "--detach", str(src), sha])
    if rc != 0:
        raise Stop(2, "git worktree add failed: {}".format(err.strip()))
    try:
        if stream([sys.executable, "-m", "venv", str(venv)]) != 0:
            raise Stop(2, "python -m venv failed")
        # the venv first on PATH: Forthon3 otherwise resolves to another Python (../venvs/base-a8446eb.BUILD.txt)
        env = dict(os.environ, PATH="{}{}{}".format(venv / "bin", os.pathsep, os.environ.get("PATH", "")),
                   OMP_NUM_THREADS="1")
        pip = [str(venv / "bin" / "python"), "-m", "pip"]
        if stream(pip + ["install", "-q"] + list(PINS), env=env) != 0:
            raise Stop(2, "pip install {} failed".format(" ".join(PINS)))
        if stream(pip + ["install", "-v", "--no-build-isolation", "--no-deps", ".", "-C",
                         "--build-option={}".format(FLAGS)], cwd=src, env=env, log=out / "build.log") != 0:
            raise Stop(2, "the build failed (log: {})".format(out / "build.log"))
        rc, gf, _ = run(["gfortran", "--version"])
        rec = {"commit": sha, "compiler": gf.splitlines()[0] if rc == 0 and gf else "unknown",
               "runner_image": "host {} {} python {} (preview)".format(sys.platform, platform.machine(),
                                                                        platform.python_version())}
        (out / "build.json").write_text(json.dumps(rec, indent=1) + "\n")
        cmd = [str(venv / "bin" / "python"), str(Path(__file__).resolve()), "_child"] + families + [
            "--out", str(out / "references"), "--build", str(out / "build.json")]
        if stream(cmd, cwd=out, env=env) != 0:
            raise Stop(2, "the evaluation failed")
    finally:
        run(["git", "-C", str(root), "worktree", "remove", "--force", str(src)])


# ---------------------------------------------------------------- host side: manifests


def assemble(sha, families, out, release):
    """{family: manifest} from the child's files in out/references."""
    manifests = {}
    for name in families:
        h5, js = out / "references" / "{}.h5".format(name), out / "references" / "{}.json".format(name)
        if not (h5.is_file() and js.is_file()):
            raise Stop(2, "{}: the child wrote no {} and {}".format(name, h5.name, js.name))
        m = json.loads(js.read_text())
        if m["provenance"]["commit"] != sha:
            raise Stop(2, "{}: provenance commit {} is not {}".format(name, m["provenance"]["commit"], sha))
        m["release"] = release
        m["external"] = {mf.reference_path(name): {"sha256": file_sha256(h5), "bytes": h5.stat().st_size}}
        mf.validate(m)
        manifests[name] = m
    return manifests


def install(manifests, out, suite):
    from yldot.harness import open_store

    for name, m in manifests.items():
        target = suite / mf.reference_path(name)
        if target.is_symlink() or target.exists():
            target.unlink()  # a fetched file is a link into .data/<tag>/: never write through it
        shutil.copyfile(out / "references" / "{}.h5".format(name), target)
        mf.dump(m, mf.path(name, suite))
        open_store(name, suite).close()


def generate(args, suite=SUITE, run=run, stream=stream):
    root = suite.parents[1]
    if args.release is not None and not mf.TAG_RE.match(args.release):
        raise Stop(2, "--release {!r}, need yldot-data-v<N>".format(args.release))
    if args.platform == "host" and args.release is not None:
        raise Stop(1, "--platform host makes previews only (release null; owner, AIUE-88 D2): drop --release")
    sha = resolve(args.from_commit, root, run)
    check_tree(sha, root, run)
    families = select(args.family, suite)
    out = Path(args.out or tempfile.mkdtemp(prefix="yldot-references-")).resolve()
    if out.exists() and any(out.iterdir()):
        raise Stop(1, "--out {} is not empty".format(out))
    out.mkdir(parents=True, exist_ok=True)
    if args.platform == "linux":
        build_linux(sha, families, out, suite, root, run, stream)
    else:
        build_host(sha, families, out, root, run, stream)
    manifests = assemble(sha, families, out, args.release)
    for name, m in manifests.items():
        e = m["external"][mf.reference_path(name)]
        print("{}  {}  {} bytes".format(e["sha256"], mf.reference_path(name), e["bytes"]))
    if args.write:
        install(manifests, out, suite)
        print("wrote {} reference files and manifests (release {})".format(len(manifests), args.release))
    else:
        print("preview in {} (--write copies it to tests/yldot/references)".format(out))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("generate", help="build a commit and write its default references")
    p.add_argument("family", nargs="*", help="default: every family with sigma.h5")
    p.add_argument("--from-commit", required=True)
    p.add_argument("--platform", choices=("linux", "host"), default="linux")
    p.add_argument("--release", help="yldot-data-v<N>, the release the manifests name (linux only)")
    p.add_argument("--out", help="an empty or new working directory (default: a temporary one)")
    p.add_argument("--write", action="store_true", help="copy to tests/yldot/references and write the manifests")
    p = sub.add_parser("_child", help="inside the built environment: evaluate and write")
    p.add_argument("family", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--build", required=True, help="JSON: commit, compiler, runner_image")
    args = parser.parse_args(argv[1:])
    try:
        if args.cmd == "_child":
            child(args.family, args.out, args.build)
        else:
            generate(args)
    except (Stop, mf.ManifestError) as e:
        print(str(e), file=sys.stderr)
        return getattr(e, "code", 2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
