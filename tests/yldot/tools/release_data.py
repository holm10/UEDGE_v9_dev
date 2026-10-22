"""Publish a yldot data release (epic AIUE-9, PRD section 7.3 "History growth"; decision 29): the documented release
command. Publishing is outward-facing: the epic owner runs or approves it (until AIUE-98's workflow takes over).

Usage (from a checkout whose manifests name the new tag):
    python release_data.py --tag yldot-data-v<N> --target <commit> [--repo OWNER/REPO] [--publish]

It collects every external file of the manifests (tests/yldot/references/*.manifest.json) whose release is --tag,
checks each file in the working tree (symlinks resolved) against its SHA-256 and size, and refuses (exit 1) if

  - the tag already exists (gh release view), or N is not the highest existing yldot-data-v* + 1;
  - --target is neither in origin/v9-develop's history nor the head of an open PR into v9-develop (fetch first);
  - a file is missing or differs from its manifest.

It then stages the files under their asset names (manifest.asset_name) in a temporary directory and prints the exact
`gh release create` command. Only with --publish does it run it, all assets in that one call (immutable releases take
no assets after publishing), and then downloads the release again and checks every SHA-256 (fetch_data.download).
Old releases are never overwritten or deleted here.

Exit codes: 0 dry run printed, or published and verified; 1 refused or the check after publishing failed; 2 usage.
"""
import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_data  # noqa: E402
from yldot.harness import manifest as mf  # noqa: E402

BASE = "v9-develop"


class Refused(Exception):
    pass


def run(cmd):
    """(returncode, stdout, stderr) of a git or gh command."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def collect(suite, tag):
    """[(path, asset, entry, file)] of every external file of the manifests naming tag."""
    files = []
    for p in sorted((Path(suite) / "references").glob("*.manifest.json")):
        m = mf.load(p)
        if m["release"] != tag:
            continue
        for rel, e in sorted(m["external"].items()):
            files.append((rel, mf.asset_name(rel), e, Path(suite) / rel))
    if not files:
        raise Refused("no manifest names release {}".format(tag))
    problems = []
    for rel, _, e, f in files:
        if not f.is_file():
            problems.append("{}: missing (or a dangling link)".format(rel))
            continue
        bad = fetch_data.matches(f, e)
        if bad:
            problems.append("{}: {}".format(rel, bad))
    if problems:
        raise Refused("files differ from their manifests: {}".format("; ".join(problems)))
    return files


def check_tag(tag, repo, run=run):
    rc, _, _ = run(["gh", "release", "view", tag, "-R", repo])
    if rc == 0:
        raise Refused("release {} already exists: never overwritten; take the next N".format(tag))
    rc, out, err = run(["gh", "release", "list", "-R", repo, "--limit", "1000", "--json", "tagName"])
    if rc != 0:
        raise Refused("gh release list failed: {}".format(err.strip()))
    numbers = [int(t["tagName"].rsplit("v", 1)[1]) for t in json.loads(out or "[]") if mf.TAG_RE.match(t["tagName"])]
    want = max(numbers, default=0) + 1
    if int(tag.rsplit("v", 1)[1]) != want:
        raise Refused("{}: the next data release is yldot-data-v{} (existing: {})".format(tag, want, sorted(numbers)))


def check_target(target, repo, run=run):
    """The full SHA of target, if it is in origin/v9-develop's history or the head of an open PR into it."""
    rc, out, err = run(["git", "rev-parse", "--verify", "{}^{{commit}}".format(target)])
    if rc != 0:
        raise Refused("--target {}: not a commit ({})".format(target, err.strip()))
    sha = out.strip()
    rc, _, _ = run(["git", "merge-base", "--is-ancestor", sha, "origin/" + BASE])
    if rc == 0:
        return sha
    rc, out, err = run(["gh", "pr", "list", "-R", repo, "--base", BASE, "--state", "open", "--json", "headRefOid"])
    if rc != 0:
        raise Refused("gh pr list failed: {}".format(err.strip()))
    if sha in {p["headRefOid"] for p in json.loads(out or "[]")}:
        return sha
    raise Refused("--target {} ({}) is neither in origin/{} nor an open PR head into {}".format(target, sha[:12], BASE,
                                                                                               BASE))


def release(tag, target, suite=mf.SUITE, repo=fetch_data.REPO, publish=False, run=run,
            download=fetch_data.download, out=print):
    """Returns the exit code."""
    if not mf.TAG_RE.match(tag):
        out("error: --tag {!r}, need yldot-data-v<N>".format(tag))
        return 2
    try:
        files = collect(suite, tag)
        check_tag(tag, repo, run)
        sha = check_target(target, repo, run)
    except (Refused, mf.ManifestError) as e:
        out("refused: {}".format(e))
        return 1
    stage = Path(tempfile.mkdtemp(prefix="yldot-release-"))
    try:
        for rel, asset, e, f in files:
            shutil.copyfile(f, stage / asset)
            bad = fetch_data.matches(stage / asset, e)
            if bad:
                out("refused: staged {} has {}".format(asset, bad))
                return 1
        notes = "yldot reference data (epic AIUE-9), named by tests/yldot/references/*.manifest.json at {}.\n\n".format(
            sha) + "\n".join("{}  {}  {} bytes".format(e["sha256"], asset, e["bytes"]) for _, asset, e, _ in files)
        cmd = ["gh", "release", "create", tag, "-R", repo, "--target", sha, "--title", tag, "--notes", notes,
               "--latest=false"] + [str(stage / asset) for _, asset, _, _ in files]
        out(shlex.join(cmd))
        if not publish:
            out("dry run: nothing published (the staged files are removed on exit; re-run with --publish)")
            return 0
        rc, o, err = run(cmd)
        if rc != 0:
            out("error: gh release create failed ({}): {}".format(rc, err.strip()))
            return 1
        out(o.strip())
        check = Path(tempfile.mkdtemp(prefix="yldot-release-check-"))
        bad = []
        try:
            download(tag, [asset for _, asset, _, _ in files], check, repo)
            for _, asset, e, _ in files:
                why = fetch_data.matches(check / asset, e) if (check / asset).is_file() else "not in the release"
                if why:
                    bad.append("{}: {}".format(asset, why))
        except fetch_data.FetchError as e:
            bad = [str(e)]
        finally:
            shutil.rmtree(check, ignore_errors=True)
        if bad:
            out("error: {} published, but the downloaded assets do not verify: {}".format(tag, "; ".join(bad)))
            return 1
        out("{} published at {} and verified ({} assets)".format(tag, sha[:12], len(files)))
        return 0
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", required=True, help="yldot-data-v<N>, N = the highest existing + 1")
    parser.add_argument("--target", required=True, help="the commit whose manifests name the tag")
    parser.add_argument("--repo", default=fetch_data.REPO, help="the GitHub repository")
    parser.add_argument("--publish", action="store_true", help="publish (outward-facing; the owner's call)")
    args = parser.parse_args(argv[1:])
    return release(args.tag, args.target, repo=args.repo, publish=args.publish)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
