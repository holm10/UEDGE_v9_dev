"""Index truth, regions and the per-entry comparator of the yldot suite (PRD sections 6 and 7.4; decisions 19, 20, 26).

    imap = index_map(result.data, load_regions("d_only"))      # every row -> (equation, species, ix, iy, region)
    tol = tolerances(ref, sigma, rtol, k, imap)                 # tol_i = max(rtol_eq*|ref_i|, k*sigma_i), floors
    c = compare(new, ref, tol.tol, imap);  c.ok, c.report(diag_ref, diag_new)

Index truth (decision 19): the equation, species and cell of a yldot row come only from UEDGE's own index arrays.
bbb/convert.m:31-152 numbers the rows over iy = 1-iymnbcl..ny+iymxbcl, ix = 1-ixmnbcl..nx+ixmxbcl, one row per
equation where its is<eq>onxy mask is 1, and writes (ix, iy) to igyl(iv,1:2). index_map inverts idx* over exactly
those active cells and checks that the inverse is a bijection onto 1..neq that agrees with igyl. No variable order
is assumed anywhere. Limitation: igyl holds the cell only, so two equations' rows swapped within one cell keep a
valid bijection; the check sees every permutation that moves a row to another cell.

Regions: the [regions] table of family.toml, confirmed by the epic owner per family (2026-10-20, AIUE-83 ticket
page): guard, core, pf, inner_leg, sol, outer_leg. A double null (nxpt = 2, owner, 2026-10-21, AIUE-91 ticket page)
has one private-flux region per X-point, the band between the two separatrices and four legs instead: guard, core,
pf_upper, pf_lower, sol_between, sol, lower_inner_leg, upper_inner_leg, upper_outer_leg, lower_outer_leg. Guard rows
are compared under the same rule as interior rows (decision 20).

Every failure that needs the epic owner raises IndexTruthError or ToleranceEscalation; nothing is masked.
"""
import tomllib
from dataclasses import dataclass

import numpy as np

from .process import family_dir

# (equation, index array, mask array); the names follow the is<eq>on switches (bbb/bbb.v:217-222)
EQUATIONS = (("ni", "idxn", "isnionxy"), ("up", "idxu", "isuponxy"), ("te", "idxte", "isteonxy"),
             ("ti", "idxti", "istionxy"), ("ng", "idxg", "isngonxy"), ("tg", "idxtg", "istgonxy"),
             ("phi", "idxphi", "isphionxy"))
REGIONS = ("guard", "core", "pf", "inner_leg", "sol", "outer_leg", "pf_upper", "pf_lower", "sol_between",
           "lower_inner_leg", "upper_inner_leg", "upper_outer_leg", "lower_outer_leg")
DNULL_SOURCE = {"ixlb", "ixrb", "ixpt1", "ixpt2", "iysptrx1", "iysptrx2"}  # one value per mesh half
DNULL_IX = ("ix_lower_inner_leg", "ix_inner_core", "ix_upper_inner_leg", "ix_upper_outer_leg", "ix_outer_core",
            "ix_lower_outer_leg")
RULE_OWN, RULE_REGION, RULE_FAMILY = 0, 1, 2  # tol_i from sigma_i, the region floor, the eq/species fallback
OWNER = "ask the epic owner (decision 23)"
MAX_LISTED = 10

