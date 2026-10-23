"""Reference storage of the yldot suite (PRD sections 7.3 and 7.4; decisions 12, 27, 29): one HDF5 file per family
behind one interface, FullVectorStore for the small families and SketchStore for the large ones.

    w = create(path, "full", "d_only", result.data, imap)        # imap: compare.index_map(data, regions)
    w.write_default("steady", yldot, yldot_J, sigma, diagnostics)
    w.write_variant("steady", "bbb.cfvisx", yldot_v, yldot_J_v)  # SENSITIVE variants only
    written = w.finish()                                          # {datasets: {path: sha}, sha256, bytes}
    s = open_store("d_only")                                      # checks the file against its manifest
    s.check("steady", None, new_yldot, new_yldot_J, tol, imap).ok

Layout (root attributes schema, family, store; a sketch file also k and seed):
    /index/{idx*, igyl}, /index/masks/<is*onxy>, /index/grid/<name>   the index arrays of the generating run
    /index/block, /index/block_labels                                  block number per row, "ni[1] core" labels
    /<config>/default/{yldot, sigma}                                   full vectors in both stores
    /<config>/default/jflag/{index, value}                             rows where yldot_J != yldot, yldot_J - yldot
    /<config>/default/diagnostics/<name>                               full: every diagnostic array; sketch: res*
    sketch: /<config>/default/sketch_threshold/{block, cell_ix, cell_iy, cell_m, cell_block}
                                                                       sketch_thresholds of the default's tol_i
                                                                       (PRD 7.11 d; AIUE-92), cells in (ix, iy) order
    full:   /<config>/variants/<id>/yldot/{index, value}                rows differing (bitwise) from the default
            /<config>/variants/<id>/jflag/{index, value}                the variant's own flag difference
    sketch: /<config>/variants/<id>/{yldot, jflag}/{proj, l2, maxabs, argmax}
    /steady/locality/{delta, column, row, mismatch, dfull}             the locality entries with score > 1 at delta
                                                                       (locality.py, PRD 7.5; AIUE-100), both stores

Blocks are (equation, species, region) from compare.IndexMap.groups() (index truth, decision 19). A sketch projects a
block onto k Rademacher (+-1) vectors whose signs are the raw bits of numpy's PCG64 bit generator, which numpy keeps
stream-stable (Generator methods are not used); each block's vectors depend only on (seed, label, block size). Sums
are math.fsum, correctly rounded and independent of the order. The sketch comparator is
|<new - ref, r_j>| <= c * sqrt(sum tol_i^2) over the block, c = 6.5 (owner-confirmed, decision 30).

Integrity (PRD section 7.6): open_store checks the file's SHA-256, its set of datasets and its blocks against the
manifest and the family's regions, and that the manifest's guarded, unguarded and variant SHA-256s and the set of
stored variants follow from its datasets (a consistent tamper of file, datasets and external is caught there);
every dataset read recomputes the dataset's SHA-256. A mismatch raises
StoreIntegrityError, so a changed .h5 with an unchanged manifest fails. Files are written with track_times=False,
so writing the same data twice gives the same bytes, and in the HDF5 1.10 file format (LIBVER), whose smaller group
headers keep the many small variant groups within the per-family caps (owner, 2026-10-22, AIUE-94 D3); the dataset
SHA-256s do not depend on the format.
"""
import functools
import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import manifest as mf
from .compare import DIAG_SCALED_RTOL, compare, index_map, listed, load_regions
from .state import INDEX_ARRAYS, MASK_ARRAYS

K = 8
SEED = 20261019
C = 6.5  # owner-confirmed, decision 30
SCHEMA = 1
LIBVER = ("v110", "latest")  # owner, 2026-10-22 (AIUE-94 D3)
FETCH = "python tests/yldot/tools/fetch_data.py"


class StoreError(Exception):
    """A reference file that cannot be used: missing, from another index layout or other regions, or misused."""


class StoreIntegrityError(StoreError):
    """A reference file whose bytes or datasets differ from its manifest."""


# ---------------------------------------------------------------- hashing and sparse vectors


