"""The locality check of the yldot suite (epic AIUE-9, PRD section 7.5; AIUE-100): how the local evaluation
pandf(xc, yc, ...) that jac_calc builds the Jacobian from differs from the full evaluation, column by column.

Child side (state.py step 8c calls it after the evaluation of every non-intake config, uedge loaded):
    run(bbb, neq, delta, columns=None)
        -> {"delta", "del", "dylconst", "f00", "stale", "entries": {column, row, mismatch, dfull}, "columns"}
    columns: the 0-based columns to perturb (select_columns), None for every column (returned as given).

The protocol follows jac_calc (bbb/oderhs.m:1095-1226) with the Jacobian flag yl(neq+1) = 1 (Python yl[neq]) for every
call, as psetnk sets it (bbb/oderhs.m:1939-1952):
    f00 = the full evaluation at y0
    per column iv: reset the whole work vector to f00 (jac_calc resets its band, :1141-1143); perturb yl[iv] by
    dyl = delta*(|y0| + dylconst/suscal[iv]) (jac_calc's formula with del -> delta, :1156); the local evaluation
    pandf(igyl[iv,0], igyl[iv,1]) into the work vector (:1160); the full evaluation at the perturbed yl; restore yl[iv]
    and evaluate locally again (:1215-1216); the full evaluation at y0, which must reproduce f00 bit for bit (else the
    column is stale: an intermediate carried over).
    Each column costs 2 local + 2 full evaluations. The entries are the rows where d = Delta_full - Delta_local is
    non-zero, Delta = (evaluation - f00); rows and columns are 0-based (labels add 1, as compare does).

Parent side: scores, pattern and compare_pattern. The score of an entry is |d| / (tol_r + rtol_eq*|Delta_full,r|),
tol_r the row's per-entry tolerance of the stored default (compare.tolerances, PRD 7.4). A reference stores the
entries with score > 1; its pattern P is those with score > M_loc. At test time (owner, 2026-10-22, AIUE-100 D3):
    a P entry must still score > 1 and match its stored d: |d_new - d_ref| <= tol_r + rtol_eq*|Delta_full,new|;
    an entry outside P must score <= M_loc;
    entries in the band (1, M_loc] are recorded but not asserted.

Columns and variants (PRD 7.5 "Columns and tiers"; AIUE-101, owner 2026-10-25): [locality].columns = "all" perturbs
every column; "special" the columns of the special cells (special_columns) plus `sample` seeded interior columns for the
default (variants: the special cells only). [locality].variants picks the variants with a stored pattern
(variant_scope); each is stored as its difference from the default pattern (diff, apply).
uedge is never imported here.
"""
import math
from dataclasses import dataclass, field

import numpy as np

FIELDS = ("column", "row", "mismatch", "dfull")
DTYPES = {"column": np.int64, "row": np.int64, "mismatch": np.float64, "dfull": np.float64}
KEYS = ("delta_loc", "m_loc", "calibration", "causes", "columns", "variants")  # family.toml [locality]
SAMPLE_KEYS = ("sample", "seed")  # with columns = "special" only
OPTIONAL = ("excluded",)  # {variant id: reason}: owner-decided exclusions from the variant scope (decision 23)
COLUMNS = ("all", "special")
VARIANTS = ("all", "listed", "meth")
# the inputs that move the local evaluation's window (owner, 2026-10-25, AIUE-101 Q3)
WINDOW_INPUTS = ("xlinc", "xrinc", "yinc", "isjaccorall", "isturbnloc", "isturbcons", "diffuslimit")
VALID = ("SENSITIVE", "INERT", "MARGINAL")  # the classes with a usable stored result (manifest.CLASSES)