# The diagnostic arrays (state.DIAGNOSTIC_GROUPS) in the order pandf first assigns them. Static: from pandf
# (bbb/pandf.m:513-747) the call tree is walked in source order, each routine once, skipping the ismcnon and
# local-Jacobian routines (initialize_ismcnon, scale_mcnsor, jacobian_store_*, jacobian_reset); an array is placed at
# the first line that assigns it by name, whatever the branch. Built at 00acc43 (AIUE-83).
PANDF_ORDER = (
    # calc_driftterms2 (bbb/pandf_potencur.m)
    "fdiaxlb", "fdiaxrb",
    # calc_currents (bbb/pandf_potencur.m)
    "fq2d", "fq2", "fqyae", "fqyai", "fqyao", "fqyd", "fqyb", "fmity", "fqymi", "fqydti", "fqya", "fqym", "fqydt",
    "fqy", "fqygp",
    # calc_fqp1 (bbb/pandf_potencur.m)
    "fqp",
    # calc_fqp2 (bbb/pandf_potencur.m)
    "fqxb", "fqx",
    # calc_volumetric_sources (bbb/pandf_plasma_continuity.m)
    "snic", "sniv", "psori", "smoc", "smov", "seec", "seev", "seic", "seiv", "seik", "seid", "seidh", "psorbgz",
    "psorbgg", "psorgc", "psorc", "psordis", "psorxrc", "psorrgc", "msor", "msorxr", "psorg", "psor", "psorxr",
    "psorrg",
    # calc_curr_cx (bbb/pandf_potencur.m)
    "fqyn",
    # calc_volumetric_sources (bbb/pandf_plasma_continuity.m)
    "psorcxg", "psordisg",
    # neudif (bbb/pandf_gas_continuity.m)
    "fngxy", "fngx", "fngy", "resng",
    # neudifpg (bbb/pandf_gas_continuity.m)
    "fngy4ord", "fngx4ord",
    # neudifl (bbb/pandf_gas_continuity.m)
    "flngxy", "flngx",
    # calc_plasma_heatconductivities (bbb/pandf_plasma_energy.m)
    "qipar",
    # engbalg (bbb/pandf_gas_energy.m)
    "segc", "fegx", "fegxy",
    # calc_plasma_transport (bbb/pandf_plasma_continuity.m)
    "fnix", "fnixcb", "fniy", "fniycb", "fniy4ord",
    # calc_fniycbo (bbb/pandf_plasma_continuity.m)
    "fniycbo",
    # calc_plasma_momentum (bbb/pandf_plasma_momentum.m)
    "fmixy", "fmiy",
    # calc_plasma_energy (bbb/pandf_plasma_energy.m)
    "feiycbo", "feeycbo", "wvh", "floxibgt", "floxebgt", "feey4ord", "feey", "feiy4ord", "feiy", "feexy", "feixy",
    "feex", "feix", "erliz", "erlrc", "edisse", "vsoreec", "vsoree", "emolia", "psicx", "seit", "seak", "sead",
    "seadh", "pwrebkg", "pwribkg",
    # calc_gas_energy (bbb/pandf_gas_energy.m)
    "eiamoldiss",
    # calc_plasma_particle_residuals (bbb/pandf_plasma_continuity.m)
    "resco",
    # calc_plasma_momentum_residuals (bbb/pandf_plasma_momentum.m)
    "resmo",
    # calc_gas_energy_residuals (bbb/pandf_gas_energy.m)
    "reseg",
    # calc_plasma_energy_residuals (bbb/pandf_plasma_energy.m)
    "resee", "resei", "wjdote",
    # calc_potential_residuals (bbb/pandf_potencur.m)
    "resphi",
)
# Diagnostic arrays the walk above cannot place: written only through call arguments (e.g. fmix in the call at
# bbb/pandf_plasma_momentum.m:200), or not by name on that path. first_difference checks them after PANDF_ORDER.
UNORDERED = (
    "fegy", "flngy", "flnix", "flniy", "fmgx", "fmgy", "fmix", "fngxs", "fngyx", "fnixtot", "fniytot", "fq2pneo",
    "fq2qneo", "fqypneo", "fqyqneo", "newfnglb", "newfnglbth", "newfngpf", "newfngpfth", "newfngrb", "newfngrbth",
    "newfngw", "newfngwth", "psor_tmpov", "psorcxgc", "psort", "qgpar",
)


class IndexTruthError(Exception):
    """The index arrays or the recorded regions do not describe the yldot rows: the epic owner has to look."""


class ToleranceEscalation(Exception):
    """Entries with sigma_i = 0 and no non-zero sigma in their equation and species: PRD section 7.4 sends them to
    the epic owner."""


