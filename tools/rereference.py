# Regenerates the stored reference of one existing test case without
# re-perturbing its solution.
#
# MakeTests.make_unittests rebuilds a whole test directory, and write_data
# perturbs solution.h5 again with unseeded random numbers, so every case of the
# directory would get a new state. This script does what
# MakeTests.execute_case does for one case, with TestClass.perturb_solution
# replaced by a no-op on the test module it loads: the stored (perturbed)
# state is kept and only the 'pytests' reference group is rebuilt. The group
# is deleted first, because write_data overwrites existing datasets in place
# and fails when a variable's shape differs in the build used (v9 indexes
# conx by species), and the file is compacted afterwards. It checks that by
# hashing everything outside 'pytests' before and after, and exits with
# status 1 if anything there changed.
#
# Usage (from the repository root, in a venv with the UEDGE build to use):
#   python tools/rereference.py pytests/unittests/D_only/nonog/<case>
# Run each case in a fresh process: UEDGE state is global.


def hash_outside_pytests(path):
    """Return a sha256 over everything outside 'pytests': every group and
    dataset name, attribute, dataset dtype, shape, storage layout and filters,
    and value."""
    from hashlib import sha256
    from h5py import File, Dataset
    digest = sha256()

    def visit(name, obj):
        if name == 'pytests' or name.startswith('pytests/'):
            return
        digest.update(name.encode())
        for key in sorted(obj.attrs.keys()):
            digest.update(key.encode())
            digest.update(repr(obj.attrs[key]).encode())
        if isinstance(obj, Dataset):
            digest.update(repr((obj.dtype.str, obj.shape, obj.chunks,
                obj.compression, obj.compression_opts, obj.shuffle,
                obj.fletcher32, obj.scaleoffset)).encode())
            value = obj[()]
            if obj.dtype.kind == 'O':
                # Object data (e.g. variable-length strings): hash the
                # values, not the pointers
                digest.update(repr(value.tolist() if obj.shape != ()
                                   else value).encode())
            elif obj.shape != ():
                digest.update(value.tobytes())
            else:
                digest.update(repr(value).encode())

    with File(path, 'r') as f:
        for key in sorted(f.attrs.keys()):
            digest.update(key.encode())
            digest.update(repr(f.attrs[key]).encode())
        f.visititems(visit)
    return digest.hexdigest()


def drop_reference(path):
    """Delete the 'pytests' group so write_data creates every dataset anew."""
    from h5py import File
    with File(path, 'a') as f:
        if 'pytests' in f:
            del f['pytests']


def compact(path):
    """Rewrite the file to reclaim the space of the deleted group."""
    from os import replace
    from h5py import File
    tmp = path + '.compact'
    with File(path, 'r') as src, File(tmp, 'w') as dst:
        for key, value in src.attrs.items():
            dst.attrs[key] = value
        for key in src.keys():
            src.copy(src[key], dst, name=key)
    replace(tmp, path)


def stored_fnrm(path):
    from h5py import File
    with File(path, 'r') as f:
        return float(f['pytests/default/fnrm'][()])


def rereference(casepath):
    import importlib.util
    from glob import glob
    from os import chdir
    from os.path import abspath, basename
    casepath = abspath(casepath)
    chdir(casepath)
    tests = glob('test_*.py')
    if len(tests) != 1:
        raise Exception('Expected one test_*.py in {}, found {}'.format(
            casepath, tests))
    before = hash_outside_pytests('solution.h5')
    oldfnrm = stored_fnrm('solution.h5')

    from uedge import bbb, com
    com.iprint = 0
    # Set up the case as MakeTests.execute_case does
    inputspec = importlib.util.spec_from_file_location('input', 'input.py')
    inputspec.loader.exec_module(importlib.util.module_from_spec(inputspec))
    bbb.issfon = 1
    bbb.ftol = 1e20
    bbb.exmain()
    # Load the test module and keep its stored state unperturbed
    testspec = importlib.util.spec_from_file_location('test', tests[0])
    testmodule = importlib.util.module_from_spec(testspec)
    testspec.loader.exec_module(testmodule)
    testmodule.TestClass.perturb_solution = (
        lambda self, file, perturbation=1e-2: None)
    drop_reference('solution.h5')
    testmodule.TestClass().write_data()
    com.iprint = 1
    compact('solution.h5')

    after = hash_outside_pytests('solution.h5')
    newfnrm = stored_fnrm('solution.h5')
    print('{}: fnrm {!r} -> {!r} (relative change {:.3e})'.format(
        basename(casepath), oldfnrm, newfnrm, (newfnrm - oldfnrm) / oldfnrm))
    print('state outside pytests/: {} ({})'.format(
        'unchanged' if before == after else 'CHANGED', after[:16]))
    return before == after


if __name__ == '__main__':
    from sys import argv, exit
    if len(argv) != 2:
        print(__doc__ or 'usage: python tools/rereference.py <case dir>')
        exit(2)
    exit(0 if rereference(argv[1]) else 1)
