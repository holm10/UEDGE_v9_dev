"""The per-family reference manifest of the yldot suite (PRD sections 7.3 and 7.6; decisions 12, 27, 29).

    m = load("d_only")                    # references/d_only.manifest.json, validated (loads: runs expanded)
    dump(m, path("d_only"))               # deterministic text: sorted keys, two-space indent, trailing newline,
                                          # each encoded value's data (or runs) list on one line (dumps)

The manifest is the reviewable text next to each family's one binary reference file. It holds:
    schema, family, store ("full" | "sketch"), release (the data release tag "yldot-data-v<N>", or null for a local
    preview), sketch ({k, seed}; sketch store only);
    external    {path relative to tests/yldot: {sha256, bytes}}: every file kept outside git (the reference .h5 and
                the owner families' states and grids). The only record of their SHA-256s (owner, 2026-10-21, AIUE-84);
                the release asset of a path is asset_name(path);
    datasets    {HDF5 dataset path: SHA-256 of its data (store.dataset_sha256)}: every dataset of the reference file,
                recomputed at each read;
    guarded     the steady and timestep defaults (yldot and the Jacobian-flag difference), their sigma, a sketch
                store's sketch thresholds (<config>/sketch_threshold, AIUE-92) and weights (<config>/sketch_weight,
                AIUE-174) and the locality pattern
                (locality/steady over the /steady/locality datasets, AIUE-100); unguarded: the diagnostics
                (summarize);
    provenance  {commit, compiler, flags, runner_image, numpy, h5py, date};
    variables   {variant id: {class, reason, applied, d (variants.encode form), phase, config, sha256 (of the
                variant's stored datasets, or null), block_l2, jflag_block_l2}}. block_l2 is the L2 norm of
                yldot_variant - yldot_default per (equation, species, region) block, zero blocks omitted (owner,
                2026-10-21, AIUE-84); jflag_block_l2 the same for the flag differences;
    locality_variants (optional) {variant id: {config, sha256, added, dropped}}: the variants whose locality pattern
                the reference stores as a difference from the default pattern (store.py, /<config>/locality_variants;
                AIUE-101), with the SHA-256 of the variant's slice (store.locality_slice_sha) and its entry counts;
                guarded as locality_variants/<config> over the packed datasets.

In the text, an encoded value {dtype, shape, data} whose data has repeated neighbours is written as {dtype, shape,
runs: [[value, count], ...]} when that has fewer entries (owner, 2026-10-25, AIUE-190: the manifests' bulk was the
applied and d arrays); loads expands it, so in memory every encoded value has its data list. Read manifest text
with load or loads, never json.loads.

A manifest with only external files (an owner family before its references exist) is valid. Every problem found by
validate raises one ManifestError listing all of them.
"""
import datetime
import hashlib
import json
import math
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


def family_assets(m):
    """The external paths under families/<family>/ of manifest m: an owner family's states, grid and inputs, and its
    sigma.h5 once measured (owner, 2026-10-22, AIUE-92 D6). A small family keeps them in git: none."""
    prefix = "families/{}/".format(m["family"])
    return sorted(p for p in m["external"] if p.startswith(prefix))


def owner_family(family, suite=SUITE):
    """Whether family is an owner family: its manifest names release assets under families/<family>/."""
    return path(family, suite).is_file() and bool(family_assets(load(family, suite)))


ENCODED = {"dtype", "shape", "data"}
RUNS = {"dtype", "shape", "runs"}
MAX_RUN_VALUES = 10 ** 7  # an expanded runs form, at most (largest real value 25,344 at AIUE-190): the guard reads PR
                          # manifests, and a few bytes of runs must not expand to gigabytes


def runs(data):
    """[[value, count], ...] of the consecutive equal values of data; equal means the same JSON text, so -0.0 and 0.0
    (and 1 and 1.0) stay apart and expanding the runs gives data back bit for bit."""
    out, last = [], None
    for x in data:
        text = json.dumps(x)
        if out and text == last:
            out[-1][1] += 1
        else:
            out.append([x, 1])
            last = text
    return out


def _text(o, level):
    """json.dumps(o, indent=2, sort_keys=True) at nesting level, but an encoded value's data list on one line, written
    as its runs when they are fewer."""
    pad, end = "  " * (level + 1), "  " * level
    if isinstance(o, dict) and o:
        flat = set(o) == ENCODED
        if flat and isinstance(o["data"], list):
            r = runs(o["data"])
            if len(r) < len(o["data"]):
                o = {"dtype": o["dtype"], "shape": o["shape"], "runs": r}
        return "{\n" + ",\n".join("{}{}: {}".format(pad, json.dumps(k), json.dumps(o[k]) if flat and k != "shape"
                                                    else _text(o[k], level + 1)) for k in sorted(o)) + "\n" + end + "}"
    if isinstance(o, list) and o:
        return "[\n" + ",\n".join(pad + _text(v, level + 1) for v in o) + "\n" + end + "]"
    return json.dumps(o)


