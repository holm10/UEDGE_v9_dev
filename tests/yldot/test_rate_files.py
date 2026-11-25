"""The synthetic rate files of tests/yldot/data (tools/make_rate_files.py; tracker T169).

They are exactly what the generator writes; each says, on its first or second line and on its last, that it is not
actual data; no real rate table is tracked anywhere in the repository, compressed files and archives included (the
known ones, by SHA-256); and UEDGE's own readers return the generator's values for every table of every file. Each
check is shown failing on a planted defect.
"""
import bz2
import gzip
import hashlib
import io
import json
import lzma
import os
import subprocess
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path

import numpy as np
import pytest

SUITE = Path(__file__).resolve().parent
REPO = SUITE.parent.parent
DATA = SUITE / "data"
sys.path.insert(0, str(SUITE / "tools"))

import make_rate_files as rf  # noqa: E402

PHRASE = "NOT ACTUAL DATA"
# SHA-256 of the real tables that were tracked until T169 (git show 0863c979:tests/yldot/data/<name>)
REAL = {
    "05ad12cf71c4ee4975d583db2fdc77ed52fcfa3cdac34642a0ac99848e8ddde3": "C_rates.adas",
    "67da65ac51f36527f6d894c0465612ae36741ce9e53229e10f502d1fcef3f4bb": "C_rates.strahl",
    "66014d055be5875c20ab497034d4aa645d08ec744a5647f19e29f4e644f28e5b": "ehr2.dat",
    "82a797555f0470483122d4c9a053bd250cbbb588f1958843a493c969a159a7db": "mist_c.dat",
    "3547f7d703dd90111094eda0cd9567146198de7d22e5b0a41b08bd4649f6b7cb": "mist_ne.dat",
}
RTOL = 2e-5  # the files hold six digits or more
RTOL_INEL = 6e-5  # carbmc.dat: five digits (1pe12.4)


# ---------------------------------------------------------------- the files as written


def test_files_are_the_generators():
    assert rf.check(DATA) == []


def test_check_finds_planted_defects(tmp_path):
    rf.write(tmp_path)
    (tmp_path / rf.README).write_text("x")
    assert rf.check(tmp_path) == []
    (tmp_path / "ehr2.dat").write_text((tmp_path / "ehr2.dat").read_text().replace("1", "2", 1))
    (tmp_path / "mist.dat").write_text("a table")
    (tmp_path / "nwfits").unlink()
    (tmp_path / rf.README).unlink()
    assert rf.check(tmp_path) == ["README.md: missing", "nwfits: missing",
                                  "mist.dat: not written by make_rate_files.py (real rate tables never go here)",
                                  "ehr2.dat: differs from what make_rate_files.py writes"]
    assert rf.main(["x", "check", str(tmp_path)]) == 1


def without_notice(text):
    """Whether a file's text lacks the notice on line 1 or 2, or on its last line."""
    lines = text.splitlines()
    return not (any(PHRASE in s for s in lines[:2]) and PHRASE in lines[-1])


@pytest.mark.parametrize("name", sorted(rf.FILES))
def test_notice(name):
    text = (DATA / name).read_text()
    assert not without_notice(text)
    lines = text.splitlines()
    assert without_notice("\n".join(lines[:-1]))  # the last line's notice alone is required too
    assert without_notice("\n".join([s.replace(PHRASE, "") for s in lines[:2]] + lines[2:]))


def test_readme_says_so():
    assert PHRASE in (DATA / rf.README).read_text().splitlines()[0]


# ---------------------------------------------------------------- no real table


def members(name, data):
    """(name, bytes) of a file and of what it holds, if it is gzip, bzip2 or xz data or a tar or zip archive."""
    yield name, data
    for unpack in (gzip.decompress, bz2.decompress, lzma.decompress):
        try:
            yield name + ":", unpack(data)
        except (OSError, EOFError, zlib.error, lzma.LZMAError, ValueError):
            continue
    try:
        if zipfile.is_zipfile(io.BytesIO(data)):
            z = zipfile.ZipFile(io.BytesIO(data))
            inner = [(n, z.read(n)) for n in z.namelist()]
        else:
            t = tarfile.open(fileobj=io.BytesIO(data))
            inner = [(m.name, t.extractfile(m).read()) for m in t.getmembers() if m.isfile()]
    except (tarfile.TarError, EOFError, OSError):
        return
    for n, b in inner:
        yield "{}:{}".format(name, n), b


