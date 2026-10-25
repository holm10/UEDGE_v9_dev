# Settings of the serial-check case yldot-d_only-core_nogradient (AIUE-106): the lines that
# pytests/unittests/D_only/nonog/core_nogradient/input.py (origin/pytests f695acd) adds to pytests/unittests/D_only/nonog/default/input.py, in order;
# run after the family's input.py (owner, 2026-10-24, AIUE-106). Values as in the deck: never edit them.
from uedge import *  # noqa: F401,F403  (as the decks)

# templates/D_only/inputs/boundary/core/energy/core_nogradient.py
bbb.iflcore = -1		#flag=0, fixed Te,i;=1, fixed power on core
