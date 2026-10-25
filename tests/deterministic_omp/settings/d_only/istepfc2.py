# Settings of the serial-check case yldot-d_only-istepfc2 (AIUE-106): the lines that
# pytests/unittests/D_only/nonog/istepfc2/input.py (origin/pytests f695acd) adds to pytests/unittests/D_only/nonog/default/input.py, in order;
# run after the family's input.py (owner, 2026-10-24, AIUE-106). Values as in the deck: never edit them.
from uedge import *  # noqa: F401,F403  (as the decks)

# templates/D_only/inputs/boundary/walls/energy/istepfc2.py
bbb.istepfc = 2		#=3 sets scale length bbb.lyte
