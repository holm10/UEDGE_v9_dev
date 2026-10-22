# yldot round-off measurement, Linux side (AIUE-87; owner, 2026-10-21: Ubuntu 24.04 amd64, the CI runner's
# distribution, as tests/deterministic_omp/linux/Dockerfile.ubuntu). Every package that compiles or runs UEDGE is
# pinned to an exact version: a pin the archive no longer carries fails the build instead of drifting (the snapshot
# archive needs https, which the base image cannot verify before ca-certificates is installed). Usage: collect.sh.
FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      gfortran=4:13.2.0-7ubuntu1 gfortran-13=13.3.0-6ubuntu2~24.04.1 \
      gcc=4:13.2.0-7ubuntu1 gcc-13=13.3.0-6ubuntu2~24.04.1 \
      libgfortran5=14.2.0-4ubuntu2~24.04.1 libgomp1=14.2.0-4ubuntu2~24.04.1 \
      binutils=2.42-4ubuntu2.10 make=4.3-4.1build2 libreadline-dev=8.2-4build1 \
      python3=3.12.3-0ubuntu2.1 python3-venv=3.12.3-0ubuntu2.1 python3-dev=3.12.3-0ubuntu2.1 \
      python3.12=3.12.3-1ubuntu0.17 ca-certificates=20260816ubuntu0.24.04.1 \
    && rm -rf /var/lib/apt/lists/*
# the pins of the macOS base venvs (../uedge-wt/venvs/base-*.BUILD.txt)
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir setuptools==84.2.1 forthon==0.10.10 numpy==2.5.4 h5py==3.16.0 \
    && dpkg-query -W > /opt/dpkg-versions.txt && /opt/venv/bin/pip freeze > /opt/pip-freeze.txt
COPY collect.sh /opt/collect.sh