def listed(items):
    items = list(items)
    more = " (+{} more)".format(len(items) - MAX_LISTED) if len(items) > MAX_LISTED else ""
    return "{}{}".format(items[:MAX_LISTED], more)


# ---------------------------------------------------------------- regions


def span(r):
    """A [first, last] range from family.toml (inclusive, as in Fortran), or [] for none, as a range object."""
    if len(r) == 0:
        return range(0)
    first, last = (int(v) for v in r)
    return range(first, last + 1)


def source_value(grid, key, dnull=False):
    """The live grid value behind a [regions] source key; for a double null, the values of both mesh halves."""
    if dnull:
        return [int(v) for v in np.asarray(grid[key]).flat[:2]]
    getters = {"ixpt1": lambda g: g["ixpt1"].flat[0], "ixpt2": lambda g: g["ixpt2"].flat[0],
               "iysptrx": lambda g: g["iysptrx"], "nxcore": lambda g: g["nxcore"][0, 1],
               "nxleg": lambda g: g["nxleg"][0, 1], "nycore": lambda g: g["nycore"][0]}
    return int(getters[key](grid))


def recorded_source(spec):
    """The [regions] source values as ints (double null: a list of two per key)."""
    return {k: [int(x) for x in v] if isinstance(v, list) else int(v) for k, v in spec["source"].items()}


def is_dnull(spec):
    return set(spec["source"]) == DNULL_SOURCE


def derived_ranges(spec):
    """The ranges the owner's rule gives from the recorded source values (owner, 2026-10-20):
    mhdgeo = 1: inner leg 1..ixpt1, core ixpt1+1..ixpt2, outer leg ixpt2+1..nx; closed rows 1..iysptrx;
    slab half mesh (symmetry boundary at ix = 0, one leg): core 1..nxcore, outer leg nxcore+1..nxcore+nxleg;
    closed rows 1..nycore.
    Double null (owner, 2026-10-21), upper X-point primary: half 1 (ixlb(1) = 0..ixrb(1)) runs from the lower inner
    plate over ixpt1(1) (lower X-point) and ixpt2(1) (upper) to the upper inner plate, half 2 (ixlb(2)..ixrb(2)) from
    the upper outer plate over ixpt1(2) (upper) and ixpt2(2) (lower) to the lower outer plate. Each leg and core side
    is the interior between those cuts. Rows 1..su are closed (su = iysptrx2(1), the upper separatrix), su+1..sl lie
    between the separatrices (sl = iysptrx1(1)), sl+1..ny are open."""
    src, nx, ny = spec["source"], int(spec["nx"]), int(spec["ny"])
    if set(src) == DNULL_SOURCE:
        s = recorded_source(spec)
        lb, rb, p1, p2, y1, y2 = (s[k] for k in ("ixlb", "ixrb", "ixpt1", "ixpt2", "iysptrx1", "iysptrx2"))
        su, sl = y2[0], y1[0]
        if lb[0] != 0 or y1[1] != su or y2[1] != sl or su > sl:
            raise IndexTruthError("[regions] double-null source {}: the rule needs ixlb(1) = 0, iysptrx1(2) = "
                                  "iysptrx2(1) <= iysptrx1(1) = iysptrx2(2) (upper X-point primary); {}"
                                  .format(s, OWNER))
        return {"ix_lower_inner_leg": [lb[0] + 1, p1[0]], "ix_inner_core": [p1[0] + 1, p2[0]],
                "ix_upper_inner_leg": [p2[0] + 1, rb[0]], "ix_upper_outer_leg": [lb[1] + 1, p1[1]],
                "ix_outer_core": [p1[1] + 1, p2[1]], "ix_lower_outer_leg": [p2[1] + 1, rb[1]],
                "iy_closed": [1, su], "iy_between": [su + 1, sl] if sl > su else [], "iy_open": [sl + 1, ny]}
    if set(src) == {"ixpt1", "ixpt2", "iysptrx"}:
        a, b, c = int(src["ixpt1"]), int(src["ixpt2"]), int(src["iysptrx"])
        return {"ix_inner_leg": [1, a], "ix_core": [a + 1, b], "ix_outer_leg": [b + 1, nx], "iy_closed": [1, c],
                "iy_open": [c + 1, ny]}
    if set(src) == {"nxcore", "nxleg", "nycore"}:
        a, b, c = int(src["nxcore"]), int(src["nxleg"]), int(src["nycore"])
        return {"ix_inner_leg": [], "ix_core": [1, a], "ix_outer_leg": [a + 1, a + b], "iy_closed": [1, c],
                "iy_open": [c + 1, ny]}
    raise IndexTruthError("[regions] source {} is neither (ixpt1, ixpt2, iysptrx), (nxcore, nxleg, nycore) nor {}: {}"
                          .format(sorted(src), sorted(DNULL_SOURCE), OWNER))


