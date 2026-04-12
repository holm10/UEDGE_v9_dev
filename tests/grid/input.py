# Import UEDGE and set paths
from uedge import *

def generate_grid():
    ''' Input file for the UEDGE single-null DIII-D case, shot 160299

    The shot is a set of well-characterized L-mode shots with fwd-B, LSN

    Power flow:
        Pinj=?
            Poh=? MW
        Pwdot=?
        P_rad~?
        P_sep=? MW
        P_div=?
    Boundary condition:
        ncore=3.0e19
        pcoree=pcorei=0.45MW
    '''
    from numpy import ones
    # Input package located in UEDGE/pyscripts/contrib/input


    from numpy import array,pi
    '''
    Function for defining the grid setup in UEGDE
    '''
    
    gridpath='.' 
    plate=None 
    nx_ileg=20 
    nx_oleg=18
    nxcore_inside=25
    nxcore_outside=25
    nycore=22 
    nysol=28       
    gengrid=1 
    isnonog=1
    psi0min1=.90
    psi0min2=0.98
    psi0sep=1.00005
    psi0max=1.10
    nxxpt=1
    nxmod=3
    alfxptu=0.75
    alfcy=2.5
    dmix0=0.5
    # Set grid paths if V7.08 is being used: not available for earlier versions
    # For previous versions, place EFIT files in data folder
    shot = 160299
    time = 2240
    stamp = ".".join(str(x) for x in [shot, time])
    com.aeqdskfname= "a{}".format(stamp) # Efit equilibrium
    com.geqdskfname="g{}".format(stamp) # Efit equilibrium
    """=====================================================================================================
    GRID
    ====================================================================================================="""
    # Geometry definition
    #- - - - - - - - - - -
    bbb.ngrid=1             # Number of grids to allocate space for: odesetup.m L6488

    bbb.mhdgeo=1            # Grid geometry:
                                #=-2 mag mirror (FRC-annulus)   
                                #=-1 cartesian geometry
                                #=0: cylindrical geometry
                                #=1: toroidal MHD equilibrium
                                #=2: toroidal circular limiter

    com.geometry="snull"    # Magnetic configuration
                                #'snull': lower single null
                                #'uppersn': upper single null
                                #'dnbot': bottom half of double null
                                #'dnull': full double null
                                #'snowflake15': Ryutov's theta~15 deg
                                #'snowflake45': Ryutov's theta~45 deg
                                #'snowflake75': Ryutov's theta~75 deg
                                #'dnXtarget': dnbot with Xtarget

    com.isnonog=isnonog           # switch determining if 9-point differencing is on for non-orthogonal meshes


    # Generate grid
    bbb.gengrid=gengrid           #1= generates grid, 0=restores grid from gridue 


    # Magnetic fluxes
    #- - - - - - - - -
    flx.psi0min1=psi0min1        # Normalized flux value at innermost core flux surface
    flx.psi0min2=psi0min2        # Normalized flux value at innermost PF surface
    flx.psi0sep=psi0sep     # Normalized flux value at separatrix flux surface (just slightly outside)
    flx.psi0max=psi0max        # Normalized flux value at wall on outboard side of magnetic axis



    # Cells
    #- - - - 
    com.nxleg[0,]=[nx_ileg,nx_oleg]                 # Number of poloidal cells in 1st divertor leg [inside, outside]
    com.nxcore[0,]=[nxcore_inside,nxcore_outside]   # Number of poloidal cells along 1st core boundary [inside, outside]
    com.nycore[0]=nycore                            # Number of radial zones in 1st core of plasma
    com.nysol[0]=nysol                              # Number of radial zones in 1st SOL

    com.nxxpt=nxxpt             # Number of extra poloidal cells at X-point (per quadrant)
    grd.nxmod=nxmod             # Number of "upstream" poloidal cells (per quadrant) in the
                            #   original mesh that are modified by subroutine refinex

    bbb.isybdryog=1         #=1 sets fx0, fmx stencil to orthogonal values at iy=0 & iy=ny

    # Shaping
    #- - - - -
    grd.alfxptu=alfxptu        # Variable for extra X-point grid spacign above X-point:
                            #  frac=(i/(nxxpt+nxmod))**alfxptu 

    flx.alfcy=alfcy           # SOL flux contour distribution:
                            #  <1: uniform
                            #  >1: concentrated near sep

    grd.slpxt=1.2           # Slope enchantment factor for x(t) near core crown

    grd.kxmesh=1            # X-mesh definition model:
                                #=0: old model (manual def. of seed points)
                                #=1: linear*rational form for x(t)
                                #=2: linear*exponential form for x(t)
                                #=3: spline form for x(t)
                                #=4: exponential+spline form for x(t)

    flx.istchkon=1          # Switches for imposing limits on polar angle about (rmagx,zmagx)
    if flx.istchkon==1:     # Limts imposed
        flx.dtheta_exclude    = array([.75,.50])*pi
                            # angular width of region where SOL flux contours are excluded
                            #   [inboard flux contours, outboard flux contours]
        flx.dtheta_overlap_pf = array([.05,.01])*pi
                            # angular width over which p.f. flux contours can overlap
                            #   with flux contours in the adjacent region.
        flx.dtheta_overlap_sol= array([0.25,0.25])*pi
                            # angular width over which SOL flux contours can overlap
                            #   with flux contours in the adjacent region.
                            #   [inboard flux contours, outboard flux contours]
        # com.theta_split=np.pi/2   # Computed poloidal angle where in-/outboard mesh regions meet
        # flx.thetax=-1.88      # Computed poloidal angle of X-point relative to magnetic axis

    flx.altsearch=1         # Search path for PF surfaces:
                                #=0: search vertically up toward x-point
                                #=1: search vertically down from x-point
                                #=2: search diagonally down and in from x-point

    com.ismmon=3
    grd.wtmesh1=0.0
    grd.istream=0
    grd.nsmooth=4
    grd.dmix0=dmix0
    grd.iplate=1

 
    # for inboard half of mesh: (same as outboard half)
    grd.nplate1=5
    grd.gchange("grd.Mmod",0)

    grd.rplate1=[   1.600E+00,      1.27300E+00,    1.15310E+00,
                    1.01600E+00,    1.01600E+00
                ]

    grd.zplate1=[   2.34100E-01,    2.34100E-01,    2.34100E-01,  
                    3.71200E-01,    1.0000
                ]

    # for outboard half of mesh: (modified baffle/plate)
    grd.nplate2=10
    grd.gchange("grd.Mmod",0)

    grd.rplate2=[   2.13690E+00,    1.78570E+00,    1.76800E+00,  
                    1.76800E+00,    1.68100E+00,    1.67500E+00,  
                    1.67200E+00,    1.67200E+00,    1.55500E+00,  
                    1.21200E+00
                ]

    grd.zplate2=[   6.28600E-01,    4.25600E-01,    3.89300E-01,  
                    0.35,           0.35,           0.35, 
                    0.35,           0.35,           0.35, 
                    0.35
                ]

    # Note: versions before V7.08 cannot read EFIT equilibra from paths: must be placed in data
    flx.flxrun()
    grd.grdrun()
    com.isgriduehdf5 = 1
    grd.grdrun()

    return

