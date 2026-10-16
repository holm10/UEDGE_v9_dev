# AIUE-62: Linux (libgomp) environment for the OpenMP Jacobian characterisation.
# Mirrors .github/workflows/build-test-omp.yml (AIUE-57): Python 3.11, numpy==1.26.4, forthon>=0.10.7, h5py, pytest,
# system gfortran; the build itself is `python -m pip install -v .` (default OpenMP build).
FROM python:3.11-bookworm@sha256:5887f265d8d44d8b4734d3658b21d668edf5aaf92e4945bc0c984afbfab105d3
RUN apt-get update && apt-get install -y --no-install-recommends gfortran binutils file && rm -rf /var/lib/apt/lists/*
RUN git config --system --add safe.directory '*'