def dataset_sha256(a):
    """SHA-256 of "<dtype>|<shape>\\n" and the C-order bytes, numbers as little-endian."""
    a = np.asarray(a)
    if a.dtype.kind in "biufc":
        a = a.astype(a.dtype.newbyteorder("<"), copy=False)
    h = hashlib.sha256("{}|{}\n".format(a.dtype.str, tuple(a.shape)).encode())
    h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _f64(name, a, neq, finite=True):
    a = np.ascontiguousarray(a, dtype=np.float64)
    if a.shape != (neq,):
        raise ValueError("{} has shape {}, need ({},)".format(name, a.shape, neq))
    if finite and not np.isfinite(a).all():
        raise ValueError("{} has non-finite entries at rows {}".format(name, listed(np.flatnonzero(~np.isfinite(a))
                                                                                    + 1)))
    return a


def differs(a, b):
    """Rows where a and b differ bitwise (so -0.0 and 0.0 differ, and a NaN equals the same NaN)."""
    return np.ascontiguousarray(a, np.float64).view(np.uint64) != np.ascontiguousarray(b, np.float64).view(np.uint64)


def sparse_diff(new, base):
    """(index int32, value float64): the rows where new differs bitwise from base, and new's values there."""
    i = np.flatnonzero(differs(new, base)).astype(np.int32)
    return i, np.asarray(new, np.float64)[i]


def jflag_sparse(yldot, yldot_j):
    """The Jacobian-flag difference yldot_J - yldot as (index, value) over the rows where the two differ."""
    i = np.flatnonzero(differs(yldot_j, yldot)).astype(np.int32)
    return i, np.asarray(yldot_j, np.float64)[i] - np.asarray(yldot, np.float64)[i]


def dense(index, value, n, base=None):
    out = np.zeros(n) if base is None else np.array(base, dtype=np.float64)
    out[np.asarray(index, dtype=np.int64)] = value
    return out


# ---------------------------------------------------------------- blocks and sketches


def blocks(imap):
    """(labels, rows, block number per row) from imap.groups(): one block per (equation, species, region)."""
    groups = imap.groups()
    labels = ["{}[{}] {}".format(e, s, r) for (e, s, r) in groups]
    rows = list(groups.values())
    ids = np.full(imap.neq, -1, dtype=np.int32)
    for b, r in enumerate(rows):
        ids[r] = b
    if (ids < 0).any():
        raise StoreError("rows in no block (index map without regions?): {}".format(listed(np.flatnonzero(ids < 0)
                                                                                           + 1)))
    return labels, rows, ids


