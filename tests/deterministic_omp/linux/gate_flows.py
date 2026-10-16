"""Apply the AIUE-56 C1 gate (AIUE-56-c1-gate.py, unchanged) to the jac groups of AIUE-52 flow directories.

Usage: python gate_flows.py GATESCRIPT LINKROOT HARNESSDIR NAME=FLOWDIR [NAME=FLOWDIR ...]
GATESCRIPT: AIUE-56-c1-gate.py from bugfix/v9-AIUE-56-omp-jacobian-fix (1553e75); it is no longer on the branch, it is
kept in the tag archive/AIUE-8-docs (`git ls-tree -r --name-only archive/AIUE-8-docs | grep c1-gate`, then
`git show archive/AIUE-8-docs:<path> > AIUE-56-c1-gate.py`). On builds with the AIUE-47 capture hook pass
tests/deterministic_omp/ci/jac_bound.py instead (see linux/README.md).
For every <cfg>/jac_t<N> group of each flow it makes LINKROOT/<NAME>__<cfg>__jac_t<N>/{serial,run*} as symlinks
(the check layout the gate script reads) and runs the gate on all of them in one call (output on stdout).
"""
import os
import subprocess
import sys

gate, root, harness = sys.argv[1], sys.argv[2], sys.argv[3]
dirs = []
for item in sys.argv[4:]:
    name, flow = item.split("=", 1)
    flow = os.path.abspath(flow)
    for cfg in sorted(os.listdir(flow)):
        cdir = os.path.join(flow, cfg)
        if not os.path.isdir(os.path.join(cdir, "serial")):
            continue
        for grp in sorted(os.listdir(cdir)):
            if not grp.startswith("jac_t"):
                continue
            link = os.path.join(root, "{}__{}__{}".format(name, cfg, grp))
            os.makedirs(link)
            os.symlink(os.path.join(cdir, "serial"), os.path.join(link, "serial"))
            for r in sorted(os.listdir(os.path.join(cdir, grp))):
                if r.startswith("run"):
                    os.symlink(os.path.join(cdir, grp, r), os.path.join(link, r))
            dirs.append(link)
sys.exit(subprocess.call([sys.executable, gate, "--harness", harness] + dirs))