def guard_ix(spec):
    """The guard columns: 0 and nx+1, and for a double null also the cut between the halves, ixrb(1)+1 and ixlb(2)
    (owner, 2026-10-21)."""
    nx = int(spec["nx"])
    if is_dnull(spec):
        s = spec["source"]
        return {0, int(s["ixrb"][0]) + 1, int(s["ixlb"][1]), nx + 1}
    return {0, nx + 1}


def region_of_dnull(ix, iy, spec):
    if iy in span(spec["iy_closed"]):
        if ix in span(spec["ix_inner_core"]) or ix in span(spec["ix_outer_core"]):
            return "core"
        if ix in span(spec["ix_upper_inner_leg"]) or ix in span(spec["ix_upper_outer_leg"]):
            return "pf_upper"
        return "pf_lower"
    if iy in span(spec["iy_between"]):
        if ix in span(spec["ix_lower_inner_leg"]) or ix in span(spec["ix_lower_outer_leg"]):
            return "pf_lower"
        return "sol_between"
    for leg in ("lower_inner_leg", "upper_inner_leg", "upper_outer_leg", "lower_outer_leg"):
        if ix in span(spec["ix_" + leg]):
            return leg
    return "sol"


def region_of(ix, iy, spec):
    """The region of cell (ix, iy) under a [regions] spec."""
    nx, ny = int(spec["nx"]), int(spec["ny"])
    if "iy_between" in spec:
        if ix in guard_ix(spec) or iy in (0, ny + 1):
            return "guard"
        return region_of_dnull(ix, iy, spec)
    if ix in (0, nx + 1) or iy in (0, ny + 1):
        return "guard"
    if iy in span(spec["iy_closed"]):
        return "core" if ix in span(spec["ix_core"]) else "pf"
    if ix in span(spec["ix_inner_leg"]):
        return "inner_leg"
    if ix in span(spec["ix_core"]):
        return "sol"
    return "outer_leg"


def region_cells(spec):
    """Cell count per region over the whole (0..nx+1) x (0..ny+1) mesh."""
    nx, ny = int(spec["nx"]), int(spec["ny"])
    counts = dict.fromkeys(REGIONS, 0)
    for ix in range(nx + 2):
        for iy in range(ny + 2):
            counts[region_of(ix, iy, spec)] += 1
    return counts