@functools.lru_cache(maxsize=4096)
def signs(seed, label, n, k):
    """k Rademacher vectors of length n for one block, as a read-only (k, n) int8 array of +-1.

    PCG64 seeded with SeedSequence(seed, spawn key (h,)), h the first 8 bytes of sha256(label) read little-endian;
    ceil(n/64) raw 64-bit words per vector in sequence, bits LSB first, 1 -> +1 and 0 -> -1."""
    h = int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "little")
    bg = np.random.PCG64(np.random.SeedSequence(entropy=seed, spawn_key=(h,)))
    m = -(-n // 64)
    words = np.asarray(bg.random_raw(k * m), dtype="<u8")
    bits = np.unpackbits(words.view(np.uint8), bitorder="little").reshape(k, m * 64)[:, :n]
    out = np.where(bits == 1, 1, -1).astype(np.int8)
    out.flags.writeable = False
    return out


def fsum(v):
    """math.fsum of a float array; NaN if any entry is not finite, Inf on overflow."""
    v = np.asarray(v, dtype=np.float64)
    if not np.isfinite(v).all():
        return float("nan")
    try:
        return math.fsum(v.tolist())
    except OverflowError:
        return float("inf")


def sketch(x, labels, rows, seed=SEED, k=K):
    """Per block: proj (nblock, k), l2, maxabs and argmax (the 0-based row of the largest |entry|)."""
    x = np.asarray(x, dtype=np.float64)
    nb = len(labels)
    out = {"proj": np.empty((nb, k)), "l2": np.empty(nb), "maxabs": np.empty(nb), "argmax": np.empty(nb, np.int32)}
    for b, (label, r) in enumerate(zip(labels, rows)):
        xb = x[r]
        s = signs(seed, label, len(xb), k)
        for j in range(k):
            out["proj"][b, j] = fsum(np.where(s[j] > 0, xb, -xb))
        out["l2"][b] = math.sqrt(fsum(xb * xb)) if np.isfinite(xb).all() else float("nan")
        a = np.abs(xb)
        i = int(np.argmax(a)) if not np.isnan(a).any() else int(np.flatnonzero(np.isnan(a))[0])
        out["maxabs"][b], out["argmax"][b] = a[i], r[i]
    return out


def block_l2(x, labels, rows):
    """{label: L2 norm} of x per block, zero blocks omitted (the manifest's block_l2, owner 2026-10-21)."""
    out = {}
    for label, r in zip(labels, rows):
        n = math.sqrt(fsum(np.asarray(x, dtype=np.float64)[r] ** 2))
        if n != 0:
            out[label] = n
    return out


@dataclass
class Check:
    ok: bool
    lines: list = field(default_factory=list)

    @property
    def report(self):
        return "\n".join(self.lines)


def sketch_compare(ref, new, tol, labels, rows, imap, c=C, what="yldot"):
    """|P_new[b, j] - P_ref[b, j]| <= c * sqrt(fsum(tol_i^2 over block b)) for every block and projection (PRD
    section 7.4); a non-finite projection fails. ref, new: sketch() dicts; tol: the per-entry tolerances."""
    tol = np.asarray(tol, dtype=np.float64)
    if tol.shape != (imap.neq,) or not (np.isfinite(tol).all() and (tol > 0).all()):
        raise ValueError("tol must have shape ({},) and be finite and > 0 at every entry".format(imap.neq))
    fails = []
    for b, label in enumerate(labels):
        bound = c * math.sqrt(fsum(tol[rows[b]] ** 2))
        with np.errstate(invalid="ignore"):
            d = np.abs(np.asarray(new["proj"][b]) - np.asarray(ref["proj"][b]))
            bad = ~(d <= bound)
        if bad.any():
            ratio = d / bound
            ratio[~np.isfinite(ratio)] = np.inf
            fails.append((float(ratio.max()), b))
    if not fails:
        return Check(True, ["{} PASS: all {} blocks within c*sqrt(sum tol^2), c = {}".format(what, len(labels), c)])
    lines = ["{} FAIL: {} of {} blocks out of tolerance (c = {})".format(what, len(fails), len(labels), c)]
    for ratio, b in sorted(fails, reverse=True):
        lines.append("  {:24s} worst |dP|/bound {:.3g}; largest |entry| stored {} ({:.6e}), new {} ({:.6e}); "
                     "L2 stored {:.6e} new {:.6e}".format(
                         labels[b], ratio, imap.label(int(ref["argmax"][b])), float(ref["maxabs"][b]),
                         imap.label(int(new["argmax"][b])), float(new["maxabs"][b]), float(ref["l2"][b]),
                         float(new["l2"][b])))
    return Check(False, lines)


def sketch_thresholds(tol, labels, rows, imap, c=C, seed=SEED, k=K):
    """(delta, cell) of the sketch comparator (PRD section 7.11 (d)): delta[b] = c * sqrt(fsum(tol^2 over block b)),
    the smallest single-entry change block b's sketch detects, whichever entry changes (it moves every projection by
    +-the change); cell {(ix, iy): (m, b)}, the smallest multiple m of each entry's own tol that a change of every
    entry at (ix, iy) needs to fail some block, and the block b that fails first (owner, 2026-10-22, AIUE-92 D5)."""
    tol = np.asarray(tol, dtype=np.float64)
    if tol.shape != (imap.neq,) or not (np.isfinite(tol).all() and (tol > 0).all()):
        raise ValueError("tol must have shape ({},) and be finite and > 0 at every entry".format(imap.neq))
    delta = np.array([c * math.sqrt(fsum(tol[r] ** 2)) for r in rows])
    cell = {}
    for b, (label, r) in enumerate(zip(labels, rows)):
        r = np.asarray(r)
        s = signs(seed, label, len(r), k).astype(np.float64)
        keys = list(zip(imap.ix[r].tolist(), imap.iy[r].tolist()))
        uniq = sorted(set(keys))
        pos = {key: n for n, key in enumerate(uniq)}
        where = np.array([pos[key] for key in keys])
        moved = np.zeros((len(uniq), k))  # per cell, sum_e r_j,e tol_e over its entries in this block
        np.add.at(moved, where, (s * tol[r]).T)
        m = delta[b] / np.abs(moved).max(axis=1)
        for key, mb in zip(uniq, m.tolist()):
            if key not in cell or mb < cell[key][0]:
                cell[key] = (mb, b)
    return delta, cell


THRESHOLD_KEYS = ("block", "cell_ix", "cell_iy", "cell_m", "cell_block")


def threshold_arrays(delta, cell):
    """The stored form of sketch_thresholds: {block, cell_ix, cell_iy, cell_m, cell_block}, cells in (ix, iy) order."""
    keys = sorted(cell)
    return {"block": np.asarray(delta, dtype=np.float64),
            "cell_ix": np.array([ix for ix, _ in keys], dtype=np.int32),
            "cell_iy": np.array([iy for _, iy in keys], dtype=np.int32),
            "cell_m": np.array([cell[key][0] for key in keys], dtype=np.float64),
            "cell_block": np.array([cell[key][1] for key in keys], dtype=np.int32)}


# ---------------------------------------------------------------- writing


def _ds(group, name, data):
    group.create_dataset(name, data=data, track_times=False)


def _config(config):
    if config not in mf.CONFIG_NAMES:
        raise ValueError("config {!r}, need one of {}".format(config, mf.CONFIG_NAMES))


class Writer:
    """Writes one family's reference file. Use create()."""

    def __init__(self, path, kind, family, data, imap, k=K, seed=SEED):
        import h5py

        if kind not in mf.STORES:
            raise ValueError("kind {!r}, need one of {}".format(kind, mf.STORES))
        if imap.neq >= 2 ** 31:
            raise ValueError("neq = {} does not fit int32 indices".format(imap.neq))
        self.path, self.kind, self.imap, self.k, self.seed = Path(path), kind, imap, k, seed
        self.labels, self.rows, ids = blocks(imap)
        self.defaults = {}
        self.f = h5py.File(self.path, "w", libver=LIBVER)
        self.f.attrs["schema"], self.f.attrs["family"], self.f.attrs["store"] = SCHEMA, family, kind
        if kind == "sketch":
            self.f.attrs["k"], self.f.attrs["seed"] = k, seed
        g = self.f.create_group("index")
        for name in INDEX_ARRAYS:
            _ds(g, name, np.asarray(data[name]))
        gm = g.create_group("masks")
        for name in MASK_ARRAYS:
            _ds(gm, name, np.asarray(data["masks"][name]))
        gg = g.create_group("grid")
        for name, v in data["grid"].items():
            _ds(gg, name, np.bytes_(v.encode()) if isinstance(v, str) else np.asarray(v))
        _ds(g, "block", ids)
        _ds(g, "block_labels", np.array([s.encode() for s in self.labels]))

    def write_default(self, config, yldot, yldot_J, sigma, diagnostics=None):
        _config(config)
        if config in self.defaults:
            raise StoreError("{}: default already written".format(config))
        n = self.imap.neq
        yldot, yldot_J = _f64("yldot", yldot, n), _f64("yldot_J", yldot_J, n)
        sigma = _f64("sigma", sigma, n)
        if (sigma < 0).any():
            raise ValueError("sigma is negative at rows {}".format(listed(np.flatnonzero(sigma < 0) + 1)))
        g = self.f.create_group("{}/default".format(config))
        _ds(g, "yldot", yldot)
        _ds(g, "sigma", sigma)
        i, v = jflag_sparse(yldot, yldot_J)
        gj = g.create_group("jflag")
        _ds(gj, "index", i)
        _ds(gj, "value", v)
        gd = g.create_group("diagnostics")
        for name in sorted(diagnostics or {}):
            if self.kind == "full" or name.startswith("res"):
                _ds(gd, name, np.asarray(diagnostics[name], dtype=np.float64))
        self.defaults[config] = yldot

    def write_sketch_thresholds(self, config, tol):
        """A sketch store's single-entry and single-cell thresholds of the default (sketch_thresholds), from tol, the
        default's per-entry tolerance (compare.tolerances with its sigma and tolerances.toml)."""
        if self.kind != "sketch":
            raise StoreError("sketch thresholds belong to a sketch store, not a {} store".format(self.kind))
        if config not in self.defaults:
            raise StoreError("{}: write the default before its sketch thresholds".format(config))
        if "{}/default/sketch_threshold".format(config) in self.f:
            raise StoreError("{}: sketch thresholds already written".format(config))
        delta, cell = sketch_thresholds(tol, self.labels, self.rows, self.imap, seed=self.seed, k=self.k)
        g = self.f.create_group("{}/default/sketch_threshold".format(config))
        for name, a in threshold_arrays(delta, cell).items():
            _ds(g, name, a)

    def write_locality(self, config, delta, entries):
        """The locality entries the reference keeps (locality.pattern: score > 1) of a run at delta."""
        from .locality import FIELDS, Entries

        if config != "steady":
            raise ValueError("locality is stored for the steady configuration only, not {!r}".format(config))
        if config not in self.defaults:
            raise StoreError("{}: write the default before its locality pattern".format(config))
        if "{}/locality".format(config) in self.f:
            raise StoreError("{}: locality already written".format(config))
        delta = float(delta)
        if not (math.isfinite(delta) and delta > 0):
            raise ValueError("delta = {}, need a finite delta > 0".format(delta))
        e = entries if isinstance(entries, Entries) else Entries.of(entries)
        n = self.imap.neq
        bad = (e.column < 0) | (e.column >= n) | (e.row < 0) | (e.row >= n)
        if bad.any():
            raise ValueError("locality entries outside 0..{}: {}".format(n - 1, listed(np.flatnonzero(bad) + 1)))
        if not (np.isfinite(e.mismatch).all() and np.isfinite(e.dfull).all()):
            raise ValueError("locality entries must be finite")
        order = np.lexsort((e.row, e.column))
        g = self.f.create_group("{}/locality".format(config))
        _ds(g, "delta", np.float64(delta))
        for name in FIELDS:
            _ds(g, name, getattr(e, name)[order])

    def write_variant(self, config, vid, yldot, yldot_J):
        _config(config)
        if config not in self.defaults:
            raise StoreError("{}: write the default before its variants".format(config))
        if "/" in vid or not vid:
            raise ValueError("variant id {!r}: non-empty, without '/'".format(vid))
        n = self.imap.neq
        yldot, yldot_J = _f64("yldot", yldot, n), _f64("yldot_J", yldot_J, n)
        g = self.f.create_group("{}/variants/{}".format(config, vid))
        if self.kind == "full":
            for name, (i, v) in (("yldot", sparse_diff(yldot, self.defaults[config])),
                                 ("jflag", jflag_sparse(yldot, yldot_J))):
                gs = g.create_group(name)
                _ds(gs, "index", i)
                _ds(gs, "value", v)
        else:
            for name, x in (("yldot", yldot), ("jflag", yldot_J - yldot)):
                gs = g.create_group(name)
                for key, a in sketch(x, self.labels, self.rows, self.seed, self.k).items():
                    _ds(gs, key, a)

    def copy_variant(self, config, vid, src):
        """Copy a stored variant of the Store src verbatim (each dataset read through src.read, so SHA-checked):
        make_references.py --only keeps the variants it does not regenerate bit for bit, which write_variant cannot
        (the flag difference yldot_J - yldot does not round-trip through yldot_J)."""
        _config(config)
        if config not in self.defaults:
            raise StoreError("{}: write the default before its variants".format(config))
        if src.kind != self.kind:
            raise StoreError("copy from a {} store into a {} store".format(src.kind, self.kind))
        if vid not in src.variants(config):
            raise StoreError("{}: no stored variant {} in {}".format(src.path, vid, config))
        prefix = "{}/variants/{}".format(config, vid)
        if prefix in self.f:
            raise StoreError("{}: variant {} already written".format(config, vid))
        g = self.f.create_group(prefix)
        keys = ("index", "value") if self.kind == "full" else ("proj", "l2", "maxabs", "argmax")
        for name in ("yldot", "jflag"):  # write_variant's order, so the bytes match a fresh write
            gs = g.create_group(name)
            for key in keys:
                _ds(gs, key, src.read("/{}/{}/{}".format(prefix, name, key)))

    def finish(self):
        """Close the file; return {datasets: {path: sha}, sha256, bytes} for the manifest."""
        import h5py

        self.f.close()
        with h5py.File(self.path, "r") as f:
            shas = {name: dataset_sha256(a) for name, a in _datasets(f).items()}
        return {"datasets": shas, "sha256": file_sha256(self.path), "bytes": self.path.stat().st_size}


def create(path, kind, family, data, imap, k=K, seed=SEED):
    """A Writer for a new reference file (kind "full" or "sketch"). imap must carry regions."""
    return Writer(path, kind, family, data, imap, k, seed)


def _datasets(f):
    out = {}

    def visit(name, obj):
        if hasattr(obj, "shape"):
            out["/" + name] = obj[()]

    f.visititems(visit)
    return out


# ---------------------------------------------------------------- reading


class Store:
    """A reference file opened against its manifest (open_store)."""
    kind = None

    def __init__(self, path, manifest, h5, regions):
        self.path, self.manifest, self.f = Path(path), manifest, h5
        self.family = manifest["family"]
        self._cache = {}
        self.imap = index_map(self.index_data(), regions)
        self.labels, self.rows, ids = blocks(self.imap)
        stored = [s.decode() for s in self.read("/index/block_labels")]
        if stored != self.labels or not np.array_equal(self.read("/index/block"), ids):
            raise StoreError("{}: the blocks rebuilt from the stored index arrays and the family's regions differ "
                             "from the stored blocks (regions or index layout changed: regenerate)".format(self.path))
        unknown = sorted("{}.{}: {}".format(vid, key, label) for vid, v in manifest.get("variables", {}).items()
                         for key in ("block_l2", "jflag_block_l2") for label in v[key] if label not in self.labels)
        if unknown:
            raise StoreIntegrityError("{}: block labels of the manifest's variables are not blocks of the store: "
                                      "{}".format(self.path, listed(unknown)))

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def read(self, name):
        """A dataset, its SHA-256 recomputed against the manifest."""
        if name in self._cache:
            return self._cache[name]
        want = self.manifest["datasets"].get(name)
        if want is None or name not in self.f:
            raise StoreIntegrityError("{}: dataset {} not in both the file and the manifest".format(self.path, name))
        a = self.f[name][()]
        got = dataset_sha256(a)
        if got != want:
            raise StoreIntegrityError("{}: dataset {} has SHA-256 {}, the manifest {}".format(self.path, name, got,
                                                                                            want))
        if isinstance(a, np.ndarray):
            a.flags.writeable = False  # the cached, verified copy: callers copy before changing it
        self._cache[name] = a
        return a

    def index_data(self):
        """The index arrays, masks and grid of the generating run, shaped as state.index_data returns them."""
        out = {name: self.read("/index/" + name) for name in INDEX_ARRAYS}
        out["masks"] = {name: self.read("/index/masks/" + name) for name in MASK_ARRAYS}
        grid = {}
        for name in self.f["index/grid"]:
            v = self.read("/index/grid/" + name)
            grid[name] = v.decode() if isinstance(v, bytes) else v
        out["grid"] = grid
        out["neq"] = int(self.f["index/block"].shape[0])
        return out

    def default(self, config):
        return self.read("/{}/default/yldot".format(config))

    def sigma(self, config):
        return self.read("/{}/default/sigma".format(config))

    def _sparse(self, prefix):
        return self.read(prefix + "/index"), self.read(prefix + "/value")

    def jflag(self, config):
        """The default's dense Jacobian-flag difference yldot_J - yldot."""
        return dense(*self._sparse("/{}/default/jflag".format(config)), self.imap.neq)

    def locality(self, config):
        """(delta, locality.Entries) of the stored locality pattern, or None if the reference stores none."""
        from .locality import FIELDS, Entries

        g = "/{}/locality".format(config)
        if g[1:] not in self.f:
            return None
        return float(self.read(g + "/delta")), Entries.of({k: self.read("{}/{}".format(g, k)) for k in FIELDS})

    def diagnostics(self, config):
        g = "{}/default/diagnostics".format(config)
        return {name: self.read("/{}/{}".format(g, name)) for name in self.f[g]}

    def variants(self, config):
        g = "{}/variants".format(config)
        return sorted(self.f[g]) if g in self.f else []

    def _same_index(self, imap):
        same = (imap.neq == self.imap.neq and all(np.array_equal(getattr(imap, a), getattr(self.imap, a))
                                                  for a in ("eq", "species", "ix", "iy", "region")))
        if not same:
            raise StoreError("{}: the new run's index map differs from the stored one".format(self.path))

    def _full_check(self, new, ref, tol, imap, what, diag=None):
        c = compare(new, ref, tol, imap)
        lines = (c.report(*diag, rtol_diag=DIAG_SCALED_RTOL, scaled=True) if diag else c.report()).splitlines()
        return Check(c.ok, ["{} {}".format(what, lines[0])] + lines[1:])

    def check(self, config, vid, yldot, yldot_J, tol, imap, diagnostics=None):
        """Compare a new run with the default (vid None) or a stored variant: yldot and the Jacobian-flag difference,
        both under the per-entry tolerance tol of the default (decision 27). diagnostics: the new run's, to name the
        first differing intermediate of a failing default."""
        self._same_index(imap)
        n = imap.neq
        yldot, yldot_J = _f64("yldot", yldot, n, False), _f64("yldot_J", yldot_J, n, False)
        if vid is None:
            diag = (self.diagnostics(config), diagnostics) if diagnostics is not None else None
            parts = [self._full_check(yldot, self.default(config), tol, imap, "yldot", diag),
                     self._full_check(yldot_J - yldot, self.jflag(config), tol, imap, "flag difference")]
        else:
            if vid not in self.variants(config):
                raise StoreError("{}: no stored variant {} in {}".format(self.path, vid, config))
            parts = self._check_variant(config, vid, yldot, yldot_J, tol, imap)
        return Check(all(p.ok for p in parts), [line for p in parts for line in p.lines])


class FullVectorStore(Store):
    kind = "full"

    def variant(self, config, vid):
        """The variant's dense yldot and Jacobian-flag difference."""
        p = "/{}/variants/{}".format(config, vid)
        return (dense(*self._sparse(p + "/yldot"), self.imap.neq, base=self.default(config)),
                dense(*self._sparse(p + "/jflag"), self.imap.neq))

    def _check_variant(self, config, vid, yldot, yldot_J, tol, imap):
        ref, ref_j = self.variant(config, vid)
        return [self._full_check(yldot, ref, tol, imap, "yldot"),
                self._full_check(yldot_J - yldot, ref_j, tol, imap, "flag difference")]


class SketchStore(Store):
    kind = "sketch"

    @property
    def k(self):
        return int(self.f.attrs["k"])

    @property
    def seed(self):
        return int(self.f.attrs["seed"])

    def variant(self, config, vid):
        """The variant's stored sketches of yldot and of the Jacobian-flag difference."""
        p = "/{}/variants/{}".format(config, vid)
        return tuple({key: self.read("{}/{}/{}".format(p, what, key)) for key in ("proj", "l2", "maxabs", "argmax")}
                     for what in ("yldot", "jflag"))

    def sketch_thresholds(self, config):
        """The stored (delta, cell) of the default (sketch_thresholds' form), or None if the file stores none."""
        g = "/{}/default/sketch_threshold".format(config)
        if g[1:] not in self.f:
            return None
        a = {key: self.read("{}/{}".format(g, key)) for key in THRESHOLD_KEYS}
        cell = {(int(ix), int(iy)): (float(m), int(b))
                for ix, iy, m, b in zip(a["cell_ix"], a["cell_iy"], a["cell_m"], a["cell_block"])}
        return np.array(a["block"]), cell

    def _check_variant(self, config, vid, yldot, yldot_J, tol, imap):
        ref, ref_j = self.variant(config, vid)
        new = sketch(yldot, self.labels, self.rows, self.seed, self.k)
        new_j = sketch(yldot_J - yldot, self.labels, self.rows, self.seed, self.k)
        return [sketch_compare(ref, new, tol, self.labels, self.rows, imap, what="yldot"),
                sketch_compare(ref_j, new_j, tol, self.labels, self.rows, imap, what="flag difference")]


STORED_VARIANT = re.compile(r"^/([^/]+)/variants/([^/]+)/")


def check_derived(m, path):
    """The manifest fields derived from m["datasets"] agree with them: guarded (with the locality pattern) and
    unguarded, each SENSITIVE variant's sha256, and the stored variants against the SENSITIVE variables."""
    problems = []
    guarded, unguarded = mf.summarize(m["datasets"])
    for what, got, want in (("guarded", m["guarded"], guarded), ("unguarded", m["unguarded"], unguarded)):
        bad = sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))
        if bad:
            problems.append("{} {} differ from the datasets".format(what, bad))
    stored = set()
    for name in m["datasets"]:
        hit = STORED_VARIANT.match(name)
        if hit:
            stored.add(hit.groups())
    sensitive = {(v["config"], vid) for vid, v in m["variables"].items() if v["class"] == "SENSITIVE"}
    if stored != sensitive:
        problems.append("stored variants not SENSITIVE variables {}, SENSITIVE variables not stored {}".format(
            sorted(stored - sensitive), sorted(sensitive - stored)))
    bad = sorted(vid for vid, v in m["variables"].items()
                 if v["class"] == "SENSITIVE" and mf.variant_sha(m["datasets"], v["config"], vid) != v["sha256"])
    if bad:
        problems.append("sha256 of the variables {} differs from their datasets".format(bad))
    if problems:
        raise StoreIntegrityError("{}: the manifest disagrees with its datasets: {}".format(path, "; ".join(problems)))


