"""Run one RunSpec in a fresh process and load what it recorded.

Each run gets its own directory holding a copy of tests/deterministic_omp/case, an empty
HOME (so no ~/.uedgerc.py), pinned OpenMP settings, and `python -I` (no PYTHON* variables,
script folder not on sys.path). The rate files come from UEDGE_OMP_RATES_DIR, defaulting
to the copy tracked in builder/test/Forthon_cases/Forthon_case5.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CASE_DIR = os.path.normpath(os.path.join(HERE, "..", "case"))
REPO_DIR = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
DEFAULT_RATES = os.path.join(REPO_DIR, "builder", "test", "Forthon_cases", "Forthon_case5")
CASE_FILES = ["input_mod4.py", "b0p1.hdf5", "gridue.hdf5", "save_input_mod4.h5", "mist.dat"]

# nksol prints "iter=" (serial RHS) or "OMP iter=" (parallel RHS), see bbb/pandf.m PandfRHS_interface
ITER_RE = re.compile(r"(OMP )?iter=\s*(\d+)\s+fnrm=\s*(\S+)\s+nfe=\s*(\d+)")


class HarnessError(Exception):
    """The harness could not produce a result (exit code 2), as opposed to a mismatch."""


class Record:
    """What one run produced: meta (record.json) and arrays (record.npz)."""

    def __init__(self, rundir):
        self.rundir = rundir
        with open(os.path.join(rundir, "record.json")) as f:
            self.meta = json.load(f)
        if "error" in self.meta:
            raise HarnessError("run in {} failed:\n{}".format(rundir, self.meta["error"]))
        with np.load(os.path.join(rundir, "record.npz")) as data:
            self.arrays = {k: data[k] for k in data.files}

    @property
    def label(self):
        return self.meta.get("label", os.path.basename(self.rundir))


def parse_iterations(log_text):
    """The fnrm sequence nksol printed for the caller's exmain (the deck's populate exmain,
    which prints the first block, is dropped). Returns [{"iter", "fnrm_printed", "nfe", "omp"}]."""
    blocks, current = [], []
    for line in log_text.splitlines():
        m = ITER_RE.search(line)
        if not m:
            continue
        omp, it, fnrm, nfe = m.groups()
        if int(it) == 0 and current:
            blocks.append(current)
            current = []
        current.append({"iter": int(it), "fnrm_printed": fnrm, "nfe": int(nfe), "omp": bool(omp)})
    if current:
        blocks.append(current)
    if len(blocks) < 2:
        raise HarnessError("expected the deck's and the caller's nksol output, found {} block(s)".format(len(blocks)))
    return blocks[-1]


def prepare_rundir(rundir):
    if os.path.exists(rundir):
        raise HarnessError("run directory {} already exists".format(rundir))
    os.makedirs(rundir)
    for name in CASE_FILES:
        src = os.path.join(CASE_DIR, name)
        if not os.path.exists(src):
            raise HarnessError("case file missing: {}".format(src))
        shutil.copy2(src, rundir)


def run_spec(spec, rundir, python=None, rates_dir=None, timeout=3600):
    """Run `spec` (config.RunSpec) in a new directory `rundir` with interpreter `python`
    (default: the current one). Returns a Record; raises HarnessError on failure."""
    spec.validate()
    python = python or sys.executable
    rates_dir = rates_dir or os.environ.get("UEDGE_OMP_RATES_DIR") or DEFAULT_RATES
    prepare_rundir(rundir)
    home = os.path.join(rundir, "home")
    os.makedirs(home)
    with open(os.path.join(rundir, "spec.json"), "w") as f:
        f.write(spec.to_json())

    env = {k: v for k, v in os.environ.items() if not k.startswith(("OMP_", "GOMP_", "KMP_", "PYTHON"))}
    env.update({
        "HOME": home,
        "UEDGE_OMP_RATES_DIR": rates_dir,
        "OMP_NUM_THREADS": str(spec.threads),
        "OMP_STACKSIZE": spec.omp_stacksize,
    })
    cmd = [python, "-I", os.path.join(HERE, "worker.py"), os.path.join(rundir, "spec.json")]
    start = time.time()
    with open(os.path.join(rundir, "run.log"), "wb") as log:
        try:
            proc = subprocess.run(cmd, cwd=rundir, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise HarnessError("run in {} timed out after {} s".format(rundir, timeout))
    elapsed = time.time() - start
    if not os.path.exists(os.path.join(rundir, "record.json")):
        raise HarnessError("run in {} exited with {} and wrote no record (see run.log)".format(rundir, proc.returncode))
    record = Record(rundir)
    if proc.returncode != 0:
        raise HarnessError("run in {} exited with {}".format(rundir, proc.returncode))
    with open(os.path.join(rundir, "run.log"), "rb") as f:
        text = f.read().replace(b"\x00", b"").decode(errors="replace")  # the Fortran output has NULs
    record.meta["iterations"] = parse_iterations(text)
    record.meta["elapsed_s"] = round(elapsed, 2)
    record.meta["label"] = spec.label()
    with open(os.path.join(rundir, "record.json"), "w") as f:
        json.dump(record.meta, f, indent=1, sort_keys=True)
    return record
