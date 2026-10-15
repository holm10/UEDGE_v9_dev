#!/bin/bash
set -eu
git clone -q --no-checkout /mnt/repo /work/harness
git -C /work/harness checkout -q "$1"
git -C /work/harness log --oneline -1
