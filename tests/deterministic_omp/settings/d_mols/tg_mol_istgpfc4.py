# Settings of the serial-check case yldot-d_mols-tg_mol_istgpfc4 (AIUE-106): the lines that
# pytests/unittests/D_mols/nonog_mols/tg_mol_istgpfc4/input.py (origin/pytests f695acd) adds to pytests/unittests/D_mols/nonog_mols/default/input.py, in order;
# run after the family's input.py (owner, 2026-10-24, AIUE-106). Values as in the deck: never edit them.
from uedge import *  # noqa: F401,F403  (as the decks)

# templates/D_mols/inputs/mols/tg_mol_istgpfc4.py
bbb.istgcore[1] = 2
bbb.istgpfc[1] = 4
bbb.istgwc[1] = 0
bbb.istglb[1] = 0
bbb.istgrb[1] = 0
bbb.tgwall[1] = 0.2
