from uedge import *
from h5py import File
from uedge.hdf5 import hdf5_restore
import os

casename = "tune"
# Rate files (ehr2.dat, C_rates.adas) come from the repository copy in
# builder/test/Forthon_cases/Forthon_case5, unless UEDGE_OMP_RATES_DIR points
# to another directory holding both files. mist.dat and the HDF5 files are read
# from the working directory (run the deck from the directory that holds them).
_case_dir = os.path.dirname(os.path.abspath(__file__))
_rates_dir = os.environ.get("UEDGE_OMP_RATES_DIR") or os.path.normpath(
    os.path.join(_case_dir, "..", "..", "..", "builder", "test", "Forthon_cases", "Forthon_case5"))
for _rate_file in ("ehr2.dat", "C_rates.adas"):
    if not os.path.exists(os.path.join(_rates_dir, _rate_file)):
        raise Exception("Rate file {} not found in {}".format(_rate_file, _rates_dir))
if len(_rates_dir) > 120:
    # aphdir/apidir are character*120: in a deep checkout fall back to the relative path
    _rel = os.path.relpath(_rates_dir)
    if len(_rel) > 120:
        raise Exception("Rate directory path longer than 120 characters: {}".format(_rates_dir))
    _rates_dir = _rel
aph.aphdir = _rates_dir
api.apidir = _rates_dir
bbb.restart=1

# ==== SPECIES ====
com.ngsp=2
com.nhsp=2
com.nhgsp=1
bbb.isimpon=6
com.nzsp[0]=6

# ==== GRID ====
bbb.mhdgeo=1
bbb.gengrid=0
com.isgriduehdf5=1
com.geometry="uppersn"
com.isnonog=1

# ==== SOLVER ====
bbb.premeth="ilut"
bbb.lenplufac=1000
bbb.lfililut=300

# ==== PHYSICS ====
bbb.minu[0]=2
bbb.ziin[0]=1
bbb.znuclin[0]=1
bbb.cngtgx=0
bbb.cngtgy=0

# ==== BOUNDARYCONDITIONS ====
bbb.iflcore=1
bbb.pcoree=6250000.0
bbb.pcorei=6250000.0
bbb.isupcore[0]=1
bbb.isnicore[0]=3
bbb.curcore[0]=250
bbb.isextrnpf=0
bbb.isnwconi[0]=3
bbb.lyni[:2]=[0.05, 0.05]
bbb.nwimin[0]=1e+16
bbb.isextrnw=0
bbb.isnwcono[0]=3
bbb.nwomin[0]=1000000000000000.0
bbb.isextrtpf=0
bbb.isextrtw=0
bbb.istepfc=3
bbb.lyte[:2]=[0.05, 0.05]
bbb.istipfc=3
bbb.lyti[:2]=[0.05, 0.05]
bbb.istewc=3
bbb.istiwc=3
bbb.isupss=1
bbb.isplflxl=0
bbb.isybdryog=1
bbb.isybdrywd=0

# ==== ATOMS ====
bbb.ineudif=2
bbb.minu[1]=2
bbb.ziin[1]=0
bbb.znuclin[1]=1
bbb.istgcon[0]=0
bbb.tgas[0]=0
bbb.isnicore[1]=3
bbb.isngcore[0]=1
bbb.albedoc[0]=1
bbb.ngcore[0]=3000000000000.0
bbb.isupcore[1]=1
bbb.tgwall[0]=0.04
bbb.isnwconi[1]=0
bbb.ifluxni=1
bbb.isnwcono[1]=0
bbb.cfloxiplt=1
bbb.ingb=2
bbb.ngbackg[0]=10000000000.0
bbb.cngfx=1
bbb.cngfy=1
bbb.cfvgpx[1]=0
bbb.cngflox[0]=1
bbb.cngfloy[0]=1
bbb.xstscal=0.02
bbb.ngscal=1
bbb.xgscal=0.01
bbb.cngmom=0
bbb.cmwall=0
bbb.cfbgt=0
bbb.kxn=0
bbb.kyn=0

# ==== RATES ====
com.istabon=10
com.isrtndep=1
bbb.icnucx=0
bbb.cnucx=0
bbb.icnuiz=0
bbb.cnuiz=0
bbb.isrecmon=1
bbb.cfrecom=1
bbb.eion=5
bbb.ediss=10

