"""OpenMP determinism harness for the AIUE-8 reproducer (tests/deterministic_omp/case).

config  -- run specifications (equation presets, arms, threads)
worker  -- runs one specification in a fresh process and records the results
runner  -- prepares a run directory and environment, launches the worker, loads the record
compare -- bitwise comparison and localisation of mismatches
cli     -- command line (run / compare / check), exit codes 0 agree, 1 mismatch, 2 harness error

The modules other than worker never import uedge, so the comparison can run anywhere.
"""