def real_tables(paths, root):
    """The known real tables among the files, archives unpacked in memory."""
    archives = (".tar", ".tgz", ".gz", ".bz2", ".xz", ".zip")
    out = []
    for p in paths:
        f = root / p
        if not f.is_file() or f.is_symlink():
            continue
        data = f.read_bytes()
        for name, b in members(p, data) if p.endswith(archives) else [(p, data)]:
            real = REAL.get(hashlib.sha256(b).hexdigest())
            if real:
                out.append("{} is {}".format(name, real))
    return out


def test_no_real_table_is_tracked():
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, text=True, check=True)
    paths = [p for p in tracked.stdout.split("\0") if p]
    assert "tests/yldot/data/ehr2.dat" in paths
    assert real_tables(paths, REPO) == []


def test_real_tables_are_found(tmp_path, monkeypatch):
    table = b"a real table"
    monkeypatch.setitem(REAL, hashlib.sha256(table).hexdigest(), "planted")
    (tmp_path / "x.dat").write_bytes(table)
    (tmp_path / "y.dat").write_bytes(b"something else")
    with tarfile.open(tmp_path / "z.tar.gz", "w:gz") as t:
        t.add(tmp_path / "x.dat", arcname="d/x.dat")
    with zipfile.ZipFile(tmp_path / "z.zip", "w") as z:
        z.write(tmp_path / "x.dat", "x.dat")
    (tmp_path / "broken.gz").write_bytes(b"not an archive")
    for suffix, pack in (("gz", gzip.compress), ("bz2", bz2.compress), ("xz", lzma.compress)):
        (tmp_path / ("w." + suffix)).write_bytes(pack(table))
    paths = ["x.dat", "y.dat", "z.tar.gz", "z.zip", "w.gz", "w.bz2", "w.xz", "broken.gz", "gone.dat"]
    assert real_tables(paths, tmp_path) == [
        "x.dat is planted", "z.tar.gz:d/x.dat is planted", "z.zip:x.dat is planted", "w.gz: is planted",
        "w.bz2: is planted", "w.xz: is planted"]


# ---------------------------------------------------------------- read back through UEDGE

ISTABON = {"ehr1.dat": 8, "ehr2.dat": 10, "thin.dat": 11, "thickLyA.dat": 12, "thickAllLy.dat": 13, "ehrtau.dat": 14,
           "ehr5.dat": 17, "rates.adpak": 1, "rates.strahl": 2, "eh.dat": 3, "atmc.dat": 3, "nwfits": 4}
POPULATIONS = ["pne31", "pne32", "pne21", "pne22", "pne41", "pne42", "pne51", "pne52", "pne61", "pne62", "pne71",
               "pne72", "pne81", "pne82", "pne91", "pne92"]  # readehr2's order; readehr1 reads the first four
EV = 1.602e-19  # inelinput's
EV2 = 1.6022e-19  # readpost's: ev2 of api/api.v
READER = '''
import json, sys
import numpy as np
job = json.loads(sys.argv[1])
from uedge import aph, api, bbb, com
aph.aphdir = job["data"]
api.apidir = job["data"]
name, arrays = job["name"], job["arrays"]
if job["istabon"]:
    com.istabon = job["istabon"]
    aph.aphread()
    pkg = aph
elif job["mist"]:
    api.readpost(job["data"] + "/" + name)
    pkg = api
elif name == "carbmc.dat":  # inelinput is not callable from Python: ueinit calls it for ismctab = 1
    import os
    inelmc = os.path.join(os.getcwd(), name)
    os.chdir(job["family"])
    exec(compile(open("input.py").read(), "input.py", "exec"))
    bbb.ismctab = 1
    com.nz = job["nz"]
    api.inelmc[0] = inelmc
    bbb.allocate()
    from uedge.hdf5 import hdf5_restore
    hdf5_restore("reference_state.h5")
    bbb.ueinit()
    pkg = com
else:
    com.mcfilename[0] = name
    api.readmc(1, com.mcfilename)
    pkg = com
np.savez(job["out"], **{a: np.array(getattr(pkg, a)) for a in arrays})
'''


