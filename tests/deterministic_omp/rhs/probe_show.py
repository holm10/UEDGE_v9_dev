"""AIUE-58: print a rhs_probe.py record (python probe_show.py <rundir> [-l for the chunk layout])."""
import json, sys
r = json.load(open(sys.argv[1] + '/probe.json'))
if r.get('error'): print(r['error'])
L = r.get('layout')
if L and '-l' in sys.argv:
    print({k: v for k, v in L.items() if not k.startswith('range')})
    print('rangechunk', L['rangechunk']); print('rangexptchunk', L['rangexptchunk'])
for s in r['steps']:
    print('%-26s ndiff %5d  sz %4d  %s  ncells %4d  %s  max_rel %.3g' % (s['name'], s['ndiff'], s['nsigned_zero'], s['by_eq'], s['ncells'], s['cells'][:8], s['max_rel']))