def open_store(family, suite=mf.SUITE, regions=None):
    """The family's reference file, checked against references/<family>.manifest.json: the file's SHA-256, its
    datasets, root attributes and blocks, and the manifest's derived fields. regions: the [regions] spec (default:
    the family's family.toml)."""
    import h5py

    m = mf.load(family, suite)
    rel = mf.reference_path(family)
    if rel not in m["external"] or "datasets" not in m:
        raise StoreError("{}: the manifest names no reference file".format(mf.path(family, suite)))
    p = Path(suite) / rel
    if not p.is_file():
        raise StoreError("{} is missing or a dangling link: run {} {}".format(p, FETCH, family))
    sha = file_sha256(p)
    if sha != m["external"][rel]["sha256"]:
        raise StoreIntegrityError("{} has SHA-256 {}, the manifest {}".format(p, sha, m["external"][rel]["sha256"]))
    f = h5py.File(p, "r")
    try:
        names = set()
        f.visititems(lambda name, obj: names.add("/" + name) if hasattr(obj, "shape") else None)
        extra, missing = sorted(names - set(m["datasets"])), sorted(set(m["datasets"]) - names)
        if extra or missing:
            raise StoreIntegrityError("{}: datasets not in the manifest {}, in the manifest but not the file {}".format(
                p, listed(extra), listed(missing)))
        attrs = {key: f.attrs.get(key) for key in ("schema", "family", "store")}
        if attrs != {"schema": SCHEMA, "family": family, "store": m["store"]}:
            raise StoreIntegrityError("{}: root attributes {} do not match the manifest".format(p, attrs))
        if m["store"] == "sketch" and {"k": int(f.attrs["k"]), "seed": int(f.attrs["seed"])} != m["sketch"]:
            raise StoreIntegrityError("{}: k/seed differ from the manifest's sketch {}".format(p, m["sketch"]))
        check_derived(m, p)
        if regions is None:
            regions = load_regions(Path(suite) / "families" / family)
        cls = FullVectorStore if m["store"] == "full" else SketchStore
        return cls(p, m, f, regions)
    except BaseException:
        f.close()
        raise