def check_regions(spec, grid=None):
    """IndexTruthError unless the [regions] spec is the owner's rule applied to its source values, partitions the
    interior, matches its recorded cell counts and, given the live grid, matches nx, ny and the source values."""
    errors = []
    nx, ny = int(spec["nx"]), int(spec["ny"])
    for key, want in derived_ranges(spec).items():
        if [int(v) for v in spec[key]] != want:
            errors.append("{} = {}, the owner's rule gives {} from source {}".format(key, spec[key], want,
                                                                                    spec["source"]))
    dnull = is_dnull(spec)
    ix_keys = DNULL_IX if dnull else ("ix_inner_leg", "ix_core", "ix_outer_leg")
    iy_keys = ("iy_closed", "iy_between", "iy_open") if dnull else ("iy_closed", "iy_open")
    ix_interior = sorted(set(range(1, nx + 1)) - guard_ix(spec))
    if sorted(i for k in ix_keys for i in span(spec[k])) != ix_interior:
        errors.append("the ix ranges do not partition 1..{}{}".format(
            nx, " without the guard columns {}".format(sorted(guard_ix(spec) - {0, nx + 1})) if dnull else ""))
    if sorted(i for k in iy_keys for i in span(spec[k])) != list(range(1, ny + 1)):
        errors.append("the iy ranges do not partition 1..{}".format(ny))
    if not errors:
        counts = region_cells(spec)
        recorded = {r: int(spec["cells"].get(r, 0)) for r in REGIONS}
        if counts != recorded:
            errors.append("cell counts {} differ from the recorded cells {}".format(counts, recorded))
    if grid is not None:
        live_dnull = int(grid["mhdgeo"]) == 1 and int(grid["nxpt"]) == 2
        live = {"nx": int(grid["nx"]), "ny": int(grid["ny"])}
        if not dnull or live_dnull:
            live.update({k: source_value(grid, k, dnull) for k in spec["source"]})
        rec = {"nx": nx, "ny": ny}
        rec.update(recorded_source(spec))
        if live != rec:
            errors.append("recorded {} differ from the live grid {}".format(rec, live))
        if live_dnull:
            scheme = DNULL_SOURCE
        else:
            scheme = {"ixpt1", "ixpt2", "iysptrx"} if int(grid["mhdgeo"]) == 1 else {"nxcore", "nxleg", "nycore"}
        if set(spec["source"]) != scheme:
            errors.append("mhdgeo = {}{} but [regions] source is {}".format(
                int(grid["mhdgeo"]), ", nxpt = {}".format(int(grid["nxpt"])) if int(grid["mhdgeo"]) == 1 else "",
                sorted(spec["source"])))
        if scheme == {"nxcore", "nxleg", "nycore"} and (grid["nxcore"][0, 0] != 0 or grid["nxleg"][0, 0] != 0):
            errors.append("the half-mesh rule needs nxcore[0,0] = nxleg[0,0] = 0, the grid has {}, {}".format(
                int(grid["nxcore"][0, 0]), int(grid["nxleg"][0, 0])))
    if errors:
        raise IndexTruthError("[regions]: {}; {}".format("; ".join(errors), OWNER))


def load_regions(family):
    """The [regions] table of the family's family.toml."""
    toml = family_dir(family) / "family.toml"
    with open(toml, "rb") as f:
        spec = tomllib.load(f).get("regions")
    if spec is None:
        raise IndexTruthError("{}: no [regions] table; {}".format(toml, OWNER))
    return spec


# ---------------------------------------------------------------- index truth


@dataclass
class IndexMap:
    """Per yldot row (0-based i, Fortran row i+1): equation, species (1-based), cell and region."""
    neq: int
    eq: np.ndarray
    species: np.ndarray
    ix: np.ndarray
    iy: np.ndarray
    region: np.ndarray

    def label(self, i):
        region = " " + self.region[i] if self.region[i] else ""
        return "{}[{}] ix={} iy={}{} (row {})".format(self.eq[i], self.species[i], self.ix[i], self.iy[i], region,
                                                      i + 1)

    def blocks(self):
        """{(equation, species): rows}, in EQUATIONS order."""
        out = {}
        for name, _, _ in EQUATIONS:
            for sp in np.unique(self.species[self.eq == name]):
                out[(name, int(sp))] = np.flatnonzero((self.eq == name) & (self.species == sp))
        return out

    def groups(self):
        """{(equation, species, region): rows}."""
        out = {}
        for (name, sp), rows in self.blocks().items():
            for r in REGIONS:
                sel = rows[self.region[rows] == r]
                if sel.size:
                    out[(name, sp, r)] = sel
        return out


def cells3(a):
    a = np.asarray(a)
    return a[..., None] if a.ndim == 2 else a