def expected(name):
    """{array: what the reader must return}: the generator's values in the reader's units and index order."""
    def tab(f, nt=60, nd=15, old=False, scale=1.0):
        return np.array(rf.grid(f, nt, nd, old, scale)).T

    rate, power, line = 1e-6, 1e-7, 1e-13  # cm^3 -> m^3, erg -> J, both (erg cm^3/s -> W m^3)
    if name in rf.EHR_SCALE:
        funcs = [(rf.ionization, rate), (rf.recombination, rate), (rf.loss_neutral, power), (rf.loss_continuum, power)]
        ntau, s = rf.NTAU if name == "ehrtau.dat" else 1, rf.EHR_SCALE[name]
        out = {a: np.stack([np.maximum(tab(f, scale=s * rf.tau_factor(r)), 1e-50) * u for r in range(ntau)], axis=2)
               for a, (f, u) in zip(("wsveh", "wsveh0", "welms1", "welms2"), funcs)}
        # one array per population table: the last optical depth read remains
        out.update({a: tab(rf.population(k), scale=s * rf.tau_factor(ntau - 1))
                    for k, a in enumerate(POPULATIONS[:rf.EHR_RATIOS[name]])})
        return out
    if name in ("nwfits", "eh.dat"):
        def t(f):
            return tab(f, scale=rf.NWFITS_SCALE) if name == "nwfits" else tab(f, 48, 11, True)
        out = {"wsveh": (np.maximum(t(rf.ionization), 1e-50) * rate)[:, :, None],
               "wsveh0": (np.maximum(t(rf.recombination), 1e-50) * rate)[:, :, None],
               "wlemiss": np.maximum(t(rf.line_emission), 1e-75) * line}
        if name == "eh.dat":
            out.update(welms=t(rf.mean_energy), pne3=t(rf.population(0)), pne2=t(rf.population(2)))
        return out
    if name == "atmc.dat":  # fifteen tables, the last one kept
        n = rf.ATMC_N
        return {"svphcx": np.array([[rf.atmc_value(rf.ATMC_TABLES - 1, i, j) * rate for j in range(n)]
                                    for i in range(n)])}
    if name in rf.BRAAMS:
        t, za2 = rf.BRAAMS[name]
        shape = (t.ns, t.nn + 1, t.nt + 1)
        out = {"lt": t.lt, "ln": t.ln, "za": range(t.ns), "zn": [t.zn] * t.ns}
        out.update({a: np.reshape(t.values(f), shape).transpose(2, 1, 0) for a, f in
                    (("lsa", t.ionization), ("lra", t.recombination), ("lqa", t.radiation), ("lcx", t.exchange))})
        return {("rt" if za2 else "ht") + a: np.array(list(v), float) for a, v in out.items()}
    if name in rf.MIST:
        m = rf.MIST[name]
        v = np.array([[[m.row(jt, jr, jn) for jn in range(m.nn)] for jr in range(m.nr)] for jt in range(m.nt)])
        return {"tdatm": v[..., 0] * EV2, "rdatm": v[..., 1], "ndatm": v[..., 2] * 1e6, "emdatm": v[..., 3] * 1e-6,
                "z1datm": v[..., 4], "z2datm": v[..., 5], "atn": np.array(m.atn), "atw": np.array(m.atw)}
    assert name == "carbmc.dat"
    c = rf.INEL
    ts = [c.temperature(i) for i in range(c.ntev)]
    units = (1.0, 1.0, EV / 1.5, 1.0)
    out = {a: np.array([[max(f(t, k), c.floor) * u for k in range(first, last + 1)] for t in ts])
           for a, (f, first, last), u in zip(("rsi", "rre", "rpwr", "rrcx"), c.tables(), units)}
    out["tevb"] = np.array(ts) * EV
    return out


RATES = ("wsveh", "wsveh0", "welms1", "welms2", "wlemiss", "lsa", "lra", "lqa", "lcx", "svphcx")


def same_rates(names):
    """(a, b, array) of every rate array that two files' readers return with the same values."""
    rates = {n: {k.removeprefix("ht").removeprefix("rt"): v for k, v in expected(n).items()} for n in names}
    return [(a, b, k) for i, a in enumerate(names) for b in names[i + 1:] for k in RATES
            if k in rates[a] and k in rates[b] and np.array_equal(rates[a][k], rates[b][k])]


