from input_mod4 import *
ppp.OMPParallelJac=1
ppp.OMPlenpfac=20
bbb.isnion=0
bbb.isngon=0
bbb.isupon=0
bbb.istion=0
bbb.isphion=0
bbb.isphiofft=1
bbb.itermx=3


bbb.isteoffxy = 1
#bbb.isteoffxy[3:-3, com.iysptrx+4:-1] = 0
bbb.isteoffxy[3:8, 18:23]=0
#bbb.isteon=0
#bbb.isnion[0]=1
#bbb.ireorder = 0
#bbb.iscolnorm = 0
#bbb.issfon = 0
bbb.exmain()
from uetools import Case
c=Case()
c.jac.write_csr_jacobian_hdf5('secondjac')

