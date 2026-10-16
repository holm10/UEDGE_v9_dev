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
    if rowptr.ndim != 1 or len(rowptr) < 1 or rowptr[0] != 1 or np.any(np.diff(rowptr) < 0) \
            or rowptr[-1] - 1 != len(values) or len(values) != len(cols):
        raise IndexError("inconsistent CSR arrays: rowptr[0]={}, rowptr[-1]-1={}, {} values, {} columns".format(
            rowptr[0] if len(rowptr) else None, rowptr[-1] - 1 if len(rowptr) else None, len(values), len(cols)))
    counts = np.diff(rowptr)
    rows = np.repeat(np.arange(len(counts), dtype=np.int64), counts)
    return rows, np.asarray(cols, dtype=np.int64) - 1, np.asarray(values, dtype=np.float64)


def matrix_mismatch(a, b, neq):
    """Compare two CSR matrices given as (values, cols, rowptr). Returns a dict with the
    mismatching entries as (row, col) arrays: value mismatches, entries only in a, only in b."""
    ra, ca, va = csr_entries(*a)
    rb, cb, vb = csr_entries(*b)
    for name, rows, cols in (("a", ra, ca), ("b", rb, cb)):
        if len(cols) and (cols.min() < 0 or cols.max() >= neq or rows.max() >= neq):
            raise IndexError("matrix {}: column/row index outside 1..neq={}".format(name, neq))
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
    """'te(ix=3,iy=18)' or 'ni[1](ix=..)' for 0-based equation index iv; 'position 12' when no map
    applies (igyl is None, e.g. a permuted matrix)."""
    if igyl is None:
        return "position {}".format(int(iv) + 1)
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
    total = sum(len(mm[k][0]) for k in ("value", "only_a", "only_b")) + mm["duplicates"]
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
    """The list of (name, (values, cols, rowptr), localisable) Jacobians a record holds, in order.
    localisable is False for a matrix whose rows/columns are permuted (post-exmain after psetnk
    with ireorder=1): it is compared position by position but not mapped to cells."""
    arr = record.arrays
    out = []
    n = int(record.meta.get("capture", {}).get("count", 0))
    for k in range(n):
        out.append(("captured[{}]".format(k), (arr["capjac_{}".format(k)], arr["capjacj_{}".format(k)],
                                               arr["capjaci_{}".format(k)]), True))
    permuted = bool(record.meta.get("post_exmain_permuted", False))
    out.append(("post_exmain" + (" (permuted indices)" if permuted else ""),
                (arr["jac_post"], arr["jacj_post"], arr["jaci_post"]), not permuted))
    return out


SERIAL_SWITCHES = ("OMPParallelJac", "OMPParallelPandf1", "ParallelJac", "ParallelPandf1")
DIAGNOSTIC_SWITCHES = ("CheckJac", "CheckPandf1", "ForceSerialCheck")


def check_arm(record, spec=None):
    """Problems (list of strings; empty = fine) showing that a run did not do what its arm asked:
    the OpenMP path didn't run, the thread count wasn't applied, a diagnostic switch was on, the
    captured Jacobians came from the wrong routine. spec defaults to the record's own spec."""
    spec = spec or record.meta.get("spec", {})
    arm, threads = spec.get("arm"), spec.get("threads")
    prov = record.meta.get("provenance", {})
    problems = []
    if not prov:
        return ["no provenance recorded"]
    if arm == "serial":
        for name in SERIAL_SWITCHES:
            if prov.get(name) != 0:
                problems.append("serial arm but {}={}".format(name, prov.get(name)))
    elif arm in ("jac", "jacrhs"):
        if prov.get("ParallelJac") != 1:
            problems.append("{} arm but ParallelJac={} (OpenMP Jacobian did not run: serial build?)"
                            .format(arm, prov.get("ParallelJac")))
        if arm == "jacrhs":
            if prov.get("ParallelPandf1") != 1:
                problems.append("jacrhs arm but ParallelPandf1={}".format(prov.get("ParallelPandf1")))
            if not record.meta.get("rhs_probe_parallel", False):
                problems.append("jacrhs arm but the RHS probe did not take the parallel branch")
        if prov.get("openmp_build") is False:
            problems.append("{} arm run with a build that has no OpenMP runtime".format(arm))
    else:
        problems.append("unknown arm {!r}".format(arm))
    if threads is not None:
        if prov.get("Nthreads") != threads:
            problems.append("Nthreads={} but {} requested".format(prov.get("Nthreads"), threads))
        if str(prov.get("OMP_NUM_THREADS")) != str(threads):
            problems.append("OMP_NUM_THREADS={} but {} requested".format(prov.get("OMP_NUM_THREADS"), threads))
    for name in DIAGNOSTIC_SWITCHES:
        if prov.get(name, 0) != 0:
            problems.append("diagnostic switch {}={} in a measured run".format(name, prov.get(name)))
    cap = record.meta.get("capture", {})
    want = "jac_calc" if arm == "serial" else "jac_calc_parallel"
    wrong = [s for s in cap.get("source", []) if s != want]
    if wrong:
        problems.append("captured Jacobians from {} on the {} arm".format(sorted(set(wrong)), arm))
    if cap.get("truncated"):
        problems.append("more Jacobians than capture slots ({}); raise RunSpec.capture".format(cap.get("slots")))
    if not record.meta.get("iterations"):
        problems.append("no nksol iterations recorded")
    return problems


