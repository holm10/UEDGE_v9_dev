"""The synthetic rate files of the yldot suite and the OpenMP reproducer (tests/yldot/data; tracker T169).

Usage:
    python make_rate_files.py write [DIR]    write every file into DIR (default tests/yldot/data)
    python make_rate_files.py check [DIR]    DIR holds exactly the files this tool writes, byte for byte, plus README.md
                                             (exit 1 names each missing, extra or different file)

NONE OF THESE FILES HOLDS ACTUAL DATA. Every number comes from the closed formulas below, invented for software tests:
positive, smooth, different from table to table, and NOT physical. This program reads no table, and no value was taken
from, fitted to or scaled to a measured, calculated or published one (owner, 2026-11-23, T169: real rate tables are not
publicly shareable). The Te-ne grids of the aphread files and the 101 temperatures of carbmc.dat are fixed by the
Fortran; the other grids are arbitrary. Never replace a file here by a real table, and never tune a formula or a grid
to one. A case run with these files need not converge.

Every file says so on its first or second line and on its last line. A format without a header record (nwfits, eh.dat,
carbmc.dat) carries the notice on line 1, after the columns that are read.

The layouts are those of UEDGE's readers:
    ehr1, ehr2, ehrtau                 aph/aphread.m readehr1 (8 tables; ehrtau: 30 optical depths)
    thin, thickLyA, thickAllLy, ehr5   aph/aphread.m readehr2 (20 tables)
    nwfits                             aph/aphread.m readnw
    eh.dat, atmc.dat                   aph/aphread.m readeh, readatmc
    rates.adpak, rates.strahl          aph/aphread.m readrt
    b2frates, C_rates.synthetic        api/fimp.m readmc (the pre-2012 format; hydrogen, carbon)
    mist_c.synthetic, mist_ne.synthetic   api/apip93.m readpost
    carbmc.dat                         api/inelrates.m inelinput (impflag = 2)
aphread's names are fixed in the Fortran; the decks choose the others, which say .synthetic.

Values are rounded to at most SIG significant digits before they are formatted, so that the last bit of a platform's
math library does not show (macOS arm64 and Linux amd64 write the same bytes; probed, T169). Standard library only.
"""
import argparse
import math
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
README = "README.md"
SIG = 9
NOTICE = "*** SYNTHETIC TEST FILE - NOT ACTUAL DATA - DO NOT USE FOR PHYSICS ***"
LAST = ("SYNTHETIC TEST FILE - NOT ACTUAL DATA. Invented values from closed formulas, for UEDGE software tests only; "
        "no measured, calculated or published rate is in it. Do not use for physics.")


# ---------------------------------------------------------------- formatting


def num(x):
    """x rounded to SIG significant digits."""
    return float("%.*E" % (SIG - 1, x))


def e12(x):
    """One value as format (1x,e12.5) reads it, clamped so that the exponent keeps two digits."""
    return "%13.5E" % max(min(x, 9e90), 1e-90)


def blocks(values, n):
    """Values 6 per line with a blank record after each n of them (format n(6(1x,e12.5)/))."""
    out = []
    for b in range(0, len(values), n):
        part = values[b:b + n]
        out += ["".join(e12(v) for v in part[i:i + 6]) for i in range(0, len(part), 6)] + [""]
    return out


def text(lines, column=None):
    """The file's text: the lines and LAST. column: the notice goes on line 1 after the data, from this column on."""
    if column is not None:
        lines = [lines[0].ljust(column) + "   " + NOTICE] + lines[1:]
    return "\n".join(lines + [LAST]) + "\n"


# ---------------------------------------------------------------- hydrogen: Te-ne tables (DEGAS layouts)


def te(i, old=False):
    """Te in eV of column i (aph setauxvar's grid; old: the eh.dat and atmc.dat grid)."""
    return 10 ** (0.1 * i) if old else 10 ** (-1.2 + 0.1 * i)


def log_ne(j):
    """log10 of the density in cm^-3 of row j."""
    return 10.0 + 0.5 * j


