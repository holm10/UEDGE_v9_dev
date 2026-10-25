"""The yldot suite's CI shards (epic AIUE-9, PRD sections 4 and 7.9; AIUE-103).

Usage (from anywhere):
    python shards.py                  # the shard names as a JSON list (the CI matrix)
    python shards.py --check NAME...  # exit 2 naming any unknown shard

One shard per family (a directory under tests/yldot/families with an input.py, the rule of conftest.py's
FAMILY_NAMES) plus "common". A test belongs to the family shard named by its "family" parameter, and to "common"
when it has none (or a value that is no family). conftest.py's --yldot-shard NAME keeps only that shard's tests.

Every test has exactly one shard, so the shards partition the suite by construction; a run of every shard covers the
suite exactly when the shard list is names(), which build-test-wheel.yml takes from this tool. Standard library only:
the CI build job lists the shards before UEDGE, numpy or h5py is installed.

Exit codes: 0 listed or every name known, 2 usage (an unknown name).
"""
import argparse
import json
import sys
from pathlib import Path

COMMON = "common"
FAMILIES = Path(__file__).resolve().parents[1] / "families"


def families():
    """The family names, sorted: directories under tests/yldot/families holding an input.py."""
    return sorted(p.name for p in FAMILIES.iterdir() if (p / "input.py").is_file())


def names():
    """Every shard: common first, then the families."""
    return [COMMON] + families()


def shard_of(params, known=None):
    """The shard of a test from its parameters (pytest's callspec.params, {} for an unparametrised test)."""
    family = params.get("family")
    return family if isinstance(family, str) and family in (families() if known is None else known) else COMMON


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", nargs="+", metavar="NAME", help="exit 2 if any NAME is not a shard")
    args = parser.parse_args(argv[1:])
    if args.check:
        unknown = [n for n in args.check if n not in names()]
        if unknown:
            print("error: unknown shard(s) {}; the shards are {}".format(", ".join(unknown), ", ".join(names())),
                  file=sys.stderr)
            return 2
        return 0
    print(json.dumps(names()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
