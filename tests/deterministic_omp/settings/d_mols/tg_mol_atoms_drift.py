# Settings of the serial-check case yldot-d_mols-tg_mol_atoms_drift (AIUE-106): the lines that
# pytests/unittests/D_mols/nonog_mols/tg_mol_atoms_drift/input.py (origin/pytests f695acd) adds to pytests/unittests/D_mols/nonog_mols/default/input.py, in order;
# run after the family's input.py (owner, 2026-10-24, AIUE-106). Values as in the deck: never edit them.
from uedge import *  # noqa: F401,F403  (as the decks)

# templates/D_mols/inputs/atoms/tg_mol_atoms_drift.py

bbb.istgon[0] = 1   # Turn on D0 temperature equation
bbb.cftiexclg = 0.  # Remove the Tg part in the Ti equation
bbb.cfdiss = 1.0
bbb.istgcore[0] = 2 #..albedo
bbb.istgpfc[0] = 4#2  #..zml flow change to 4 later
bbb.istgwc[0] = 4#2   #..flow
bbb.istglb[0] = 4
bbb.istgrb[0] = 4
bbb.recyce = 0.3
bbb.recycm = -0.9
bbb.cfnidhgy = 1.0
bbb.cfnidhg2 = 1.0
bbb.cfnidhdis = 1.0 #..consider drift heating for dissociation
bbb.cfnidhmol = 1.0 #..ignore molecular v in dissociation drift heating


# templates/D_mols/inputs/drifts/tg_mol_atoms_drift.py

# Drifts and currents
bbb.isphion = 1
bbb.b0 = 1.0                    # =1 for normal direction of B-field
bbb.rsigpl=1.e-8                #anomalous cross-field conductivity
bbb.cfjhf=1.            #turn-on heat flow from current [bbb.fqp]
bbb.cfjve = 1.          #makes bbb.vex = vix - bbb.cfjve*bbb.fqx
bbb.cfjpy = 0.          #diamag. cur. in flx.y-direction
bbb.cfjp2 = 0.          #diamag. cur. in 2-direction
bbb.cfsigm = 1.0
#
bbb.newbcl=1
bbb.newbcr=1
bbb.isfdiax =1.         #Factor to turn on (ExB+diamag.) contrib. to sheath
#
bbb.cfyef = 1.0         #ExB drift in flx.y-dir.
bbb.cf2ef = 1.0         #ExB drift in 2-dir.
bbb.cfydd = 0.          #Diamag. drift in flx.y-dir. [always=0]
bbb.cf2dd = 0.          #Diamag. drift in 2-dir. [always=0]
bbb.cfrd = 0.           #Resistive drift in flx.y and 2 dirs.
bbb.cfbgt = 0.          #Diamag. energy drift [always=0]
bbb.cfybf = 1.0              #turns on bbb.vycb - radial grad_B drift
bbb.cf2bf = 1.0              #turns on bbb.v2cb - perp grad_B drift [nearly pol]
bbb.cfqybf = 1.0             #turns on bbb.vycb contrib to radial current
bbb.cfq2bf = 1.0             #turns on bbb.v2cb contrib to perp["2"] current
#..modified
bbb.cfqybbo=1.     #turn off Grad B current on boundary
bbb.cfqydbo=0.     #use full diagmagetic current on boundary to force j_r=0

bbb.cfniybbo=1.   # use to avoid artificial source at core boundary
bbb.cfniydbo=0.   # use to avoid artificial source at core boundary
bbb.cfeeybbo=1.   # ditto
bbb.cfeeydbo=0.   # ditto
#bbb.cfeixdbo=1.   # turn on BXgrad(T) drift in plate BC
#bbb.cfeexdbo=1.   # turn on diamagnetic drift in plate BC
bbb.cfeixdbo=0.
bbb.cfeexdbo=0.
bbb.cftef=1.0     #turns on v2ce for toroidal velocity
bbb.cftdd=1.0     #turns on v2dd (diamag vel) for toloidal velocity
bbb.cfqym=1.0     #turns on inertial correction to fqy current
#
bbb.isnewpot = 1
bbb.rnewpot = 1.
#bbb.iphibcc = 0         #set bbb.phi[,1] uniform poloidally
bbb.iphibcc=3     # =3 gives ey=eycore on core bdry
bbb.iphibcwi=0    # set ey=0 on inner wall if =0
                  # phi(PF)=phintewi*te(ix,0) on PF wall if =1
bbb.iphibcwo=0    # same for outer wall
bbb.isutcore=2    # =1, set dut/dy=0 on iy=0 (if iphibcc=0)
                # =0, toroidal angular momentum=lzcore on iy=0 (iphibcc=0)


# templates/D_mols/inputs/mols/tg_mol_atoms_drift.py
bbb.istgcore[1] = 2
bbb.istgpfc[1] = 0
bbb.istgwc[1] = 0
bbb.istglb[1] = 0
bbb.istgrb[1] = 0
bbb.tgwall[1] = 0.2