def ionization(t, ln):
    x = t / 10.0
    return 1e-8 * math.exp(-1 / x) * math.sqrt(x) / (1 + x) * (1.2 + 0.4 * math.tanh((ln - 13) / 2))


def recombination(t, ln):
    return 2e-13 / (1 + t) ** 0.7 * (1 + 10 ** (0.35 * (ln - 13)))


def loss_neutral(t, ln):
    return 1e-11 * 10 ** ln * ionization(t, ln) * (1.5 + 0.2 * math.sin(math.log(t)))


def loss_continuum(t, ln):
    return 1e-11 * 10 ** ln * recombination(t, ln) * (1.0 + 0.1 * math.cos(math.log(t)))


def line_emission(t, ln):
    return 1.6e-12 * 12 * ionization(t, ln)


def mean_energy(t, ln):
    return 25 + t ** 0.3


def population(k):
    """The population ratio of excited table k."""
    def f(t, ln):
        return 10 ** (-2 - 0.25 * k + 0.2 * (ln - 13)) * t / (t + 3.0 + 0.5 * k)
    return f


def grid(f, nt, nd, old=False, scale=1.0):
    """f on the grid: a list of nd rows (density) of nt values (Te)."""
    return [[scale * f(te(i, old), log_ne(j)) for i in range(nt)] for j in range(nd)]


EHR_SCALE = {"ehr1.dat": 1.0, "ehr2.dat": 1.05, "thin.dat": 1.1, "thickLyA.dat": 1.15, "thickAllLy.dat": 1.2,
             "ehr5.dat": 1.25, "ehrtau.dat": 1.4}
EHR_RATIOS = {"ehr1.dat": 4, "ehr2.dat": 4, "ehrtau.dat": 4, "thin.dat": 16, "thickLyA.dat": 16, "thickAllLy.dat": 16,
              "ehr5.dat": 16}
NTAU = 30


def tau_factor(r):
    """The factor of optical-depth block r (0-based) of ehrtau.dat."""
    return 1 - 0.02 * r


def ehr(name):
    """readehr1 (4 rate and 4 population tables) and readehr2 (4 and 16): 60 Te by 15 densities."""
    ntau = NTAU if name == "ehrtau.dat" else 1
    funcs = [ionization, recombination, loss_neutral, loss_continuum] + [population(k) for k in range(EHR_RATIOS[name])]
    out = []
    for r in range(ntau):
        if ntau > 1:
            out.append(" %s tau %d" % (NOTICE, r + 1))
        for n, f in enumerate(funcs):
            out.append(" %s table %d" % (NOTICE, n + 1))
            for j, row in enumerate(grid(f, 60, 15, scale=EHR_SCALE[name] * tau_factor(r))):
                out.append(" jn = %d" % (j + 1))
                out += blocks(row, 60)
    return text(out)


def degas(funcs, nt, nd, old=False):
    out = []
    for f in funcs:
        for row in grid(f, nt, nd, old):
            out += blocks(row, nt)
    return text(out, column=78)


ATMC_N, ATMC_TABLES = 48, 15


def atmc_value(k, i, j):
    """Table k (0-based) at projectile energy i and temperature j."""
    return (1 + 0.01 * k) * 1e-8 * (1 + te(i, True) + te(j, True)) ** 0.3


def atmc():
    out = []
    for k in range(ATMC_TABLES):
        out.append(" %s table %d" % (NOTICE, k + 1))  # the leading / of format 9015
        for j in range(ATMC_N):
            out += blocks([atmc_value(k, i, j) for i in range(ATMC_N)], ATMC_N)
    return text(out)


# ---------------------------------------------------------------- the Braams layout (readrt, readmc)


