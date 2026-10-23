"""The locality check of the yldot suite (epic AIUE-9, PRD section 7.5; AIUE-100): how the local evaluation
pandf(xc, yc, ...) that jac_calc builds the Jacobian from differs from the full evaluation, column by column.

Child side (state.py step 8c calls it after the default evaluation, uedge loaded):
    run(bbb, neq, delta)  -> {"delta", "del", "dylconst", "f00", "stale", "entries": {column, row, mismatch, dfull}}

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
uedge is never imported here.
"""
import math
from dataclasses import dataclass, field

import numpy as np

FIELDS = ("column", "row", "mismatch", "dfull")
DTYPES = {"column": np.int64, "row": np.int64, "mismatch": np.float64, "dfull": np.float64}
KEYS = ("delta_loc", "m_loc", "calibration", "causes")  # family.toml [locality]


def load_config(fdir):
    """The family's [locality] table (family.toml; guarded, check_reference_change.py), or None without one."""
    import tomllib
    from pathlib import Path

    with open(Path(fdir) / "family.toml", "rb") as f:
        t = tomllib.load(f).get("locality")
    if t is None:
        return None
    bad = sorted(set(t) ^ set(KEYS))
    if bad:
        raise ValueError("{}: [locality] needs exactly the keys {}, differs in {}".format(fdir, list(KEYS), bad))
    for key in ("delta_loc", "m_loc"):
        v = t[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError("{}: [locality].{} = {!r}, need a finite number > 0".format(fdir, key, v))
    if t["m_loc"] <= 1:
        raise ValueError("{}: [locality].m_loc = {}, need > 1".format(fdir, t["m_loc"]))
    if not isinstance(t["causes"], dict):
        raise ValueError("{}: [locality].causes must be a table".format(fdir))
    return t


# ---------------------------------------------------------------- child side


def run(bbb, neq, delta):
    """The PRD 7.5 protocol over every column, in the child after the default evaluation."""
    delta = float(delta)
    if not (math.isfinite(delta) and delta > 0):
        raise ValueError("delta = {}, need a finite delta > 0".format(delta))
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
    for iv in range(neq):
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
            "stale": np.asarray(stale, dtype=np.int64), "entries": entries}


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
