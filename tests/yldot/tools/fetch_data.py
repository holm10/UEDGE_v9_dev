"""Fetch and verify the yldot suite's external files (epic AIUE-9, PRD sections 7.3 and 7.6; decision 29).

Usage (from anywhere):
    python fetch_data.py [family ...] [--repo OWNER/REPO] [--check]

Every file kept outside git (the reference .h5 files, the owner families' states and grids) is named, with its
SHA-256 and size, in the external table of tests/yldot/references/<family>.manifest.json, under the manifest's data
release tag yldot-data-v<N>. For each manifest (default: all) this tool

  1. checks the files already in tests/yldot/.data/<tag>/ (gitignored) and refuses any whose SHA-256 or size
     differs from the manifest: it never overwrites one, remove it by hand and re-run;
  2. downloads the missing ones with `gh release download <tag>` into a temporary directory, checks each and moves
     it into .data/<tag>/; a file that fails the check is deleted and nothing is linked for it;
  3. links each file at its manifest path with a relative symlink (owner, 2026-10-21, AIUE-84), e.g.
     families/large_dd2c/base_state.h5 -> ../../.data/yldot-data-v2/families--large_dd2c--base_state.h5, so the
     harness and input.py read them by name. A regular file already at that path is accepted only if its SHA-256
     matches; a link is re-pointed.

--check verifies only (the cache and the links), never downloads. A manifest without a release (a local preview) is
skipped. gh uses its own login; CI provides its token in the workflow. Release asset names are the external paths
with "/" replaced by "--" (manifest.asset_name).

Exit codes: 0 every file verified and linked, 1 a file missing, different from its manifest or not downloadable,
2 usage (an unknown family, an invalid manifest).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/, for the yldot package

from yldot.harness import manifest as mf  # noqa: E402
from yldot.harness.store import file_sha256  # noqa: E402

REPO = "holm10/UEDGE_v9_dev"


class FetchError(Exception):
    pass


def matches(path, entry):
    """None if path holds the manifest's bytes, else what differs."""
    size = path.stat().st_size
    if size != entry["bytes"]:
        return "{} bytes, the manifest {}".format(size, entry["bytes"])
    sha = file_sha256(path)
    if sha != entry["sha256"]:
        return "SHA-256 {}, the manifest {}".format(sha, entry["sha256"])
    return None


def download(tag, assets, dest, repo=REPO):
    """gh release download of the named assets of tag into dest."""
    if shutil.which("gh") is None:
        raise FetchError("gh (GitHub CLI) is not on PATH")
    cmd = ["gh", "release", "download", tag, "-R", repo, "-D", str(dest)]
    for a in assets:
        cmd += ["-p", a]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise FetchError("{} failed ({}): {}".format(" ".join(cmd), r.returncode, r.stderr.strip()))


def manifests(suite, families):
    ref = Path(suite) / "references"
    found = {p.name[:-len(".manifest.json")]: p for p in sorted(ref.glob("*.manifest.json"))} if ref.is_dir() else {}
    unknown = sorted(set(families) - set(found))
    if unknown:
        raise mf.ManifestError("no manifest for {} in {}".format(unknown, ref))
    return {f: mf.load(p) for f, p in found.items() if not families or f in families}


def link(target, at):
    """A relative symlink at `at` to `target`, replacing a link that points elsewhere."""
    rel = os.path.relpath(target, at.parent)
    if at.is_symlink():
        if os.readlink(at) == rel:
            return "linked"
        at.unlink()
        os.symlink(rel, at)
        return "re-linked"
    at.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(rel, at)
    return "linked"


def fetch(suite=mf.SUITE, families=(), repo=REPO, check=False, download=download, out=print):
    """Verify, download and link; returns the exit code."""
    suite = Path(suite)
    try:
        found = manifests(suite, families)
    except (mf.ManifestError, ValueError) as e:
        out("error: {}".format(e))
        return 2
    if not found:
        out("no manifests in {}".format(suite / "references"))
        return 0
    problems = []
    for family, m in found.items():
        tag = m["release"]
        if tag is None:
            out("{}: no release (local preview), skipped".format(family))
            continue
        cache = suite / ".data" / tag
        entries = {p: (e, cache / mf.asset_name(p)) for p, e in m["external"].items()}
        ok, missing = set(), []
        for p, (e, cached) in entries.items():
            if cached.is_file():
                bad = matches(cached, e)
                if bad:
                    problems.append("{}: {} has {}: refused (remove it and re-run)".format(family, cached, bad))
                else:
                    ok.add(p)
            else:
                missing.append(p)
        if missing and check:
            problems += ["{}: {} not in {}".format(family, p, cache) for p in missing]
        elif missing:
            (suite / ".data").mkdir(exist_ok=True)
            tmp = Path(tempfile.mkdtemp(prefix=".{}-".format(tag), dir=suite / ".data"))
            try:
                download(tag, [mf.asset_name(p) for p in missing], tmp, repo)
                for p in missing:
                    e, cached = entries[p]
                    got = tmp / mf.asset_name(p)
                    if not got.is_file():
                        problems.append("{}: {} not in release {}".format(family, mf.asset_name(p), tag))
                        continue
                    bad = matches(got, e)
                    if bad:
                        got.unlink()
                        problems.append("{}: downloaded {} has {}: refused".format(family, mf.asset_name(p), bad))
                        continue
                    cache.mkdir(parents=True, exist_ok=True)
                    os.replace(got, cached)
                    ok.add(p)
                    out("{}: {} downloaded and verified".format(family, p))
            except FetchError as e:
                problems.append("{}: {}".format(family, e))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        for p in sorted(ok):
            e, cached = entries[p]
            at = suite / p
            if at.exists() and not at.is_symlink():
                bad = matches(at, e)
                if bad:
                    problems.append("{}: {} is a regular file with {}: refused".format(family, at, bad))
                else:
                    out("{}: {} regular file, verified".format(family, p))
                continue
            if check:
                if not (at.is_symlink() and at.resolve() == cached.resolve()):
                    problems.append("{}: {} is not linked to {}".format(family, at, cached))
                else:
                    out("{}: {} verified".format(family, p))
                continue
            out("{}: {} {}".format(family, p, link(cached, at)))
    for line in problems:
        out("error: " + line)
    return 1 if problems else 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("families", nargs="*", help="family names (default: every manifest)")
    parser.add_argument("--repo", default=REPO, help="the GitHub repository holding the data releases")
    parser.add_argument("--check", action="store_true", help="verify only, never download")
    args = parser.parse_args(argv[1:])
    return fetch(families=args.families, repo=args.repo, check=args.check)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