class Braams:
    """A table in B. Braams' layout: species zn+1 charge states 0..zn, nt+1 temperatures, nn+1 densities."""

    def __init__(self, zn, tmin=0.17, tmax=1.3e4, nt=31, nn=11, nmin=3e15, nmax=2e22):
        self.zn, self.nt, self.nn, self.ns = zn, nt, nn, zn + 1
        self.lt = [num(math.log(tmin) + i * math.log(tmax / tmin) / nt) for i in range(nt + 1)]
        self.ln = [num(math.log(nmin) + j * math.log(nmax / nmin) / nn) for j in range(nn + 1)]

    def ionization(self, t, n, k):
        """ln of the rate in m^3/s (as all five)."""
        return math.log(1e-13 / (k + 1)) - 10.0 * (k + 1) ** 1.6 / t + 0.02 * (n - 43) if k < self.zn else -120.0

    def recombination(self, t, n, k):
        return math.log(3e-19 * k ** 2) - 0.6 * math.log(1 + t) + 0.03 * (n - 43) if k > 0 else -120.0

    def radiation(self, t, n, k):
        return (math.log(2e-13 * (self.zn + 1 - k) / (k + 1)) - 4.0 * (k + 1) / t - 0.2 * math.log(1 + t)
                + 0.01 * (n - 43))

    def exchange(self, t, n, k):
        return math.log(1e-15 * k) + 0.2 * math.log(1 + t) if k > 0 else -120.0

    def values(self, f):
        """f over (charge state, density, temperature), the temperature fastest, as the readers loop."""
        return [num(f(math.exp(t), n, k)) for k in range(self.ns) for n in self.ln for t in self.lt]

    def text(self, za2):
        """za2: readmc's layout, which has the squared charges; readrt's has not."""
        def head(kind, n, name):
            return "%-8s%-8s%12d    %-32s" % ("*cf:", kind, n, name)

        out = [head("char", 120, "SYNTHETIC - NOT ACTUAL DATA"), " %s zn=%d" % (NOTICE, self.zn),
               head("int", 3, "rtnt,rtnn,rtns"), "%12d%12d%12d" % (self.nt, self.nn, self.ns)]
        states = list(range(self.ns))
        sections = [("rtza", states), ("rtzn", [self.zn] * self.ns)]
        if za2:
            sections.append(("rtza2", [k * k for k in states]))
        sections += [("rtt", [num(math.exp(t)) for t in self.lt]), ("rtn", [num(math.exp(n)) for n in self.ln]),
                     ("rtlt", self.lt), ("rtln", self.ln), ("rtlsa", self.values(self.ionization)),
                     ("rtlra", self.values(self.recombination)), ("rtlqa", self.values(self.radiation)),
                     ("rtlcx", self.values(self.exchange))]
        for name, v in sections:
            out.append(head("real", len(v), name))
            out += ["".join("%22.13E" % x for x in v[i:i + 5]) for i in range(0, len(v), 5)]
        return text(out)


BRAAMS = {"rates.adpak": (Braams(1), False), "rates.strahl": (Braams(1, tmin=0.3), False),
          "b2frates": (Braams(1), True), "C_rates.synthetic": (Braams(6), True)}


# ---------------------------------------------------------------- the Post '93 layout (readpost)


class Mist:
    """atn, atw: atomic number and weight. Values over (n*tau, ng/ne, Te), Te fastest, as readpost1 loops."""
    nt, nr, nn = 13, 5, 7

    def __init__(self, atn, atw):
        self.atn, self.atw = atn, atw

    def row(self, jt, jr, jn):
        """Te [eV], ng/ne, n*tau [s/cm^3], emissivity [W cm^3], <Z>, <Z^2>."""
        t, ratio, ntau = 10 ** (0.15 + 3.7 * jt / (self.nt - 1)), 10 ** (-6.3 + 1.15 * jr), 10 ** (7.4 + 1.1 * jn)
        z = self.atn * t / (t + 20.0 * self.atn)
        emissivity = (1e-25 * self.atn * math.exp(-((math.log10(t) - 1.2) / 0.9) ** 2) * (1 + 50 * ratio)
                      * (1 + 0.1 * (self.nn - jn)))
        return t, ratio, ntau, emissivity, z, z * z * 1.05

    def text(self):
        out = [" " + NOTICE, " " + LAST, " te, ng/ne, n*tau, emissivity, <z>, <z^2>; all invented", " " + NOTICE]
        out += [" %2d" % v for v in (self.atn, self.atw, self.nt, self.nr, self.nn)] + [""]
        out += ["".join(e12(v) for v in self.row(jt, jr, jn))
                for jn in range(self.nn) for jr in range(self.nr) for jt in range(self.nt)]
        return text(out)


