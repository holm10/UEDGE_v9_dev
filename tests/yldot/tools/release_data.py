"""Publish a yldot data release (epic AIUE-9, PRD section 7.3 "History growth"; decision 29). Publishing is
outward-facing: .github/workflows/regenerate-references.yml runs it in the yldot-data environment, whose required
reviewer is the epic owner (AIUE-98); a hand publish from a checkout stays possible, run or approved by the owner.

Usage (the files and manifests are read from the working tree):
    python release_data.py --tag yldot-data-v<N> --target <commit> [--repo OWNER/REPO] [--publish]
                           [--generated [--renumber]] [--note TEXT]
    python release_data.py --gate --target <commit> [--repo OWNER/REPO]

Without --generated it runs in a checkout of --target, whose committed manifests name the new tag. With --generated
(the workflow) the manifests naming the tag were generated from --target and are not committed yet: the working
tree's tests/yldot outside references/ must be --target's, and every manifest naming the tag must record --target as
its provenance commit; the PR commits the manifests afterwards. --renumber (with --generated) takes N = the highest
existing yldot-data-v* (release or remote tag) + 1 instead of --tag, rewriting the release of the manifests that name
--tag, and on a tag collision at publish moves to N + 1 (at most ATTEMPTS tries). --gate only checks --target.

It collects every external file of the manifests (tests/yldot/references/*.manifest.json) whose release is --tag,
checks each file in the working tree (symlinks resolved) against its SHA-256 and size, and refuses (exit 1) if

  - the tag already exists (gh release view, or a git tag on the remote without a release: git ls-remote), or N is
    not the highest existing yldot-data-v* + 1;
  - --target is neither in origin/v9-develop's history nor the head of an open PR into v9-develop (fetch first);
  - the working tree's tests/yldot/references differs from --target's (git diff <target> -- tests/yldot/references),
    or with --generated the checks above;
  - a file is missing or differs from its manifest.

It then stages the files under their asset names (manifest.asset_name) in a temporary directory and prints the exact
`gh release create` command. Only with --publish does it create the tag at --target through the git refs API (atomic:
an existing tag fails the call, PRD 7.3 "Numbering") and then run that command with --verify-tag, all assets in that
one call (immutable releases take no assets after publishing), and then downloads the release again and checks every
SHA-256 (fetch_data.download). A tag created whose release then fails stays (the tag ruleset blocks deletion): its N
is used up. Old releases are never overwritten or deleted here. The last line of a successful run is tag=<tag>.

Exit codes: 0 dry run printed, gate passed, or published and verified; 1 refused or the check after publishing
failed; 2 usage.
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
ATTEMPTS = 3  # tag creations under --renumber


class Refused(Exception):
    pass


class Collision(Exception):
    """The tag exists on the remote already."""


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
    rc, out, err = run(["git", "ls-remote", "--tags", "https://github.com/{}.git".format(repo), "refs/tags/" + tag])
    if rc != 0:
        raise Refused("git ls-remote failed: {}".format(err.strip()))
    if out.strip():
        raise Refused("tag {} exists without a release (a deleted release keeps its tag): never reused; take the next "
                      "N".format(tag))
    rc, _, _ = run(["gh", "release", "view", tag, "-R", repo])
    if rc == 0:
        raise Refused("release {} already exists: never overwritten; take the next N".format(tag))
    numbers = existing(repo, run)
    want = max(numbers, default=0) + 1
    if number(tag) != want:
        raise Refused("{}: the next data release is yldot-data-v{} (existing: {})".format(tag, want, sorted(numbers)))


def number(tag):
    return int(tag.rsplit("v", 1)[1])


def existing(repo, run=run):
    """The N of every yldot-data-v<N> release and remote tag (a tag without a release has used up its N)."""
    rc, out, err = run(["gh", "release", "list", "-R", repo, "--limit", "1000", "--json", "tagName"])
    if rc != 0:
        raise Refused("gh release list failed: {}".format(err.strip()))
    tags = {t["tagName"] for t in json.loads(out or "[]")}
    rc, out, err = run(["git", "ls-remote", "--tags", "https://github.com/{}.git".format(repo),
                        "refs/tags/yldot-data-v*"])
    if rc != 0:
        raise Refused("git ls-remote failed: {}".format(err.strip()))
    tags |= {line.split("refs/tags/", 1)[1] for line in out.splitlines() if "refs/tags/" in line}
    return {number(t) for t in tags if mf.TAG_RE.match(t)}


def create_tag(tag, sha, repo, run=run):
    """Creates refs/tags/<tag> at sha on the remote; Collision if it exists (the refs API refuses an existing ref)."""
    rc, _, err = run(["gh", "api", "-X", "POST", "repos/{}/git/refs".format(repo), "-f", "ref=refs/tags/" + tag,
                      "-f", "sha=" + sha])
    if rc == 0:
        return
    if "Reference already exists" in err:
        raise Collision(tag)
    raise Refused("creating tag {} failed: {}".format(tag, err.strip()))


def relabel(suite, old, new):
    """Rewrites release old to new in every manifest that names old; returns their families."""
    names = []
    for p in sorted((Path(suite) / "references").glob("*.manifest.json")):
        m = mf.load(p)
        if m["release"] == old:
            m["release"] = new
            mf.dump(m, p)
            names.append(m["family"])
    return names


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


def check_manifests(sha, root, run=run):
    """The working tree's manifests are those at the target commit."""
    rc, _, _ = run(["git", "-C", str(root), "diff", "--quiet", sha, "--", "tests/yldot/references"])
    if rc != 0:
        raise Refused("tests/yldot/references in the working tree differs from --target {}: run this in a checkout "
                      "of --target".format(sha[:12]))


