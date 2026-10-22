"""The per-family reference manifest of the yldot suite (PRD sections 7.3 and 7.6; decisions 12, 27, 29).

    m = load("d_only")                    # references/d_only.manifest.json, validated
    dump(m, path("d_only"))               # deterministic text: sorted keys, two-space indent, trailing newline

The manifest is the reviewable text next to each family's one binary reference file. It holds:
    schema, family, store ("full" | "sketch"), release (the data release tag "yldot-data-v<N>", or null for a local
    preview), sketch ({k, seed}; sketch store only);
    external    {path relative to tests/yldot: {sha256, bytes}}: every file kept outside git (the reference .h5 and
                the owner families' states and grids). The only record of their SHA-256s (owner, 2026-10-21, AIUE-84);
                the release asset of a path is asset_name(path);
    datasets    {HDF5 dataset path: SHA-256 of its data (store.dataset_sha256)}: every dataset of the reference file,
                recomputed at each read;
    guarded     the steady and timestep defaults (yldot and the Jacobian-flag difference), their sigma, and the
                locality patterns (AIUE-100); unguarded: the diagnostics (summarize);
    provenance  {commit, compiler, flags, runner_image, numpy, h5py, date};
    variables   {variant id: {class, reason, applied, d (variants.encode form), phase, config, sha256 (of the
                variant's stored datasets, or null), block_l2, jflag_block_l2}}. block_l2 is the L2 norm of
                yldot_variant - yldot_default per (equation, species, region) block, zero blocks omitted (owner,
                2026-10-21, AIUE-84); jflag_block_l2 the same for the flag differences.

A manifest with only external files (an owner family before its references exist) is valid. Every problem found by
validate raises one ManifestError listing all of them.
"""
import datetime
import hashlib
import json
import re
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent
SCHEMA = 1
STORES = ("full", "sketch")
CONFIG_NAMES = ("steady", "timestep")
CLASSES = ("SENSITIVE", "INERT", "MARGINAL", "INVALID", "EXCLUDED")
PHASES = ("PRE", "POST")
TAG_RE = re.compile(r"^yldot-data-v[1-9][0-9]*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
PATH_RE = re.compile(r"^(families|references)(/[A-Za-z0-9_.][A-Za-z0-9_.-]*)+$")  # no glob characters, no ".."
PROVENANCE = ("commit", "compiler", "flags", "runner_image", "numpy", "h5py", "date")
REQUIRED = ("schema", "family", "store", "release", "external")
WITH_DATA = ("datasets", "guarded", "unguarded", "provenance", "variables")


class ManifestError(Exception):
    """A manifest that does not follow the schema."""


def path(family, suite=SUITE):
    return Path(suite) / "references" / "{}.manifest.json".format(family)


def reference_path(family):
    """The reference file's path in the manifest's external table (relative to tests/yldot)."""
    return "references/{}.h5".format(family)


def asset_name(p):
    """The release asset name of an external path: the path with "/" replaced by "--"."""
    return p.replace("/", "--")


def dumps(m):
    return json.dumps(m, indent=2, sort_keys=True) + "\n"


def dump(m, target):
    validate(m)
    Path(target).write_text(dumps(m))


def load(family_or_path, suite=SUITE):
    p = Path(family_or_path)
    if p.suffix != ".json":
        p = path(family_or_path, suite)
    with open(p) as f:
        m = json.load(f)
    validate(m)
    return m


def combined_sha(shas):
    """One SHA-256 over {name: sha}: of the "name sha" lines in sorted order."""
    h = hashlib.sha256()
    for name in sorted(shas):
        h.update("{} {}\n".format(name, shas[name]).encode())
    return h.hexdigest()


def summarize(datasets):
    """The guarded and unguarded SHA-256s from the dataset SHAs of a reference file."""
    guarded, unguarded = {}, {}
    for config in CONFIG_NAMES:
        base = "/{}/default/".format(config)
        vec = {n: s for n, s in datasets.items()
               if n == base + "yldot" or n.startswith(base + "jflag/")}
        if vec:
            guarded["{}/default".format(config)] = combined_sha(vec)
        sig = {n: s for n, s in datasets.items() if n == base + "sigma"}
        if sig:
            guarded["{}/sigma".format(config)] = combined_sha(sig)
    diag = {n: s for n, s in datasets.items() if "/diagnostics/" in n}
    if diag:
        unguarded["diagnostics"] = combined_sha(diag)
    return guarded, unguarded


def variant_sha(datasets, config, vid):
    """The SHA-256 of one variant's stored datasets, or None if it stores none."""
    prefix = "/{}/variants/{}/".format(config, vid)
    shas = {n: s for n, s in datasets.items() if n.startswith(prefix)}
    return combined_sha(shas) if shas else None


def provenance(commit, compiler, flags, runner_image):
    """The provenance record, with the numpy and h5py versions of this process and the UTC date."""
    import h5py
    import numpy

    return {"commit": commit, "compiler": compiler, "flags": flags, "runner_image": runner_image,
            "numpy": numpy.__version__, "h5py": h5py.__version__,
            "date": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()}


def _encoded(e):
    return e is None or (isinstance(e, dict) and set(e) == {"dtype", "shape", "data"})


def _norms(where, d, errors):
    if not isinstance(d, dict) or not all(isinstance(k, str) and isinstance(v, float) and v > 0 for k, v in d.items()):
        errors.append("{}: need {{block label: positive float}}".format(where))


def validate(m):
    errors = []
    if not isinstance(m, dict):
        raise ManifestError("manifest: not a JSON object")
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        errors.append("missing keys {}".format(missing))
    unknown = sorted(set(m) - set(REQUIRED) - set(WITH_DATA) - {"sketch"})
    if unknown:
        errors.append("unknown keys {}".format(unknown))
    if m.get("schema") != SCHEMA:
        errors.append("schema = {!r}, need {}".format(m.get("schema"), SCHEMA))
    if not isinstance(m.get("family"), str) or not m.get("family"):
        errors.append("family must be a non-empty string")
    if m.get("store") not in STORES:
        errors.append("store = {!r}, need one of {}".format(m.get("store"), STORES))
    release = m.get("release")
    if release is not None and not (isinstance(release, str) and TAG_RE.match(release)):
        errors.append("release = {!r}, need null or yldot-data-v<N>".format(release))
    external = m.get("external", {})
    if not isinstance(external, dict):
        errors.append("external must be an object")
        external = {}
    assets = {}
    for p, e in external.items():
        if not PATH_RE.match(p) or ".." in p.split("/"):
            errors.append("external path {!r}: need families/... or references/..., [A-Za-z0-9_.-] only".format(p))
        if not (isinstance(e, dict) and set(e) == {"sha256", "bytes"} and isinstance(e["sha256"], str)
                and SHA_RE.match(e["sha256"]) and isinstance(e["bytes"], int) and e["bytes"] >= 0):
            errors.append("external {!r}: need {{sha256: 64 hex, bytes: int >= 0}}".format(p))
        assets.setdefault(asset_name(p), []).append(p)
    clash = [v for v in assets.values() if len(v) > 1]
    if clash:
        errors.append("external paths share an asset name: {}".format(clash))
    with_data = [k for k in WITH_DATA if k in m]
    if with_data:
        absent = [k for k in WITH_DATA if k not in m]
        if absent:
            errors.append("a manifest with {} also needs {}".format(with_data, absent))
        if isinstance(m.get("family"), str) and reference_path(m["family"]) not in external:
            errors.append("external has no {}".format(reference_path(m.get("family"))))
        if m.get("store") == "sketch":
            sk = m.get("sketch")
            if not (isinstance(sk, dict) and set(sk) == {"k", "seed"} and all(isinstance(v, int) for v in sk.values())
                    and sk["k"] > 0):
                errors.append("sketch must be {k: int > 0, seed: int}")
        datasets = m.get("datasets", {})
        if not (isinstance(datasets, dict) and datasets and all(
                isinstance(n, str) and n.startswith("/") and isinstance(s, str) and SHA_RE.match(s)
                for n, s in datasets.items())):
            errors.append("datasets must map /paths to 64-hex SHA-256s")
        for key in ("guarded", "unguarded"):
            d = m.get(key, {})
            if not (isinstance(d, dict) and all(isinstance(s, str) and SHA_RE.match(s) for s in d.values())):
                errors.append("{} must map names to 64-hex SHA-256s".format(key))
        prov = m.get("provenance", {})
        if not (isinstance(prov, dict) and set(prov) == set(PROVENANCE) and all(isinstance(v, str) for v in prov.values())):
            errors.append("provenance must hold exactly {} as strings".format(list(PROVENANCE)))
        variables = m.get("variables", {})
        if not isinstance(variables, dict):
            errors.append("variables must be an object")
            variables = {}
        for vid, v in variables.items():
            where = "variables[{!r}]".format(vid)
            if "/" in vid:
                errors.append("{}: a variant id may not contain '/'".format(where))
            keys = {"class", "reason", "applied", "d", "phase", "config", "sha256", "block_l2", "jflag_block_l2"}
            if not isinstance(v, dict) or set(v) != keys:
                errors.append("{}: need exactly the keys {}".format(where, sorted(keys)))
                continue
            if v["class"] not in CLASSES:
                errors.append("{}: class {!r}, need one of {}".format(where, v["class"], CLASSES))
            if not isinstance(v["reason"], str):
                errors.append("{}: reason must be a string".format(where))
            if v["phase"] not in PHASES or v["config"] not in CONFIG_NAMES:
                errors.append("{}: phase {!r} / config {!r}".format(where, v["phase"], v["config"]))
            if not (_encoded(v["applied"]) and _encoded(v["d"])):
                errors.append("{}: applied and d must be null or variants.encode values".format(where))
            sha = v["sha256"]
            if v["class"] == "SENSITIVE" and not (isinstance(sha, str) and SHA_RE.match(sha)):
                errors.append("{}: a SENSITIVE variant needs the SHA-256 of its stored data".format(where))
            if v["class"] != "SENSITIVE" and sha is not None:
                errors.append("{}: only a SENSITIVE variant stores data (sha256 must be null)".format(where))
            _norms(where + ".block_l2", v["block_l2"], errors)
            _norms(where + ".jflag_block_l2", v["jflag_block_l2"], errors)
    if errors:
        raise ManifestError("manifest {}: {}".format(m.get("family", "?"), "; ".join(errors)))