def load_config(fdir):
    """The family's [locality] table (family.toml; guarded, check_reference_change.py), or None without one."""
    import tomllib
    from pathlib import Path

    with open(Path(fdir) / "family.toml", "rb") as f:
        t = tomllib.load(f).get("locality")
    if t is None:
        return None
    want = KEYS + (SAMPLE_KEYS if t.get("columns") == "special" else ())
    bad = sorted((set(t) - set(OPTIONAL)) ^ set(want))
    if bad:
        raise ValueError("{}: [locality] needs exactly the keys {}, differs in {}".format(fdir, list(want), bad))
    if t["columns"] not in COLUMNS:
        raise ValueError("{}: [locality].columns = {!r}, need one of {}".format(fdir, t["columns"], COLUMNS))
    if t["variants"] not in VARIANTS:
        raise ValueError("{}: [locality].variants = {!r}, need one of {}".format(fdir, t["variants"], VARIANTS))
    for key in SAMPLE_KEYS if t["columns"] == "special" else ():
        v = t[key]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("{}: [locality].{} = {!r}, need an integer >= 0".format(fdir, key, v))
    for key in ("delta_loc", "m_loc"):
        v = t[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError("{}: [locality].{} = {!r}, need a finite number > 0".format(fdir, key, v))
    if t["m_loc"] <= 1:
        raise ValueError("{}: [locality].m_loc = {}, need > 1".format(fdir, t["m_loc"]))
    if not isinstance(t["causes"], dict):
        raise ValueError("{}: [locality].causes must be a table".format(fdir))
    ex = t.get("excluded", {})
    if not (isinstance(ex, dict) and all(isinstance(v, str) and v.strip() for v in ex.values())):
        raise ValueError("{}: [locality].excluded must map variant ids to a reason".format(fdir))
    return t


# ---------------------------------------------------------------- columns and variants


def special_columns(data):
    """The sorted 0-based columns of the special cells (owner, 2026-10-25, AIUE-101 Q1), every variable of each cell.

    data: index data as state.index_data or Store.index_data return it (igyl and the grid read live from com), with
    jx < nxpt:
        plates      ix in {ixlb(jx), ixlb(jx)+1, ixrb(jx), ixrb(jx)+1}
        radial      iy in {0, 1, ny, ny+1}
        separatrix  iy in {s, s+1} for every distinct s of iysptrx1(jx), iysptrx2(jx)
        cuts        ix in {ixptK(jx), ixptK(jx)+1} for iy <= iysptrxK(jx), K = 1, 2
    iysptrxK(jx) pairs with ixptK(jx) (the gridue header, doc/pdf/Snowflake_mapping_rpt_Rensink_Rognlien.pdf; the
    xccuts test, bbb/pandf.m:113-119). The X-point cells and the corners fall inside."""
    g = data["grid"]
    neq = int(data["neq"])
    igyl = np.asarray(data["igyl"])[:neq]
    ix, iy = igyl[:, 0], igyl[:, 1]
    nxpt, ny = int(g["nxpt"]), int(g["ny"])
    arr = lambda name: np.atleast_1d(np.asarray(g[name], dtype=np.int64))[:nxpt]  # noqa: E731
    lb, rb, sp1, sp2 = arr("ixlb"), arr("ixrb"), arr("iysptrx1"), arr("iysptrx2")
    plates = np.concatenate([lb, lb + 1, rb, rb + 1])
    seps = np.unique(np.concatenate([sp1, sp2]))
    mask = np.isin(ix, plates) | np.isin(iy, [0, 1, ny, ny + 1]) | np.isin(iy, np.concatenate([seps, seps + 1]))
    for xpt, sep in ((arr("ixpt1"), sp1), (arr("ixpt2"), sp2)):
        for a, s in zip(xpt, sep):
            mask |= np.isin(ix, [a, a + 1]) & (iy <= s)
    return np.flatnonzero(mask).astype(np.int64)


def select_columns(cfg, data, sample=True):
    """The columns a run perturbs: None for columns = "all"; else the special cells' columns and, with sample, the
    [locality].sample interior columns of smallest key, the keys PCG64(seed).random_raw(neq) (one per column, stable
    across numpy versions as store.signs)."""
    if cfg["columns"] == "all":
        return None
    special = special_columns(data)
    n = int(cfg["sample"]) if sample else 0
    if n == 0:
        return special
    neq = int(data["neq"])
    keys = np.asarray(np.random.PCG64(int(cfg["seed"])).random_raw(neq), dtype=np.uint64)
    interior = np.setdiff1d(np.arange(neq, dtype=np.int64), special)
    if n > interior.size:
        raise ValueError("[locality].sample = {} exceeds the {} interior columns".format(n, interior.size))
    picked = interior[np.argsort(keys[interior], kind="stable")[:n]]
    return np.union1d(special, picked).astype(np.int64)


def variant_scope(cfg, variables):
    """The sorted variant ids with a stored locality pattern (owner, 2026-10-25, AIUE-101 Q2-Q3), from the manifest's
    variables ({id: {"class", ...}}): "all" every SENSITIVE, INERT and MARGINAL variant; "listed" the bbb.meth* variants
    and the WINDOW_INPUTS, "meth" the bbb.meth* variants, both of those classes only. The ids in [locality].excluded
    (owner decisions with their reasons) are left out."""
    excluded = cfg.get("excluded", {})
    def name(vid):
        return vid.split("=", 1)[0]

    def listed(vid):
        n = name(vid)
        return n.startswith("bbb.meth") or (cfg["variants"] == "listed" and n in ["bbb." + w for w in WINDOW_INPUTS])

    return sorted(vid for vid, v in variables.items()
                  if v["class"] in VALID and vid not in excluded and (cfg["variants"] == "all" or listed(vid)))


# ---------------------------------------------------------------- child side


def run(bbb, neq, delta, columns=None):
    """The PRD 7.5 protocol over the given columns (every column for None), in the child after an evaluation."""
    delta = float(delta)
    if not (math.isfinite(delta) and delta > 0):
        raise ValueError("delta = {}, need a finite delta > 0".format(delta))
    if columns is None:
        columns = range(neq)
    else:
        columns = np.asarray(columns, dtype=np.int64)
        if columns.ndim != 1 or (columns.size and (columns.min() < 0 or columns.max() >= neq)) or \
                (np.diff(columns) <= 0).any():
            raise ValueError("columns must be increasing 0-based columns below neq = {}".format(neq))
        columns = columns.tolist()
    yl = bbb.yl
    yl[neq] = 1.0
    yl[neq + 1] = 0.0
    f00 = np.zeros_like(np.asarray(bbb.yldot))
    bbb.pandf(-1, -1, neq, 0.0, yl, f00)
    wk, ff, scratch = f00.copy(), f00.copy(), f00.copy()
    igyl = np.array(bbb.igyl).copy()
    suscal = np.array(bbb.suscal).copy()
    dylconst = float(bbb.dylconst)
    base = f00[:neq]
    cols, rows, mism, dfull, stale = [], [], [], [], []
    for iv in columns:
        xc, yc = int(igyl[iv, 0]), int(igyl[iv, 1])
        wk[:] = f00
        y0 = float(yl[iv])
        yl[iv] = y0 + delta * (abs(y0) + dylconst / suscal[iv])
        bbb.pandf(xc, yc, neq, 0.0, yl, wk)
        bbb.pandf(-1, -1, neq, 0.0, yl, ff)
        yl[iv] = y0
        bbb.pandf(xc, yc, neq, 0.0, yl, scratch)
        bbb.pandf(-1, -1, neq, 0.0, yl, scratch)
        if not np.array_equal(scratch[:neq], base):
            stale.append(iv)
        df = ff[:neq] - base
        d = df - (wk[:neq] - base)
        nz = np.flatnonzero(d)
        cols.append(np.full(nz.size, iv, dtype=np.int64))
        rows.append(nz.astype(np.int64))
        mism.append(d[nz])
        dfull.append(df[nz])
    yl[neq] = -1.0
    cat = lambda parts, dt: np.concatenate(parts).astype(dt) if parts else np.zeros(0, dt)  # noqa: E731
    entries = {"column": cat(cols, np.int64), "row": cat(rows, np.int64), "mismatch": cat(mism, np.float64),
               "dfull": cat(dfull, np.float64)}
    return {"delta": delta, "del": float(getattr(bbb, "del")), "dylconst": dylconst, "f00": base.copy(),
            "stale": np.asarray(stale, dtype=np.int64), "entries": entries,
            "columns": None if isinstance(columns, range) else np.asarray(columns, dtype=np.int64)}


# ---------------------------------------------------------------- parent side


@dataclass
class Entries:
    """Sparse (column, row) entries of a locality run or a stored pattern, 0-based."""
    column: np.ndarray
    row: np.ndarray
    mismatch: np.ndarray
    dfull: np.ndarray

    @classmethod
    def of(cls, d):
        e = cls(*(np.asarray(d[k], dtype=DTYPES[k]) for k in FIELDS))
        n = e.column.size
        if any(getattr(e, k).shape != (n,) for k in FIELDS):
            raise ValueError("locality entries of unequal lengths: {}".format({k: getattr(e, k).shape for k in FIELDS}))
        keys = set(zip(e.column.tolist(), e.row.tolist()))
        if len(keys) != n:
            raise ValueError("locality entries repeat a (column, row) key: {} of {} are unique".format(len(keys), n))
        return e

    def to_dict(self):
        return {k: getattr(self, k) for k in FIELDS}

    def select(self, mask):
        return Entries(*(getattr(self, k)[mask] for k in FIELDS))

    def __len__(self):
        return int(self.column.size)

    def sorted(self):
        """The entries ordered by (column, row), as run writes them."""
        return self.select(np.lexsort((self.row, self.column)))


def _keys(column, row):
    return [(int(c), int(r)) for c, r in zip(column, row)]


def diff(default, variant):
    """A variant's pattern as its difference from the default pattern (both Entries): (added, dropped). added holds
    the variant's entries that are new or differ bitwise from the default's in mismatch or dfull; dropped
    {"column", "row"} the default's keys the variant lacks. apply(default, added, dropped) restores the variant."""
    ref = {k: (m.tobytes(), f.tobytes()) for k, m, f in zip(_keys(default.column, default.row), default.mismatch,
                                                            default.dfull)}
    keys = _keys(variant.column, variant.row)
    new = np.array([ref.get(k) != (m.tobytes(), f.tobytes()) for k, m, f in zip(keys, variant.mismatch,
                                                                                 variant.dfull)], dtype=bool)
    gone = sorted(set(ref) - set(keys))
    dropped = {"column": np.array([c for c, _ in gone], dtype=np.int64),
               "row": np.array([r for _, r in gone], dtype=np.int64)}
    return variant.select(new.reshape(-1)).sorted(), dropped


def apply(default, added, dropped):
    """The variant's Entries from the default pattern and its difference (diff), ordered by (column, row)."""
    out = set(_keys(dropped["column"], dropped["row"])) | set(_keys(added.column, added.row))
    keep = np.array([k not in out for k in _keys(default.column, default.row)], dtype=bool).reshape(-1)
    kept = default.select(keep)
    return Entries.of({k: np.concatenate([getattr(kept, k), getattr(added, k)]) for k in FIELDS}).sorted()


def rtol_rows(rtol, imap):
    """rtol_eq per row (tolerances.toml [rtol])."""
    return np.array([rtol[e] for e in imap.eq], dtype=float)


def scores(e, tol, rteq):
    """|d| / (tol_r + rtol_eq*|Delta_full,r|) per entry."""
    return np.abs(e.mismatch) / (tol[e.row] + rteq[e.row] * np.abs(e.dfull))


def pattern(e, tol, rteq):
    """The entries a reference stores: score > 1."""
    return e.select(scores(e, tol, rteq) > 1.0)


def short(imap, i):
    """'ti[1](2,4)': equation, Fortran species and cell of row i."""
    return "{}[{}]({},{})".format(imap.eq[i], imap.species[i], imap.ix[i], imap.iy[i])


@dataclass
class LocalityComparison:
    ok: bool
    n_fail: int
    new_rows: list  # (column, row, score): outside P, score > M_loc
    lost: list  # (column, row, score): in P, score <= 1 (0 when the entry vanished)
    magnitude: list  # (column, row, ratio): in P, |d_new - d_ref| / (tol_r + rtol_eq*|Delta_full,new|) > 1
    nonfinite: list  # (column, row, inf): a live entry whose mismatch or dfull is NaN or Inf
    fired: dict  # {"eq[sp]": [(ix, iy), ...]}: the blocks of the failing rows
    max_ratio: float  # largest failing ratio: score/M_loc (new), 1/score (lost), the magnitude ratio
    n_pattern: int
    imap: object = field(repr=False)
    family: str = ""

    def headline(self):
        """The worst failing entry's column in the PRD story 6 form (non-finite, new, lost, then magnitude)."""
        if self.ok:
            return "{} locality: pattern of {} entries reproduced".format(self.family, self.n_pattern)
        if self.nonfinite:
            col = self.nonfinite[0][0]
            rows = [r for c, r, _ in self.nonfinite if c == col]
            what = "non-finite mismatch or dfull in rows {}".format(", ".join(short(self.imap, r) for r in rows))
        elif self.new_rows:
            col = self.new_rows[0][0]
            rows = [r for c, r, _ in self.new_rows if c == col]
            what = "new mismatch rows {} not in reference pattern".format(", ".join(short(self.imap, r) for r in rows))
        elif self.lost:
            col = self.lost[0][0]
            rows = [r for c, r, _ in self.lost if c == col]
            what = "reference pattern rows {} no longer mismatch".format(", ".join(short(self.imap, r) for r in rows))
        else:
            col = self.magnitude[0][0]
            rows = [r for c, r, _ in self.magnitude if c == col]
            what = "reference pattern rows {} changed magnitude".format(", ".join(short(self.imap, r) for r in rows))
        return "{} locality: column {}: {}".format(self.family, short(self.imap, col), what)

    def report(self, limit=10):
        lines = [self.headline()]
        if self.ok:
            return lines[0]
        for name, items, unit in (("non-finite live entries (NaN or Inf mismatch or dfull)", self.nonfinite, "score"),
                                  ("new mismatch entries (score > M_loc, not in the pattern)", self.new_rows, "score"),
                                  ("pattern entries lost (score <= 1)", self.lost, "score"),
                                  ("pattern entries changed magnitude", self.magnitude, "ratio")):
            if items:
                lines.append("{}: {}".format(name, len(items)))
                for c, r, s in items[:limit]:
                    lines.append("  column {} -> row {}  {} {:.3e}".format(self.imap.label(c), self.imap.label(r),
                                                                       unit, s))
        lines.append("failing per block: " + ", ".join("{} {}".format(b, len(c)) for b, c in self.fired.items()))
        return "\n".join(lines)


def compare_pattern(ref, new, tol, rteq, m_loc, imap, family=""):
    """The live entries new against the stored ref (both Entries), PRD 7.5 with the band (module docstring)."""
    if not (math.isfinite(m_loc) and m_loc > 1):
        raise ValueError("M_loc = {}, need a finite M_loc > 1".format(m_loc))
    tol, rteq = np.asarray(tol, dtype=float), np.asarray(rteq, dtype=float)
    if not (np.isfinite(ref.mismatch).all() and np.isfinite(ref.dfull).all()):
        raise ValueError("the stored reference pattern has non-finite entries")
    s_ref, s_new = scores(ref, tol, rteq), scores(new, tol, rteq)
    bad = ~(np.isfinite(new.mismatch) & np.isfinite(new.dfull))  # every comparison below is False for NaN
    nonfinite = sorted((int(new.column[i]), int(new.row[i]), math.inf) for i in np.flatnonzero(bad))
    in_p = s_ref > m_loc
    live = {(int(c), int(r)): i for i, (c, r) in enumerate(zip(new.column, new.row))}
    pkeys = {(int(ref.column[i]), int(ref.row[i])) for i in np.flatnonzero(in_p)}
    new_rows, lost, magnitude = [], [], []
    for i in np.flatnonzero((s_new > m_loc) & ~bad):
        key = (int(new.column[i]), int(new.row[i]))
        if key not in pkeys:
            new_rows.append((key[0], key[1], float(s_new[i])))
    for i in np.flatnonzero(in_p):
        key = (int(ref.column[i]), int(ref.row[i]))
        j = live.get(key)
        if j is not None and bad[j]:
            continue  # counted in nonfinite
        s = float(s_new[j]) if j is not None else 0.0
        if s <= 1.0:
            lost.append((key[0], key[1], s))
            continue
        r = key[1]
        ratio = abs(new.mismatch[j] - ref.mismatch[i]) / (tol[r] + rteq[r] * abs(new.dfull[j]))
        if ratio > 1.0:
            magnitude.append((key[0], key[1], float(ratio)))
    order = lambda items: sorted(items, key=lambda t: (-t[2], t[0], t[1]))  # noqa: E731
    new_rows, magnitude = order(new_rows), order(magnitude)
    lost = sorted(lost, key=lambda t: (t[2], t[0], t[1]))
    fired = {}
    for c, r, _ in nonfinite + new_rows + lost + magnitude:
        fired.setdefault("{}[{}]".format(imap.eq[r], imap.species[r]), []).append((int(imap.ix[r]), int(imap.iy[r])))
    ratios = [math.inf] * len(nonfinite) + [s / m_loc for _, _, s in new_rows] + [math.inf if s == 0 else 1.0 / s for _, _, s in lost] + \
        [s for _, _, s in magnitude]
    n_fail = len(nonfinite) + len(new_rows) + len(lost) + len(magnitude)
    return LocalityComparison(n_fail == 0, n_fail, new_rows, lost, magnitude, nonfinite, fired, max(ratios, default=0.0),
                              int(in_p.sum()), imap, family)