def index_map(data, regions=None):
    """The inverse of idx* over the active cells, checked against neq and igyl. data: an evaluation result (neq,
    the idx* arrays, igyl, masks, grid). regions: a [regions] spec, checked and applied."""
    neq, grid, masks = int(data["neq"]), data["grid"], data["masks"]
    nx, ny = int(grid["nx"]), int(grid["ny"])
    in_range = np.zeros((nx + 2, ny + 2), dtype=bool)
    in_range[1 - int(grid["ixmnbcl"]):nx + int(grid["ixmxbcl"]) + 1,
             1 - int(grid["iymnbcl"]):ny + int(grid["iymxbcl"]) + 1] = True
    eq = np.full(neq, "", dtype=object)
    species = np.zeros(neq, dtype=np.int64)
    ix = np.full(neq, -1, dtype=np.int64)
    iy = np.full(neq, -1, dtype=np.int64)
    count = np.zeros(neq, dtype=np.int64)
    errors = []
    for name, idx_name, mask_name in EQUATIONS:
        idx, mask = cells3(data[idx_name]), cells3(masks[mask_name])
        # convert.m loops the species of each equation up to the idx* array's own bound (idxu: nusp), while
        # isuponxy is dimensioned nisp (bbb/bbb.v:237): mask slices past that bound are never read
        if idx.shape[:2] != (nx + 2, ny + 2) or mask.shape[:2] != idx.shape[:2] or mask.shape[2] < idx.shape[2]:
            errors.append("{} {} / {} {} do not fit the ({}, {}) mesh".format(idx_name, idx.shape, mask_name,
                                                                             mask.shape, nx + 2, ny + 2))
            continue
        mask = mask[..., :idx.shape[2]]
        for s in range(idx.shape[2]):
            a = idx[..., s]
            active = (mask[..., s] == 1) & in_range
            stale = ~active & (a != 0)
            if stale.any():
                errors.append("{}[{}] holds a row number at {} inactive cells, first (ix, iy) {}".format(
                    idx_name, s + 1, int(stale.sum()), listed(map(tuple, np.argwhere(stale).tolist()))))
            where = np.argwhere(active)  # row-major, the same order as a[active]
            rows = a[active].astype(np.int64)
            bad = (rows < 1) | (rows > neq)
            if bad.any():
                errors.append("{}[{}] has row numbers outside 1..{} at (ix, iy) {}".format(
                    idx_name, s + 1, neq, listed(map(tuple, where[bad].tolist()))))
            r = rows[~bad] - 1
            np.add.at(count, r, 1)
            eq[r], species[r] = name, s + 1
            ix[r], iy[r] = where[~bad, 0], where[~bad, 1]
    missing, twice = np.flatnonzero(count == 0), np.flatnonzero(count > 1)
    if missing.size:
        errors.append("{} of rows 1..{} claimed by no active cell: {}".format(missing.size, neq,
                                                                            listed(missing + 1)))
    if twice.size:
        errors.append("{} rows claimed more than once: {}".format(twice.size, listed(twice + 1)))
    igyl = np.asarray(data["igyl"])
    if igyl.ndim != 2 or igyl.shape[0] < neq or igyl.shape[1] != 2:
        errors.append("igyl has shape {}, need (>= {}, 2)".format(igyl.shape, neq))
    else:
        once = count == 1
        off = np.flatnonzero(once & ((igyl[:neq, 0] != ix) | (igyl[:neq, 1] != iy)))
        if off.size:
            errors.append("{} rows where igyl disagrees with the idx* cell, first {}".format(off.size, listed(
                "row {}: idx* ({}, {}) igyl ({}, {})".format(i + 1, ix[i], iy[i], igyl[i, 0], igyl[i, 1])
                for i in off)))
    if errors:
        raise IndexTruthError("index truth: {}; {}".format("; ".join(errors), OWNER))
    region = np.full(neq, "", dtype=object)
    if regions is not None:
        check_regions(regions, grid)
        region = np.array([region_of(int(a), int(b), regions) for a, b in zip(ix, iy)], dtype=object)
    return IndexMap(neq, eq.astype(str), species, ix, iy, region.astype(str))


# ---------------------------------------------------------------- tolerances and comparison


@dataclass
class Tolerance:
    tol: np.ndarray
    rule: np.ndarray  # RULE_OWN, RULE_REGION or RULE_FAMILY per entry


