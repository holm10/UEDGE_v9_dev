"""Trim the owner's HDF5 data files to the datasets the reproducer deck reads.

Usage: python trim_case_data.py <b0p1.hdf5> <save_input_mod4.h5> <outdir>

input_mod4.py reads from b0p1.hdf5:
  - restore/bbb/{ngs,nis,phis,tes,tgs,tis,ups}  (falls back to bbb/ if restore/ is missing)
  - diffusivities/bbb/*                         (each one optional)
and calls uedge.hdf5.hdf5_restore on save_input_mod4.h5, which reads
  - bbb/{tes,tis,ups,nis,phis,ngs,tgs,tipers}   (tipers only if bbb has it and the file has it)
Everything else in the two files is dropped. Datasets are copied bit for bit (h5py copy).
"""
import sys
from os.path import join
from h5py import File

STATE = ["ngs", "nis", "phis", "tes", "tgs", "tis", "ups"]


def trim_b0p1(src, dst):
    with File(src, "r") as fin, File(dst, "w") as fout:
        group = "restore/bbb" if "restore" in fin else "bbb"
        for var in STATE:
            fout.require_group(group)
            fin.copy(fin[group][var], fout[group], name=var)
        if "diffusivities" in fin:
            fin.copy(fin["diffusivities"], fout, name="diffusivities")


def trim_save(src, dst):
    with File(src, "r") as fin, File(dst, "w") as fout:
        fout.require_group("bbb")
        for var in STATE + ["tipers"]:
            if var in fin["bbb"]:
                fin.copy(fin["bbb"][var], fout["bbb"], name=var)


if __name__ == "__main__":
    b0p1, save, outdir = sys.argv[1:4]
    trim_b0p1(b0p1, join(outdir, "b0p1.hdf5"))
    trim_save(save, join(outdir, "save_input_mod4.h5"))
