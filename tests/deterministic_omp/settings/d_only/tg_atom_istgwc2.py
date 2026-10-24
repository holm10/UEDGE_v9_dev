# Settings of the serial-check case yldot-d_only-tg_atom_istgwc2 (AIUE-106): the lines that
# pytests/unittests/D_only/nonog/tg_atom_istgwc2/input.py (origin/pytests f695acd) adds to pytests/unittests/D_only/nonog/default/input.py, in order;
# run after the family's input.py (owner, 2026-10-24, AIUE-106). Values as in the deck: never edit them.
from uedge import *  # noqa: F401,F403  (as the decks)

setni = True
setup = True
setphi = True
setphiofft = True
setng = True
setupg = True
setti = True
sette = True
settg = True

# templates/D_only/inputs/atoms/tg_atom_istgwc2.py
settg = False
bbb.istgon = 0      # Reset Tg equation
bbb.istgon[0] = 1   # Turn on D0 temperature equation
bbb.cftiexclg = 0.  # Remove the Tg part in the Ti equation
bbb.cfdiss = 1.0
bbb.istgcore[0] = 2 #..albedo
bbb.istgpfc[0] = 4#2  #..zml flow change to 4 later
bbb.istgwc[0] = 2#2   #..flow
bbb.istglb[0] = 4
bbb.istgrb[0] = 4

bbb.cfnidhgy = 1.0
bbb.cfnidhg2 = 1.0
bbb.cfnidhdis = 1.0 #..consider drift heating for dissociation
bbb.cfnidhmol = 1.0 #..ignore molecular v in dissociation drift heating

bbb.recyce = 0.3
bbb.recycm = -0.9


if setni:
    bbb.isnion = 1
if setup:
    bbb.isupon = 1
if sette:
    bbb.isteon = 1
if setti:
    bbb.istion = 1
if setphi:
    bbb.isphion = 1
if setphiofft:
    bbb.isphiofft = 0
if settg:
    bbb.istgon = 0
if setng:
    bbb.isngon = 0
    bbb.isngon[0] = 0
if setupg:
    bbb.isupgon = 0
    bbb.isupgon[0] = 1