# ==== CARBON ====
com.mcfilename[0]="C_rates.adas"
com.iscxfit=2
bbb.ziin[2:8]=[1, 2, 3, 4, 5, 6]
bbb.minu[2:8]=[12, 12, 12, 12, 12, 12]
bbb.znuclin[2:8]=[6, 6, 6, 6, 6, 6]
bbb.isnicore[2:8]=[3, 3, 3, 3, 3, 3]
bbb.ncore[2:8]=[7e+19, 7e+19, 7e+19, 7e+19, 7e+19, 7e+19]
bbb.curcore[2:8]=[0, 0, 0, 0, 0, 0]
bbb.isupcore[2:8]=[1, 1, 1, 1, 1, 1]
bbb.isngcore[1]=1
bbb.ngcore[1]=3000000000000.0
bbb.isnwcono[2:8]=[3, 3, 3, 3, 3, 3]
bbb.nwomin[2:8]=[10000000.0, 10000000.0, 10000000.0, 10000000.0, 10000000.0, 10000000.0]
bbb.isnwconi[2:8]=[3, 3, 3, 3, 3, 3]
bbb.nwimin[2:8]=[10000000.0, 10000000.0, 10000000.0, 10000000.0, 10000000.0, 10000000.0]
bbb.tgwall[1]=0.04
bbb.isbohmms=0
bbb.n0[2:8]=[1e+17, 1e+17, 1e+17, 1e+17, 1e+17, 1e+17]
bbb.n0g[1]=1e+18
bbb.nzbackg=10000000000.0
bbb.inzb=2
bbb.ngbackg[1]=10000000000.0
bbb.ismctab=2
bbb.rcxighg[1]=0
bbb.kelighg[1]=5e-16
bbb.isch_sput[1]=7
bbb.fchemygwi=1
bbb.fchemygwo=1
bbb.fchemylb=1
bbb.fchemyrb=1
bbb.isph_sput[1]=3
bbb.crmb=2
bbb.cizb=1
bbb.fphysylb=1
bbb.fphysyrb=1
bbb.isi_sputw[1]=2
bbb.isi_sputpf[2]=2
bbb.t_wall=300
bbb.t_plat=300

# ==== DIFFUSIVITIES ====
bbb.kxe=1
bbb.kxi=1
bbb.parvis[0]=1
bbb.fcdif=0
bbb.isbohmcalc=0
bbb.inbtdif=0
bbb.inbpdif=0

# ==== FLUXLIM ====
bbb.flalfv=1
bbb.flalfe=0.21
bbb.flalfi=0.21
bbb.flalfgx[:3]=[0.6, 10, 1]
bbb.flalfgy[:3]=[0.6, 10, 1]
bbb.flalfgxy[:3]=[0.6, 10, 1]
bbb.flalftgx=1
bbb.flalftgy=1
bbb.flalfvgx=1e+20
bbb.flalfvgy=1e+20
bbb.flalfvgxy=1e+20
bbb.lgmax=0.25
bbb.lgtmax=0.1
bbb.lgvmax=0.1

# ==== DIFFERENCING ====
bbb.methn=33
bbb.methu=83
bbb.methe=33
bbb.methi=33
bbb.methg=66
bbb.methp=33

# ==== DRIFTS ====
bbb.newbcl=1
bbb.newbcr=1
bbb.b0=1.0
bbb.rsigpl=1e-08
bbb.cfjhf=1
bbb.cfjve=1
bbb.cfjpy=0
bbb.cfjp2=0
bbb.isfdiax=1
bbb.cfqydbo=0   #modified
bbb.cfydd=0
bbb.cf2dd=0
bbb.cftdd=1
bbb.cfyef=1
bbb.cftef=1
bbb.cf2ef=1
bbb.cfybf=1
bbb.cf2bf=1
bbb.cfqybf=1
bbb.cfq2bf=1
bbb.cfqybbo=0
bbb.cfniybbo=1
bbb.cfeeybbo=1
bbb.cfniydbo=0
bbb.cfeeydbo=0
bbb.cfeixdbo=0    #modified
bbb.cfeexdbo=0    #modified
bbb.cfqym=1
bbb.cfnus_i=1
bbb.cfnus_e=1

# ==== POTENTIAL ====
bbb.isnewpot=1
bbb.rnewpot=1
bbb.iphibcc=2
bbb.isutcore=2
bbb.iphibcwi=0
bbb.iphibcwo=0