def tolerances(ref, sigma, rtol, k, imap):
    """PRD section 7.4: tol_i = max(rtol_eq*|ref_i|, k*sigma_i) where sigma_i > 0; where sigma_i = 0, k*sigma_min,r
    with sigma_min,r the smallest non-zero sigma of the entry's (equation, species, region), else of its (equation,
    species) over the family; else ToleranceEscalation. rtol: {equation: rtol_eq}. Needs imap with regions."""
    ref, sigma = np.asarray(ref, dtype=float), np.asarray(sigma, dtype=float)
    for name, a in (("ref", ref), ("sigma", sigma)):
        if a.shape != (imap.neq,):
            raise ValueError("{} has shape {}, need ({},)".format(name, a.shape, imap.neq))
        if not np.isfinite(a).all():
            raise ValueError("{} has non-finite entries at rows {}".format(name, listed(
                np.flatnonzero(~np.isfinite(a)) + 1)))
    if (sigma < 0).any():
        raise ValueError("sigma is negative at rows {}".format(listed(np.flatnonzero(sigma < 0) + 1)))
    if not (np.isfinite(k) and k > 0):
        raise ValueError("k = {}, need a finite k > 0".format(k))
    if (imap.region == "").any():
        raise ValueError("tolerances need an index map with regions")
    missing = sorted(set(imap.eq) - set(rtol))
    if missing:
        raise ValueError("rtol has no value for equations {}".format(missing))
    if not all(np.isfinite(rtol[e]) and rtol[e] >= 0 for e in set(imap.eq)):
        raise ValueError("rtol values must be finite and >= 0: {}".format(rtol))
    base = np.array([rtol[e] for e in imap.eq], dtype=float) * np.abs(ref)
    tol = np.maximum(base, k * sigma)
    rule = np.full(imap.neq, RULE_OWN, dtype=np.int8)
    zero = sigma == 0
    escalate = []
    for (name, sp), rows in imap.blocks().items():
        if not zero[rows].any():
            continue
        nonzero = sigma[rows][sigma[rows] > 0]
        family_min = nonzero.min() if nonzero.size else None
        for r in REGIONS:
            group = rows[imap.region[rows] == r]
            z = group[zero[group]]
            if not z.size:
                continue
            nz = sigma[group][sigma[group] > 0]
            if nz.size:
                floor, code = nz.min(), RULE_REGION
            elif family_min is not None:
                floor, code = family_min, RULE_FAMILY
            else:
                escalate.append("{}[{}] {}: {} entries".format(name, sp, r, z.size))
                continue
            tol[z] = np.maximum(base[z], k * floor)
            rule[z] = code
    if escalate:
        raise ToleranceEscalation("sigma = 0 in a whole equation and species, no floor: {}; {}".format(
            "; ".join(escalate), OWNER))
    return Tolerance(tol, rule)


@dataclass
class Difference:
    """The first diagnostic array that differs (first_difference)."""
    name: str
    ordered: bool
    kind: str  # "values", "shape", "missing in reference", "missing in new"
    max_rel: float = float("nan")
    index: tuple = None

    def __str__(self):
        where = "pandf order" if self.ordered else "unordered (not placed in pandf order)"
        if self.kind != "values":
            return "{} ({}): {}".format(self.name, where, self.kind)
        return "{} ({}): max relative difference {:.3e} at {}".format(self.name, where, self.max_rel, self.index)