def check_generated(sha, root, suite, tag, run=run):
    """--generated: tests/yldot outside references/ is --target's, and every manifest naming tag was generated from
    it (provenance.commit)."""
    rc, _, _ = run(["git", "-C", str(root), "diff", "--quiet", sha, "--", "tests/yldot",
                    ":(exclude)tests/yldot/references"])
    if rc != 0:
        raise Refused("tests/yldot outside references/ in the working tree differs from --target {}".format(sha[:12]))
    for p in sorted((Path(suite) / "references").glob("*.manifest.json")):
        m = mf.load(p)
        if m["release"] == tag and (m.get("provenance") or {}).get("commit") != sha:
            raise Refused("{}: generated from {}, not from --target {}".format(
                p.name, (m.get("provenance") or {}).get("commit"), sha[:12]))


def release(tag, target, suite=mf.SUITE, repo=fetch_data.REPO, publish=False, run=run,
            download=fetch_data.download, out=print, generated=False, renumber=False, note=None):
    """Returns the exit code."""
    if not mf.TAG_RE.match(tag):
        out("error: --tag {!r}, need yldot-data-v<N>".format(tag))
        return 2
    if renumber and not generated:
        out("error: --renumber rewrites manifests, so only uncommitted ones (--generated)")
        return 2
    root = Path(suite).resolve().parent.parent
    try:
        if renumber:
            want = "yldot-data-v{}".format(max(existing(repo, run), default=0) + 1)
            if want != tag:
                out("renumbered: {} -> {} ({})".format(tag, want, ", ".join(relabel(suite, tag, want))))
                tag = want
        files = collect(suite, tag)
        check_tag(tag, repo, run)
        sha = check_target(target, repo, run)
        if generated:
            check_generated(sha, root, suite, tag, run)
        else:
            check_manifests(sha, root, run)
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
        if not publish:
            out(shlex.join(create_cmd(tag, sha, repo, note, files, stage, generated)))
            out("dry run: nothing published (the tag is created first; the staged files are removed on exit; re-run "
                "with --publish)")
            out("tag={}".format(tag))
            return 0
        for attempt in range(1, (ATTEMPTS if renumber else 1) + 1):
            try:
                create_tag(tag, sha, repo, run)
                break
            except Collision:
                if attempt == (ATTEMPTS if renumber else 1):
                    out("refused: tag {} was created meanwhile (attempt {}); take the next N".format(tag, attempt))
                    return 1
                new = "yldot-data-v{}".format(number(tag) + 1)
                out("collision: {} exists; renumbered to {} ({})".format(tag, new, ", ".join(relabel(suite, tag, new))))
                tag = new
            except Refused as e:
                out("refused: {}".format(e))
                return 1
        cmd = create_cmd(tag, sha, repo, note, files, stage, generated)
        out(shlex.join(cmd))
        rc, o, err = run(cmd)
        if rc != 0:
            out("error: gh release create failed ({}): {}; tag {} exists without a release, its N is used up".format(
                rc, err.strip(), tag))
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
        out("tag={}".format(tag))
        return 0
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def create_cmd(tag, sha, repo, note, files, stage, generated=False):
    """The gh release create command: the tag exists already (create_tag), all assets in this one call."""
    notes = (note.strip() + "\n\n" if note else "") + (
        "yldot reference data (epic AIUE-9), named by tests/yldot/references/*.manifest.json {} {}.\n\n"
        .format("generated from" if generated else "at", sha)) + "\n".join("{}  {}  {} bytes".format(e["sha256"], asset, e["bytes"]) for _, asset, e, _ in files)
    return ["gh", "release", "create", tag, "-R", repo, "--verify-tag", "--target", sha, "--title", tag, "--notes",
            notes, "--latest=false"] + [str(stage / asset) for _, asset, _, _ in files]


def gate(target, repo=fetch_data.REPO, run=run, out=print):
    """--gate: only the target check (the workflow's first job). Returns the exit code."""
    try:
        sha = check_target(target, repo, run)
    except Refused as e:
        out("refused: {}".format(e))
        return 1
    out("gate: {} may publish (in origin/{} or an open PR head into it)".format(sha, BASE))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", help="yldot-data-v<N>, N = the highest existing + 1 (required unless --gate)")
    parser.add_argument("--target", required=True, help="the commit whose manifests name the tag")
    parser.add_argument("--repo", default=fetch_data.REPO, help="the GitHub repository")
    parser.add_argument("--publish", action="store_true", help="publish (outward-facing; the owner's call)")
    parser.add_argument("--generated", action="store_true",
                        help="the manifests naming --tag were generated from --target and are not committed")
    parser.add_argument("--renumber", action="store_true", help="with --generated: take the next free N")
    parser.add_argument("--note", help="the first paragraph of the release notes")
    parser.add_argument("--gate", action="store_true", help="only check that --target may publish")
    args = parser.parse_args(argv[1:])
    if args.gate:
        return gate(args.target, repo=args.repo)
    if args.tag is None:
        parser.error("--tag is required unless --gate")
    return release(args.tag, args.target, repo=args.repo, publish=args.publish, generated=args.generated,
                   renumber=args.renumber, note=args.note)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
