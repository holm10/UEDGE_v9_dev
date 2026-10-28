#!/bin/bash
# The Linux side of tools/make_references.py generate (AIUE-88): builds UEDGE --serial from a git archive of COMMIT
# inside the pinned image and writes the families' reference files. make_references.py runs it from the read-only
# mount, so the image (built for collect.sh, AIUE-87) is used as it is:
#
#   docker run --rm --platform linux/amd64 -v "$PWD/tests:/tests:ro" -v OUT:/out yldot-linux:24.04 \
#       bash /tests/yldot/linux/generate.sh COMMIT RUNNER_IMAGE d_c d_mols d_only ortho slab_phi [_child options]
#
# Arguments after RUNNER_IMAGE (the families, then make_references.py's _child options such as --sweep none,
# --only VAR ..., --full, --prune or --rename OLD=NEW ..., AIUE-94, AIUE-95) go to the child unchanged, except
# --no-audit. Unless --no-audit is given, it first builds the archive --serial --checkbounds in /work/src-audit and
# runs the audit there (_child --audit-only, OUT/audit/; PRD section 4, AIUE-95), then reinstalls the serial build,
# whose child reads OUT/audit/<family>.audit.json (_child --audit).
# RUNNER_IMAGE is the manifest's provenance runner_image ("yldot-linux:24.04 <image id> (<base digest>)"). The archive
# OUT/src.tar must name COMMIT in its pax header. Writes OUT/build.log, OUT/build.json (the build record) and
# OUT/references/<family>.{h5,json}; with the audit also OUT/build-audit.log and OUT/audit/.
set -euo pipefail
COMMIT=$1
RUNNER_IMAGE=$2
shift 2
audit=1
args=()
for a in "$@"; do
  if [ "$a" = --no-audit ]; then audit=0; else args+=("$a"); fi
done
archived=$(python3 -c 'import sys, tarfile; print(tarfile.open(sys.argv[1]).pax_headers.get("comment", ""))' /out/src.tar)
if [ "$archived" != "$COMMIT" ]; then
  echo "refused: /out/src.tar is an archive of '$archived', not $COMMIT" >&2
  exit 2
fi
# the CPU, in the log: results can differ by round-off between runner CPUs with the same image (AIUE-101)
echo "cpu: $(grep -m1 '^model name' /proc/cpuinfo | cut -d: -f2-) ($(grep -m1 '^flags' /proc/cpuinfo | grep -o 'avx512f' || echo 'no avx512f'))" >&2
# install SRC LOG BUILD_OPTION...: the archive extracted to SRC and installed into /opt/venv with those options
install() {
  local src=$1 log=$2
  shift 2
  mkdir -p "$src"
  tar -xf /out/src.tar -C "$src"
  (cd "$src" && PATH=/opt/venv/bin:$PATH pip install -v --no-build-isolation --no-deps --force-reinstall . \
    "${@/#/--config-settings=--build-option=}" > "$log" 2>&1)
}
audit_opts=()
if [ "$audit" = 1 ]; then
  install /work/src-audit /out/build-audit.log --serial --checkbounds
  (cd /tmp && /opt/venv/bin/python /tests/yldot/tools/make_references.py _child "${args[@]}" --repo /work/src-audit \
    --out /out/audit --audit-only)
  audit_opts=(--audit /out/audit)
fi
install /work/src /out/build.log --serial
# No reference from a build that calls glibc's vector math library: libmvec's log gives different bits on Intel and
# AMD (AIUE-210), and setup.py keeps the math calls scalar on Linux (AIUE-211). Counted by symbol, since Forthon
# names -lmvec on every link and only --as-needed drops it
undefined=$(nm -D --undefined-only /opt/venv/lib/python3.12/site-packages/uedge/*.so)
mvec=$(grep -c '_ZGV' <<< "$undefined" || true)  # grep -c prints 0 and exits 1 when nothing matches
if [ "$mvec" != 0 ]; then
  echo "refused: the build calls libmvec ($mvec _ZGV symbols; AIUE-211)" >&2
  exit 2
fi
cd /tmp
python3 - "$COMMIT" "$RUNNER_IMAGE" > /out/build.json <<'EOF'
import json, subprocess, sys
gfortran = subprocess.run(["gfortran", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
print(json.dumps({"commit": sys.argv[1], "compiler": gfortran, "runner_image": sys.argv[2]}, indent=1))
EOF
# --repo: the variant inventory comes from the archive's .v files (only tests/ is mounted)
/opt/venv/bin/python /tests/yldot/tools/make_references.py _child "${args[@]}" --repo /work/src --out /out/references \
  --build /out/build.json "${audit_opts[@]}"