MIST = {"mist_c.synthetic": Mist(6, 12), "mist_ne.synthetic": Mist(10, 20)}


# ---------------------------------------------------------------- the INEL multi-charge layout (inelinput)


class Inel:
    """impflag = 2: per temperature the rates of the charge states, formats 7(1pe12.4) and 8(1pe12.4)."""
    nz, ntev, floor = 6, 101, 1e-60  # floor: the exponent keeps two digits

    def temperature(self, i):
        return 10 ** (-0.3 + 4.5 * i / self.ntev)

    def ionization(self, t, k):
        return 1e-14 / (k + 1) * math.exp(-10.0 * (k + 1) ** 1.6 / t)

    def recombination(self, t, k):
        return 3e-19 * k * k / (1 + t) ** 0.6

    def radiation(self, t, k):
        return 2e-14 * (self.nz + 1 - k) / (k + 1) * math.exp(-4.0 * (k + 1) / t)

    def exchange(self, t, k):
        return 1e-15 * k * (1 + t) ** 0.2

    def tables(self):
        """(function, first charge state, last charge state) in the order of the file."""
        return [(self.ionization, 0, self.nz - 1), (self.recombination, 1, self.nz), (self.radiation, 0, self.nz),
                (self.exchange, 1, self.nz)]

    def text(self):
        out = []
        for f, first, last in self.tables():
            for i in range(self.ntev):
                t = self.temperature(i)
                rates = [f(t, k) for k in range(first, last + 1)]
                out.append("".join("%12.4E" % max(v, self.floor) for v in [t] + rates))
        return text(out, column=84)


INEL = Inel()


# ---------------------------------------------------------------- the files


FILES = {name: (lambda name=name: ehr(name)) for name in EHR_SCALE}
FILES.update({name: (lambda t=t, za2=za2: t.text(za2)) for name, (t, za2) in BRAAMS.items()})
FILES.update({name: t.text for name, t in MIST.items()})
FILES.update({
    "nwfits": lambda: degas([ionization, recombination, line_emission], 60, 15),
    "eh.dat": lambda: degas([ionization, recombination, line_emission, mean_energy, population(0), population(2)], 48,
                            11, old=True),
    "atmc.dat": atmc,
    "carbmc.dat": INEL.text,
})


def write(d):
    d.mkdir(parents=True, exist_ok=True)
    for name, f in sorted(FILES.items()):
        (d / name).write_text(f(), newline="\n")


def check(d):
    """The problems of DIR: files missing, extra or different from what this tool writes ([]: none)."""
    present = {p.name for p in d.iterdir()} if d.is_dir() else set()
    out = ["{}: missing".format(n) for n in sorted((set(FILES) | {README}) - present)]
    out += ["{}: not written by make_rate_files.py (real rate tables never go here)".format(n)
            for n in sorted(present - set(FILES) - {README})]
    for name in sorted(set(FILES) & present):
        if (d / name).read_bytes() != FILES[name]().encode():
            out.append("{}: differs from what make_rate_files.py writes".format(name))
    return out


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("cmd", choices=("write", "check"))
    p.add_argument("dir", nargs="?", type=Path, default=DATA)
    args = p.parse_args(argv[1:])
    if args.cmd == "write":
        write(args.dir)
        print("wrote {} files to {}".format(len(FILES), args.dir))
        return 0
    problems = check(args.dir)
    for s in problems:
        print(s)
    if not problems:
        print("{}: {} files as written by make_rate_files.py".format(args.dir, len(FILES)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
