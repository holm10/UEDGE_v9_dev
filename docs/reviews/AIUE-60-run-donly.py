"""Run upstream pytests D_only, one process per test file (pytest-isolate not installed), with a given venv.
Usage: python3 run_donly.py VENV_PYTHON OUT.json [JOBS]. Records the pytest summary line (or 'no summary') per file."""
import concurrent.futures as cf
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

py, out = sys.argv[1], sys.argv[2]
jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 2
root = "/Users/holma/Documents/uedge/src/uedge-pytests/pytests/unittests/D_only"
files = sorted(glob.glob(os.path.join(root, "**", "test*.py"), recursive=True))


def run(f):
    home = tempfile.mkdtemp(prefix="donly_home_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OMP_", "PYTHON"))}
    env.update({"HOME": home, "OMP_NUM_THREADS": "1"})
    try:
        r = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", os.path.basename(f)],
                           cwd=os.path.dirname(f), env=env, capture_output=True, timeout=3600)
        text = r.stdout.decode(errors="replace").replace("\x00", "")
    except subprocess.TimeoutExpired:
        return os.path.relpath(f, root), "timeout"
    m = re.findall(r"^=*\s*(\d+ (?:passed|failed|error)[^=\n]*?)\s*=*\s*$", text, re.M)
    return os.path.relpath(f, root), (m[-1] if m else "no summary (exit {})".format(r.returncode))


with cf.ThreadPoolExecutor(jobs) as ex:
    res = dict(ex.map(run, files))
json.dump(res, open(out, "w"), indent=1, sort_keys=True)
summ = {}
for v in res.values():
    k = "pass" if ("passed" in v and "failed" not in v and "error" not in v) else ("no summary" if v.startswith("no summary") else "fail")
    summ[k] = summ.get(k, 0) + 1
print(len(res), "files", summ)
