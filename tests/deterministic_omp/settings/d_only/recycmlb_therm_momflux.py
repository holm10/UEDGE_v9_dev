# Settings of the serial-check case yldot-d_only-recycmlb_therm_momflux (AIUE-106): the lines that
# pytests/unittests/D_only/nonog/recycmlb_therm_momflux/input.py (origin/pytests f695acd) adds to pytests/unittests/D_only/nonog/default/input.py, in order;
# run after the family's input.py (owner, 2026-10-24, AIUE-106). Values as in the deck: never edit them.
from uedge import *  # noqa: F401,F403  (as the decks)

# templates/D_only/inputs/boundary/plates/momentum/recycmlb_therm_momflux.py
bbb.recycm = 0
bbb.recycmlb_use = -20