def test_tables_differ():
    """No two files return the same rate table: a run that reads the wrong file must show it."""
    assert same_rates(sorted(set(rf.EHR_SCALE) | set(rf.BRAAMS) | {"nwfits", "eh.dat", "atmc.dat"})) == []


def test_same_rates_finds_a_copy(monkeypatch):
    monkeypatch.setitem(rf.BRAAMS, "rates.adpak", (rf.Braams(1), False))
    monkeypatch.setattr(rf, "NWFITS_SCALE", 1.0)
    assert same_rates(["b2frates", "ehr1.dat", "nwfits", "rates.adpak"]) == [
        ("b2frates", "rates.adpak", k) for k in ("lsa", "lra", "lqa", "lcx")] + [
        ("ehr1.dat", "nwfits", k) for k in ("wsveh", "wsveh0")]


def read_back(name, data, tmp_path):
    """(expected(name), {array: what UEDGE's reader returns}): a fresh process, HOME in tmp_path; carbmc.dat through
    d_c's deck."""
    want = expected(name)
    job = {"name": name, "data": ".", "arrays": sorted(want), "istabon": ISTABON.get(name, 0),
           "mist": name in rf.MIST, "nz": rf.INEL.nz,
           "family": str(SUITE / "families" / "d_c"), "out": str(tmp_path / "out.npz")}
    run = tmp_path / "run"  # holds links to the files: aphdir, apidir and the names are at most 120 characters
    run.mkdir()
    for f in data.iterdir():
        (run / f.name).symlink_to(f)
    p = subprocess.run([sys.executable, "-I", "-c", READER, json.dumps(job)], cwd=run, capture_output=True,
                       text=True, errors="replace", timeout=120,
                       env=dict(os.environ, HOME=str(tmp_path), UEDGE_BANNER="0", OMP_NUM_THREADS="1"))
    assert p.returncode == 0, p.stdout[-1500:] + p.stderr[-1500:]
    with np.load(tmp_path / "out.npz") as z:
        return want, {a: z[a] for a in z.files}


def differences(want, got, rtol=RTOL):
    """{array: largest |got - want| relative to |want|} over rtol (1e-30 absolute where want is 0)."""
    out = {}
    for a, w in want.items():
        assert got[a].shape == w.shape, (a, got[a].shape, w.shape)
        d = np.abs(got[a] - w)
        rel = float(np.max(np.where(w == 0, np.where(d > 1e-30, np.inf, 0.0), d / np.where(w == 0, 1.0, np.abs(w)))))
        if not rel < rtol:
            out[a] = rel
    return out


@pytest.mark.parametrize("name", sorted(rf.FILES))
def test_read_back(name, tmp_path):
    want, got = read_back(name, DATA, tmp_path)
    assert differences(want, got, RTOL_INEL if name == "carbmc.dat" else RTOL) == {}


def test_read_back_reads_the_given_carbmc(tmp_path):
    """carbmc.dat goes through d_c's deck; a changed copy must still be the file that is read."""
    d = tmp_path / "data"
    rf.write(d)
    lines = (d / "carbmc.dat").read_text().splitlines()
    i = len(lines) - 2  # the last record of the last table (rrcx), before the closing notice
    assert lines[i].count("E") == rf.INEL.nz + 1
    lines[i] = lines[i][:-12] + "%12.4E" % (2 * float(lines[i][-12:]))
    (d / "carbmc.dat").write_text("\n".join(lines) + "\n")
    want, got = read_back("carbmc.dat", d, tmp_path)
    assert set(differences(want, got, RTOL_INEL)) == {"rrcx"}


def test_read_back_finds_a_wrong_value(tmp_path):
    """One digit changed in the last table of a file shows in that array only."""
    d = tmp_path / "data"
    rf.write(d)
    lines = (d / "thin.dat").read_text().splitlines()
    assert lines[-3].count("E") == 6  # the last record of the last table, before its blank record and the notice
    old = lines[-3][1:3]
    lines[-3] = lines[-3].replace(old, {"9": "8"}.get(old[0], "9") + old[1], 1)
    (d / "thin.dat").write_text("\n".join(lines) + "\n")
    want, got = read_back("thin.dat", d, tmp_path)
    assert set(differences(want, got)) == {"pne92"}
