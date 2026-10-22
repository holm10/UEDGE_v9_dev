#!/bin/bash
# The Linux side of tools/make_references.py generate (AIUE-88): builds UEDGE --serial from a git archive of COMMIT
# inside the pinned image and writes the families' reference files. make_references.py runs it from the read-only
# mount, so the image (built for collect.sh, AIUE-87) is used as it is:
#
#   docker run --rm --platform linux/amd64 -v "$PWD/tests:/tests:ro" -v OUT:/out yldot-linux:24.04 \
#       bash /tests/yldot/linux/generate.sh COMMIT RUNNER_IMAGE d_c d_mols d_only ortho slab_phi [_child options]
#
# Arguments after RUNNER_IMAGE (the families, then make_references.py's _child options such as --sweep none,
# --only VAR ... or --full, AIUE-94) go to the child unchanged.
# RUNNER_IMAGE is the manifest's provenance runner_image ("yldot-linux:24.04 <image id> (<base digest>)"). The archive
# OUT/src.tar must name COMMIT in its pax header. Writes OUT/build.log, OUT/build.json (the build record) and
# OUT/references/<family>.{h5,json}.
set -euo pipefail
COMMIT=$1
RUNNER_IMAGE=$2
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
  > /out/build.log 2>&1
cd /tmp
python3 - "$COMMIT" "$RUNNER_IMAGE" > /out/build.json <<'EOF'
import json, subprocess, sys
gfortran = subprocess.run(["gfortran", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
print(json.dumps({"commit": sys.argv[1], "compiler": gfortran, "runner_image": sys.argv[2]}, indent=1))
EOF
/opt/venv/bin/python /tests/yldot/tools/make_references.py _child "$@" --out /out/references --build /out/build.json
