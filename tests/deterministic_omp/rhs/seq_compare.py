"""AIUE-58: compare rhs_sequence.py runs with a reference run.
   python seq_compare.py <ref_rundir> <rundir> [<rundir> ...]
Prints, per run: iterm/ijactot per exmain, whether yl after each exmain is bitwise equal to the reference
(else the number of differing entries and the max relative difference), and the printed fnrm sequences
of the caller's two exmain calls (the deck's populate exmain is dropped).
"""
import json
import os
import re
import sys

import numpy as np

ITER_RE = re.compile(r"(OMP )?iter=\s*(\d+)\s+fnrm=\s*(\S+)\s+nfe=\s*(\d+)")


def fnrm_blocks(rundir):
    with open(os.path.join(rundir, "run.log"), "rb") as f:
        text = f.read().replace(b"\x00", b"").decode(errors="replace")
    blocks, cur = [], []
    for line in text.splitlines():
        m = ITER_RE.search(line)
        if not m:
            continue
        if int(m.group(2)) == 0 and cur:
            blocks.append(cur)
            cur = []
        cur.append(("O" if m.group(1) else "") + m.group(3))
    if cur:
        blocks.append(cur)
    return blocks[1:]  # drop the deck's populate exmain


def load(rundir):
    meta = json.load(open(os.path.join(rundir, "seq.json")))
    arr = dict(np.load(os.path.join(rundir, "seq.npz"))) if os.path.exists(os.path.join(rundir, "seq.npz")) else {}
    return meta, arr


def main(ref, runs):
    rmeta, rarr = load(ref)
    rblocks = fnrm_blocks(ref)
    print("REF", ref, [(e["iterm"], e["ijactot"]) for e in rmeta["exmain"]], rmeta.get("error", "")[-300:])
    for b in rblocks:
        print("   fnrm", " ".join(b))
    for rd in runs:
        meta, arr = load(rd)
        print("RUN", rd, [(e["iterm"], e["ijactot"]) for e in meta["exmain"]], meta.get("error", "")[-300:])
        for k in ("yl1", "yl2"):
            if k in arr and k in rarr:
                a, b = arr[k], rarr[k]
                d = a != b
                rel = np.abs(a - b) / np.maximum(np.abs(b), 1e-300)
                print("   {}: {}".format(k, "bitwise equal" if not d.any() else
                                         "{} differ, max rel {:.3g}".format(int(d.sum()), rel.max())))
        blocks = fnrm_blocks(rd)
        for i, b in enumerate(blocks):
            same = i < len(rblocks) and [x.lstrip("O") for x in b] == [x.lstrip("O") for x in rblocks[i]]
            print("   fnrm{} {}".format(" (= ref)" if same else "", " ".join(b)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
