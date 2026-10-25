# Settings of the serial-check case yldot-d_only-recycmrb (AIUE-106): the lines that
# pytests/unittests/D_only/nonog/recycmrb/input.py (origin/pytests f695acd) adds to pytests/unittests/D_only/nonog/default/input.py, in order;
# run after the family's input.py (owner, 2026-10-24, AIUE-106). Values as in the deck: never edit them.
from uedge import *  # noqa: F401,F403  (as the decks)

# templates/D_only/inputs/boundary/plates/momentum/recycmrb.py
bbb.recycm = 0
bbb.recycmrb_use = -0.5
