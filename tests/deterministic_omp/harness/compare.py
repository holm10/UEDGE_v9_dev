"""Bitwise comparison of two run records, with localisation of every mismatch.

"Bitwise" means equal IEEE-754 bit patterns: +0.0 and -0.0 differ, and any NaN or Inf in
either operand is a failure even if both sides hold the same bits. The one exception is the
RHS-arm yldot, where REDUCTION(+) in OMPPandf1Rhs (ppp/omp_parallel.F90) turns a serial
-0.0 into +0.0; compare_records(..., rhs_signed_zero_equal=True) treats +0.0 == -0.0 for
those vectors only.

Sparse matrices are compared as sets of (row, col) entries: entries present on one side
only are pattern mismatches; entries on both sides must hold the same bits.
"""
import numpy as np

EQ_CODES = ["ni", "up", "te", "ti", "ng", "tg", "phi"]
FIRST_N = 10


def _bits(a):
    a = np.ascontiguousarray(a, dtype=np.float64)
    return a.view(np.uint64)


def nonfinite(a):
    return int(np.count_nonzero(~np.isfinite(np.asarray(a, dtype=np.float64))))


def vector_mismatch(a, b, signed_zero_equal=False):
    """Indices (0-based) where vectors a and b differ bitwise (or either is non-finite)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("shape mismatch {} vs {}".format(a.shape, b.shape))
    if signed_zero_equal:
        a = a + 0.0  # -0.0 + 0.0 == +0.0; every other value keeps its bits
        b = b + 0.0
    bad = _bits(a) != _bits(b)
    bad |= ~np.isfinite(a) | ~np.isfinite(b)
    return np.flatnonzero(bad)


def csr_entries(values, cols, rowptr):
    """(row, col, value) arrays, 0-based, from 1-based CSR (jac, jacj, jaci)."""
    rowptr = np.asarray(rowptr, dtype=np.int64)
    counts = np.diff(rowptr)
    rows = np.repeat(np.arange(len(counts), dtype=np.int64), counts)
    return rows, np.asarray(cols, dtype=np.int64) - 1, np.asarray(values, dtype=np.float64)


def matrix_mismatch(a, b, neq):
    """Compare two CSR matrices given as (values, cols, rowptr). Returns a dict with the
    mismatching entries as (row, col) arrays: value mismatches, entries only in a, only in b."""
    ra, ca, va = csr_entries(*a)
    rb, cb, vb = csr_entries(*b)
    ka = ra * neq + ca
    kb = rb * neq + cb
    oa = np.argsort(ka, kind="stable")
    ob = np.argsort(kb, kind="stable")
    ka, va = ka[oa], va[oa]
    kb, vb = kb[ob], vb[ob]
    dup = int(np.count_nonzero(np.diff(ka) == 0) + np.count_nonzero(np.diff(kb) == 0))
    common, ia, ib = np.intersect1d(ka, kb, assume_unique=False, return_indices=True)
    bad = (_bits(va[ia]) != _bits(vb[ib])) | ~np.isfinite(va[ia]) | ~np.isfinite(vb[ib])
    only_a = np.setdiff1d(ka, kb)
    only_b = np.setdiff1d(kb, ka)
    split = lambda k: (k // neq, k % neq)  # noqa: E731
    return {
        "value": split(common[bad]),
        "value_pairs": (va[ia][bad], vb[ib][bad]),
        "only_a": split(only_a),
        "only_b": split(only_b),
        "duplicates": dup,
        "nonfinite_a": nonfinite(va),
        "nonfinite_b": nonfinite(vb),
    }


def describe_iv(iv, eq, species, igyl):
    """'te(ix=3,iy=18)' or 'ni[1](ix=..)' for 0-based equation index iv."""
    code = int(eq[iv])
    name = EQ_CODES[code] if code >= 0 else ("?" if code == -1 else "ambiguous")
    sp = int(species[iv])
    ix, iy = (int(igyl[iv, 0]), int(igyl[iv, 1]))
    return "{}{}(ix={},iy={})".format(name, "[{}]".format(sp) if sp >= 0 else "", ix, iy)


def _eqname(eq, iv):
    code = int(eq[iv])
    return EQ_CODES[code] if code >= 0 else ("?" if code == -1 else "ambiguous")


def summarize_matrix(mm, eq, species, igyl):
    """Counts per (row equation, column equation) pair and the first entries."""
    pairs = {}
    first = []
    for kind in ("value", "only_a", "only_b"):
        rows, cols = mm[kind]
        for n, (r, c) in enumerate(zip(rows, cols)):
            key = "{}/{}".format(_eqname(eq, r), _eqname(eq, c))
            pairs.setdefault(key, {"value": 0, "only_a": 0, "only_b": 0})[kind] += 1
            if len([f for f in first if f["kind"] == kind]) < FIRST_N:
                entry = {"kind": kind, "row": describe_iv(r, eq, species, igyl),
                         "col": describe_iv(c, eq, species, igyl), "iv_row": int(r) + 1, "iv_col": int(c) + 1}
                if kind == "value":
                    entry["a"], entry["b"] = repr(float(mm["value_pairs"][0][n])), repr(float(mm["value_pairs"][1][n]))
                first.append(entry)
    total = sum(len(mm[k][0]) for k in ("value", "only_a", "only_b"))
    return {"mismatches": total, "value": len(mm["value"][0]), "only_a": len(mm["only_a"][0]),
            "only_b": len(mm["only_b"][0]), "duplicates": mm["duplicates"],
            "nonfinite_a": mm["nonfinite_a"], "nonfinite_b": mm["nonfinite_b"],
            "by_equation_pair": pairs, "first": first}


def summarize_vector(bad, a, b, eq, species, igyl):
    per_eq = {}
    for iv in bad:
        per_eq[_eqname(eq, iv)] = per_eq.get(_eqname(eq, iv), 0) + 1
    first = [{"iv": int(iv) + 1, "at": describe_iv(iv, eq, species, igyl), "a": repr(float(a[iv])),
              "b": repr(float(b[iv]))} for iv in bad[:FIRST_N]]
    return {"mismatches": int(len(bad)), "by_equation": per_eq, "first": first,
            "nonfinite_a": nonfinite(a), "nonfinite_b": nonfinite(b)}


def jacobians(record):
    """The list of (name, (values, cols, rowptr)) Jacobians a record holds, in order."""
    arr = record.arrays
    out = []
    n = int(record.meta.get("capture", {}).get("count", 0))
    for k in range(n):
        out.append(("captured[{}]".format(k), (arr["capjac_{}".format(k)], arr["capjacj_{}".format(k)],
                                               arr["capjaci_{}".format(k)])))
    out.append(("post_exmain", (arr["jac_post"], arr["jacj_post"], arr["jaci_post"])))
    return out


def compare_records(a, b, rhs_signed_zero_equal=None):
    """Compare record a (usually the reference) with record b. Returns a report dict with
    "agree" (bool) and one section per compared quantity."""
    neq = a.meta["neq"]
    report = {"a": a.label, "b": b.label, "agree": True, "sections": {}}

    def add(name, section):
        report["sections"][name] = section
        if section.get("mismatches", 0) or section.get("nonfinite_a", 0) or section.get("nonfinite_b", 0) \
                or section.get("error"):
            report["agree"] = False

    if b.meta["neq"] != neq:
        add("neq", {"error": "neq {} vs {}".format(neq, b.meta["neq"]), "mismatches": 1})
        return report
    eq, species, igyl = a.arrays["eq"], a.arrays["species"], a.arrays["igyl"]
    for side, rec in (("a", a), ("b", b)):
        if rec.meta.get("capture", {}).get("truncated"):
            add("capture_" + side, {"error": "{} saw more Jacobians than capture slots ({}); raise RunSpec.capture"
                .format(rec.label, rec.meta["capture"]["slots"]), "mismatches": 1})

    ja, jb = jacobians(a), jacobians(b)
    if [n for n, _ in ja] != [n for n, _ in jb]:
        add("jacobian_count", {"error": "jacobians {} vs {}".format([n for n, _ in ja], [n for n, _ in jb]),
                               "mismatches": 1})
    for (name, ma), (_, mb) in zip(ja, jb):
        add("jacobian:" + name, summarize_matrix(matrix_mismatch(ma, mb, neq), eq, species, igyl))

    for vec in ("sfscal", "suscal", "yldot"):
        bad = vector_mismatch(a.arrays[vec], b.arrays[vec])
        add(vec, summarize_vector(bad, a.arrays[vec], b.arrays[vec], eq, species, igyl))
    if "yldot_probe" in a.arrays and "yldot_probe" in b.arrays:
        szero = rhs_signed_zero_equal
        if szero is None:  # default: only when one side ran the parallel RHS
            szero = bool(a.meta.get("rhs_probe_parallel") or b.meta.get("rhs_probe_parallel"))
        bad = vector_mismatch(a.arrays["yldot_probe"], b.arrays["yldot_probe"], signed_zero_equal=szero)
        sec = summarize_vector(bad, a.arrays["yldot_probe"], b.arrays["yldot_probe"], eq, species, igyl)
        sec["signed_zero_equal"] = szero
        sec["parallel"] = [a.meta.get("rhs_probe_parallel"), b.meta.get("rhs_probe_parallel")]
        add("yldot_probe", sec)

    fa, fb = a.meta["fnrm_final_hex"], b.meta["fnrm_final_hex"]
    add("fnrm_final", {"mismatches": int(fa != fb), "a": fa, "b": fb})
    ia = [(i["iter"], i["fnrm_printed"]) for i in a.meta.get("iterations", [])]
    ib = [(i["iter"], i["fnrm_printed"]) for i in b.meta.get("iterations", [])]
    add("fnrm_printed", {"mismatches": int(ia != ib), "a": ia, "b": ib})
    return report


def format_report(report):
    lines = ["{} vs {}: {}".format(report["a"], report["b"], "AGREE" if report["agree"] else "MISMATCH")]
    for name, sec in report["sections"].items():
        if "error" in sec:
            lines.append("  {}: ERROR {}".format(name, sec["error"]))
            continue
        n = sec.get("mismatches", 0)
        nf = sec.get("nonfinite_a", 0) + sec.get("nonfinite_b", 0)
        if not n and not nf:
            lines.append("  {}: equal".format(name))
            continue
        detail = ""
        if "by_equation_pair" in sec:
            detail = " (value {}, only-a {}, only-b {}); pairs {}".format(
                sec["value"], sec["only_a"], sec["only_b"],
                ", ".join("{}: {}".format(k, sum(v.values())) for k, v in sorted(sec["by_equation_pair"].items())))
            if sec["first"]:
                f = sec["first"][0]
                detail += "; first {} row {} col {}".format(f["kind"], f["row"], f["col"])
        elif "by_equation" in sec:
            detail = "; by equation {}".format(sec["by_equation"])
            if sec["first"]:
                detail += "; first at {}".format(sec["first"][0]["at"])
        elif "a" in sec:
            detail = ": {} vs {}".format(sec["a"], sec["b"])
        lines.append("  {}: {} mismatch(es){}{}".format(name, n, " + {} non-finite".format(nf) if nf else "", detail))
    return "\n".join(lines)