def dumps(m):
    """The manifest's text: sorted keys, two-space indent, trailing newline (json.dumps(m, indent=2, sort_keys=True)),
    except that each encoded value's data list (variants.encode: an applied value or d) is on one line (owner,
    2026-10-22, AIUE-94 D9), as runs when they are fewer (owner, 2026-10-25, AIUE-190); loads gives m back."""
    return _text(m, 0) + "\n"


def _expand(o, where, errors):
    if isinstance(o, dict):
        if set(o) == RUNS:
            r, shape = o["runs"], o["shape"]
            if not (isinstance(r, list) and all(isinstance(e, list) and len(e) == 2 and _int(e[1]) and e[1] >= 1
                                                for e in r)):
                errors.append("{}: runs must be [[value, int count >= 1], ...]".format(where))
                return o
            if not (isinstance(shape, list) and all(_int(n) and n >= 0 for n in shape)):
                errors.append("{}: shape must be a list of ints >= 0".format(where))
                return o
            total = sum(n for _, n in r)
            if total > MAX_RUN_VALUES:
                errors.append("{}: runs hold {} values, more than {}".format(where, total, MAX_RUN_VALUES))
                return o
            if total != math.prod(shape):
                errors.append("{}: runs hold {} values, shape {} needs {}".format(where, total, shape,
                                                                                    math.prod(shape)))
                return o
            return {"dtype": o["dtype"], "shape": shape, "data": [x for x, n in r for _ in range(n)]}
        return {k: _expand(v, "{}.{}".format(where, k), errors) for k, v in o.items()}
    if isinstance(o, list):
        return [_expand(v, "{}[{}]".format(where, i), errors) for i, v in enumerate(o)]
    return o


def loads(text):
    """The manifest m of its text (dumps): json.loads with every runs form expanded to its data list. Raises
    ManifestError on a malformed runs form; does not validate (load does)."""
    errors = []
    m = _expand(json.loads(text), "manifest", errors)
    if errors:
        raise ManifestError("; ".join(errors))
    return m


def dump(m, target):
    validate(m)
    Path(target).write_text(dumps(m))


def load(family_or_path, suite=SUITE):
    p = Path(family_or_path)
    if p.suffix != ".json":
        p = path(family_or_path, suite)
    m = loads(p.read_text())
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
        thr = {n: s for n, s in datasets.items() if n.startswith(base + "sketch_threshold/")}
        if thr:
            guarded["{}/sketch_threshold".format(config)] = combined_sha(thr)
        wgt = {n: s for n, s in datasets.items() if n == base + "sketch_weight"}
        if wgt:
            guarded["{}/sketch_weight".format(config)] = combined_sha(wgt)
        loc = {n: s for n, s in datasets.items() if n.startswith("/{}/locality/".format(config))}
        if loc:
            guarded["locality/{}".format(config)] = combined_sha(loc)
        lv = {n: s for n, s in datasets.items() if n.startswith("/{}/locality_variants/".format(config))}
        if lv:
            guarded["locality_variants/{}".format(config)] = combined_sha(lv)
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


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _norms(where, d, errors):
    if not isinstance(d, dict) or not all(isinstance(k, str) and isinstance(v, float) and math.isfinite(v) and v > 0
                                              for k, v in d.items()):
        errors.append("{}: need {{block label: finite positive float}}".format(where))


def _locality_variants(m, variables, errors):
    loc = m.get("locality_variants", {})
    if not isinstance(loc, dict):
        errors.append("locality_variants must be an object")
        return
    for vid, e in loc.items():
        where = "locality_variants[{!r}]".format(vid)
        if not (isinstance(e, dict) and set(e) == {"config", "sha256", "added", "dropped"}):
            errors.append("{}: need exactly the keys config, sha256, added, dropped".format(where))
            continue
        v = variables.get(vid)
        if not (isinstance(v, dict) and v.get("config") == e["config"]
                and v.get("class") in ("SENSITIVE", "INERT", "MARGINAL")):
            errors.append("{}: not a SENSITIVE, INERT or MARGINAL variable of config {!r}".format(where, e["config"]))
        if not (isinstance(e["sha256"], str) and SHA_RE.match(e["sha256"])):
            errors.append("{}: sha256 must be 64 hex".format(where))
        if not (_int(e["added"]) and _int(e["dropped"]) and e["added"] >= 0 and e["dropped"] >= 0):
            errors.append("{}: added and dropped must be integers >= 0".format(where))


def validate(m):
    errors = []
    if not isinstance(m, dict):
        raise ManifestError("manifest: not a JSON object")
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        errors.append("missing keys {}".format(missing))
    unknown = sorted(set(m) - set(REQUIRED) - set(WITH_DATA) - {"sketch", "locality_variants"})
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
                and SHA_RE.match(e["sha256"]) and _int(e["bytes"]) and e["bytes"] >= 0):
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
            if not (isinstance(sk, dict) and set(sk) == {"k", "seed"} and all(_int(v) for v in sk.values())
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
        if not (isinstance(prov, dict) and set(prov) == set(PROVENANCE)
                and all(isinstance(v, str) for v in prov.values())):
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
        _locality_variants(m, variables, errors)
    elif "locality_variants" in m:
        errors.append("locality_variants without the reference data")
    if errors:
        raise ManifestError("manifest {}: {}".format(m.get("family", "?"), "; ".join(errors)))
