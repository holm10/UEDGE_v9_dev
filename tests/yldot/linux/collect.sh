#!/bin/bash
# The Linux side of tools/measure_roundoff.py (AIUE-87): builds UEDGE --serial from a git archive of COMMIT inside
# the pinned image and collects the families under the label linux-serial. From the worktree root, on the host:
#
#   docker build --platform linux/amd64 -t yldot-linux:24.04 tests/yldot/linux
#   git archive --format=tar -o OUT/src.tar COMMIT
#   docker run --rm --platform linux/amd64 -v "$PWD/tests:/tests:ro" -v OUT:/out yldot-linux:24.04 \
#       /opt/collect.sh COMMIT IMAGE_ID d_c d_mols d_only ortho slab_phi
#
# IMAGE_ID is `docker image inspect --format '{{.Id}}' yldot-linux:24.04`. The tool and the families come from the
# mounted tests/ (read-only); UEDGE comes from the archive, whose pax header must name COMMIT. Writes
# OUT/linux-build.log, OUT/linux-serial.json (the build record) and OUT/collections/linux-serial/*.pkl.
set -euo pipefail
COMMIT=$1
IMAGE=$2
shift 2
archived=$(python3 -c 'import sys, tarfile; print(tarfile.open(sys.argv[1]).pax_headers.get("comment", ""))' /out/src.tar)
if [ "$archived" != "$COMMIT" ]; then
  echo "refused: /out/src.tar is an archive of '$archived', not $COMMIT" >&2
  exit 2
fi
mkdir -p /work/src
tar -xf /out/src.tar -C /work/src
cd /work/src
PATH=/opt/venv/bin:$PATH pip install -v --no-build-isolation --no-deps . -C "--build-option=--serial" \
  > /out/linux-build.log 2>&1
cd /tmp
python3 - "$COMMIT" "$IMAGE" > /out/linux-serial.json <<'EOF'
import json, platform, subprocess, sys
gfortran = subprocess.run(["gfortran", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
# multi-arch packages (libgfortran5, libgomp1, libc6) are listed as <name>:amd64
dpkg = dict((l.split("\t", 1)[0].split(":")[0], l.split("\t", 1)[1])
            for l in open("/opt/dpkg-versions.txt").read().splitlines() if "\t" in l)
os_release = dict(l.split("=", 1) for l in open("/etc/os-release").read().splitlines() if "=" in l)
print(json.dumps({
    "label": "linux-serial", "commit": sys.argv[1], "options": "--serial (-O3)", "compiler": gfortran,
    "platform": "{} {} (docker linux/amd64)".format(os_release["PRETTY_NAME"].strip('"'), platform.machine()),
    "image": "ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55",
    "image_id": sys.argv[2], "python": platform.python_version(),
    "pins": open("/opt/pip-freeze.txt").read().split(),
    "packages": {p: dpkg.get(p, "") for p in ("gfortran-13", "gcc-13", "libgfortran5", "libgomp1", "binutils",
                                               "python3.12", "libc6")},
}, indent=1))
EOF
/opt/venv/bin/python /tests/yldot/tools/measure_roundoff.py collect "$@" --label linux-serial \
  --out /out/collections --build /out/linux-serial.json