def first_difference(ref_diag, new_diag, rtol=0.0):
    """The first array, in PANDF_ORDER and then the others sorted, whose max relative difference |a-b|/max(|a|,|b|)
    exceeds rtol (0 = bitwise), or that is missing on one side or changed shape. None if all agree.

    A heuristic for localization, never a pass/fail decision: an UNORDERED array is reported only when no ordered one
    differs, although pandf may write it earlier (fmix, written through a call argument before fmixy)."""
    names = set(ref_diag) | set(new_diag)
    ordered = [n for n in PANDF_ORDER if n in names]
    for n in ordered + sorted(names - set(PANDF_ORDER)):
        in_order = n in PANDF_ORDER
        if n not in ref_diag or n not in new_diag:
            return Difference(n, in_order, "missing in reference" if n not in ref_diag else "missing in new")
        a, b = np.asarray(ref_diag[n], dtype=float), np.asarray(new_diag[n], dtype=float)
        if a.shape != b.shape:
            return Difference(n, in_order, "shape")
        with np.errstate(invalid="ignore", divide="ignore"):
            rel = np.where(a == b, 0.0, np.abs(a - b) / np.maximum(np.abs(a), np.abs(b)))
        rel[np.isnan(rel) & ~(np.isnan(a) & np.isnan(b))] = np.inf
        rel[np.isnan(rel)] = 0.0  # NaN in both: same value for this purpose
        if rel.size and rel.max() > rtol:
            i = np.unravel_index(int(np.argmax(rel)), rel.shape)
            return Difference(n, in_order, "values", float(rel[i]), tuple(int(v) for v in i))
    return None


@dataclass
class Comparison:
    ok: bool
    n_fail: int
    fail_mask: np.ndarray
    per_block: dict  # {(equation, species): failing count}
    worst: list  # dicts: row, label, ref, new, diff, tol, ratio; worst first
    imap: IndexMap

    def report(self, diag_ref=None, diag_new=None, rtol_diag=0.0):
        if self.ok:
            return "PASS: all {} entries within tolerance".format(self.imap.neq)
        lines = ["FAIL: {} of {} entries out of tolerance".format(self.n_fail, self.imap.neq),
                 "failing per equation: " + ", ".join("{}[{}] {}".format(e, s, n)
                                                      for (e, s), n in self.per_block.items() if n)]
        lines.append("worst entries (|new - ref| / tol):")
        for w in self.worst:
            lines.append("  {:40s} ref {: .6e} new {: .6e} diff {: .3e} tol {:.3e} ratio {:.3g}".format(
                w["label"], w["ref"], w["new"], w["diff"], w["tol"], w["ratio"]))
        if diag_ref is not None and diag_new is not None:
            d = first_difference(diag_ref, diag_new, rtol_diag)
            lines.append("first differing intermediate: {}".format(d if d is not None else "none"))
        return "\n".join(lines)


def compare(new, ref, tol, imap, worst=10):
    """Full-vector comparison |new_i - ref_i| <= tol_i (PRD section 7.4); NaN and Inf in new fail.

    imap labels both vectors: the caller must first check that the run that produced new has the same index map as
    the reference (the same idx*, igyl and neq); compare only checks the lengths."""
    new, ref, tol = (np.asarray(a, dtype=float) for a in (new, ref, tol))
    for name, a in (("new", new), ("ref", ref), ("tol", tol)):
        if a.shape != (imap.neq,):
            raise ValueError("{} has shape {}, need ({},)".format(name, a.shape, imap.neq))
    if not (np.isfinite(tol).all() and (tol > 0).all()):
        raise ValueError("tol must be finite and > 0 at every entry")
    if not np.isfinite(ref).all():
        raise ValueError("ref has non-finite entries at rows {}".format(listed(np.flatnonzero(~np.isfinite(ref)) + 1)))
    with np.errstate(invalid="ignore", over="ignore"):
        diff = new - ref
        fail = ~(np.abs(diff) <= tol)
        ratio = np.abs(diff) / tol
    ratio[~np.isfinite(ratio)] = np.inf
    rows = np.flatnonzero(fail)
    rows = rows[np.argsort(-ratio[rows], kind="stable")][:worst]
    entries = [{"row": int(i) + 1, "label": imap.label(i), "ref": float(ref[i]), "new": float(new[i]),
                "diff": float(diff[i]), "tol": float(tol[i]), "ratio": float(ratio[i])} for i in rows]
    per_block = {key: int(fail[r].sum()) for key, r in imap.blocks().items()}
    return Comparison(not fail.any(), int(fail.sum()), fail, per_block, entries, imap)