def _parallel_rhs(record):
    return int(record.meta.get("provenance", {}).get("ParallelPandf1", 0)) > 0


def compare_records(a, b, rhs_signed_zero_equal=None):
    """Compare record a (usually the reference) with record b.

    Returns a report dict: "agree" (True only if every section matches and there are no
    errors), "errors" (list: reasons the comparison can't be trusted -> harness error, exit 2)
    and one section per compared quantity (mismatch -> exit 1)."""
    report = {"a": a.label, "b": b.label, "agree": True, "errors": [], "sections": {}}

    def add(name, section):
        report["sections"][name] = section
        if section.get("mismatches", 0) or section.get("nonfinite_a", 0) or section.get("nonfinite_b", 0):
            report["agree"] = False

    def error(message):
        report["errors"].append(message)
        report["agree"] = False

    for side, rec in (("a", a), ("b", b)):
        for problem in check_arm(rec):
            error("{} ({}): {}".format(side, rec.label, problem))
        for name in ("yldot", "sfscal", "suscal", "eq", "species", "igyl", "jac_post", "jacj_post", "jaci_post"):
            if name not in rec.arrays:
                error("{} ({}): {} missing from the record".format(side, rec.label, name))
    neq = a.meta.get("neq")
    if b.meta.get("neq") != neq:
        error("neq {} vs {}: different problems".format(neq, b.meta.get("neq")))
    sa, sb = a.meta.get("spec", {}), b.meta.get("spec", {})
    for key in ("preset", "itermx"):
        if sa.get(key) != sb.get(key):
            error("spec {} differs: {!r} vs {!r} (different problems)".format(key, sa.get(key), sb.get(key)))
    if report["errors"]:
        return report
    eq, species, igyl = a.arrays["eq"], a.arrays["species"], a.arrays["igyl"]
    for name in ("eq", "species", "igyl"):
        if not np.array_equal(a.arrays[name], b.arrays[name]):
            error("equation map {} differs between the records".format(name))
    if a.meta.get("capture", {}).get("hook") != b.meta.get("capture", {}).get("hook"):
        error("only one record has captured Jacobians (capture hook in one build only)")
    if report["errors"]:
        return report

    ja, jb = jacobians(a), jacobians(b)
    if [n for n, _, _ in ja] != [n for n, _, _ in jb]:
        add("jacobian_count", {"mismatches": 1, "a": [n for n, _, _ in ja], "b": [n for n, _, _ in jb]})
    for (name, ma, loc), (_, mb, _) in zip(ja, jb):
        try:
            mm = matrix_mismatch(ma, mb, neq)
        except IndexError as err:  # out-of-range index or inconsistent CSR arrays
            error("jacobian {}: {}".format(name, err))
            continue
        if loc:
            add("jacobian:" + name, summarize_matrix(mm, eq, species, igyl))
        else:
            sec = summarize_matrix(mm, np.full(neq, -1), np.full(neq, -1), None)
            sec["note"] = "permuted indices: positions compared, not mapped to cells"
            add("jacobian:" + name, sec)

    # The parallel RHS's REDUCTION(+) turns a serial -0.0 into +0.0 (ppp/omp_parallel.F90): for every
    # yldot a parallel RHS may have produced, +0.0 == -0.0 (counted separately).
    szero_auto = _parallel_rhs(a) or _parallel_rhs(b)
    szero = szero_auto if rhs_signed_zero_equal is None else rhs_signed_zero_equal
    for vec in ("sfscal", "suscal", "yldot", "yldot_probe"):
        if vec == "yldot_probe" and vec not in a.arrays and vec not in b.arrays:
            continue
        if (vec in a.arrays) != (vec in b.arrays):
            add(vec, {"mismatches": 1, "error": "{} present in one record only".format(vec)})
            continue
        zero_ok = szero and vec in ("yldot", "yldot_probe")
        bad = vector_mismatch(a.arrays[vec], b.arrays[vec], signed_zero_equal=zero_ok)
        sec = summarize_vector(bad, a.arrays[vec], b.arrays[vec], eq, species, igyl)
        if vec in ("yldot", "yldot_probe"):
            sec["signed_zero_equal"] = zero_ok
            if zero_ok:
                strict = vector_mismatch(a.arrays[vec], b.arrays[vec])
                sec["signed_zero_differences"] = int(len(strict) - len(bad))
        if vec == "yldot_probe":
            sec["parallel"] = [a.meta.get("rhs_probe_parallel"), b.meta.get("rhs_probe_parallel")]
        add(vec, sec)

    fa, fb = a.meta["fnrm_final_hex"], b.meta["fnrm_final_hex"]
    add("fnrm_final", {"mismatches": int(fa != fb), "a": fa, "b": fb})
    ia = [(i["iter"], i["fnrm_printed"]) for i in a.meta["iterations"]]
    ib = [(i["iter"], i["fnrm_printed"]) for i in b.meta["iterations"]]
    add("fnrm_printed", {"mismatches": int(ia != ib), "a": ia, "b": ib})
    return report


def format_report(report):
    verdict = "ERROR" if report.get("errors") else ("AGREE" if report["agree"] else "MISMATCH")
    lines = ["{} vs {}: {}".format(report["a"], report["b"], verdict)]
    for err in report.get("errors", []):
        lines.append("  ERROR: {}".format(err))
    for name, sec in report["sections"].items():
        if "error" in sec:
            lines.append("  {}: MISMATCH {}".format(name, sec["error"]))
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