# ==== EQUATIONS ====
bbb.isnion[:8]=[1, 1, 1, 1, 1, 1, 1, 1]
bbb.isngon[:2]=[0, 1]
bbb.cnfx=1
bbb.cnfy=1
bbb.cnsor=1
bbb.cnurn=1
bbb.cngsor=1
bbb.cnurg=1
bbb.isupon[:8]=[1, 1, 1, 1, 1, 1, 1, 1]
bbb.isupgon[:2]=[1, 0]
bbb.cmfx=1
bbb.cmfy=1
bbb.cpgx=1
bbb.cnuru=1
bbb.isteon=1
bbb.istion=1
bbb.istgon=0
bbb.cfvisx=1
bbb.cfvisy=1
bbb.cvgp=1
bbb.cnure=1
bbb.cnuri=1
bbb.isphion=1
bbb.isphiofft=0

# ==== OMP ====
#ppp.OMPParallelJac=1
#ppp.OMPlenpfac=25
#ppp.OMPParallelPandf1=0

# ==== RECYCLING ====
bbb.bcen=0
bbb.bcenw=0
bbb.recycp[:2]=[1, 1e-10]
bbb.recycw[:2]=[1, 1e-10]
bbb.recycm=-0.95
bbb.nwsor=3
bbb.issorlb[:3]=[1, 1, 1]
bbb.igspsoro[:3]=[1, 2, 1]
bbb.igaso[:3]=[0, 0, 2000]
bbb.xgaso[:3]=[0, 0, 4.3]
bbb.wgaso[:3]=[1000.0, 1000.0, 0.3]
bbb.albdso[:3]=[0.994, 1, 1]
bbb.matwso[:3]=[1, 1, 1]
bbb.igspsori[:3]=[1, 2, 1]
bbb.igasi[:3]=[0, 0, 0]
bbb.xgasi[:3]=[0, 0, 0]
bbb.wgasi[:3]=[1000.0, 1000.0, 1000.0]
bbb.albdsi[:3]=[1, 1, 1]
bbb.matwsi[:3]=[1, 1, 1]

bbb.allocate()

# ==== RESTORE SOLUTION ====
with File("b0p1.hdf5") as f:
    
    try:
        savegroup = f["restore/bbb"]
    except:
        savegroup = f["bbb"]
    for var in ["ngs", "nis", "phis", "tes", "tgs", "tis", "ups"]:
        setattr(bbb, var, savegroup[var][()])

# ==== USER-SPECIFIED COMMANDS ====
# Populate UEDGE arrays
bbb.issfon=0
bbb.ftol=1e20
bbb.exmain()
bbb.issfon=1
bbb.ftol=1e-8
bbb.albedo_by_user = 1
bbb.isimpon = 7
bbb.afracs = 1.5e-2
bbb.albrb[35:37,:,0] = 0.87
bbb.recyrb_use[35:37,0,0] = -0.13

# ==== SET USER-SPECIFIED DIFFUSIVITIES ====
with File("b0p1.hdf5", "r") as f:
    try:
        bbb.difniv=f["diffusivities/bbb/difniv"][()]
    except:
        pass
    try:
        bbb.kyev=f["diffusivities/bbb/kyev"][()]
    except:
        pass
    try:
        bbb.kyiv=f["diffusivities/bbb/kyiv"][()]
    except:
        pass
    try:
        bbb.travisv=f["diffusivities/bbb/travisv"][()]
    except:
        pass
    try:        bbb.dif_use=f["diffusivities/bbb/dif_use"][()]
    except:
        pass
    try:
        bbb.kye_use=f["diffusivities/bbb/kye_use"][()]
    except:
        pass
    try:
        bbb.kyi_use=f["diffusivities/bbb/kyi_use"][()]
    except:
        pass
    try:
        bbb.tray_use=f["diffusivities/bbb/tray_use"][()]
    except:
        pass
    try:
        bbb.fcdif=f["diffusivities/bbb/fcdif"][()]
    except:
        pass

# === TR Restore converged solution with new seec & seic
hdf5_restore("save_input_mod4.h5")

# === TR increase D+ diffusivities only in core/near-SOL region from 0.1 to 0.2
bbb.dif_use[com.ixpt1[0]+1:com.ixpt2[0]+1,4:28,0]=0.2
 
try:
    bbb.fracseecnew=1
except:
    pass
try:
    bbb.fracseicnew=1
except:
    pass
try:
    bbb.iyseicgmin=1    #omit neutral vg_dot_grad_Pg term in seic for iy<=iyseicgmin
except:
    pass

