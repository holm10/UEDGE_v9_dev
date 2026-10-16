python testscript1.py > run1_1.txt
python testscript2.py > run1_2.txt
mv firstjac.hdf5 firstjac1.hdf5 
mv secondjac.hdf5 secondjac1.hdf5 
python testscript1.py > run1_2.txt
python testscript2.py > run1_2.txt
mv firstjac.hdf5 firstjac2.hdf5 
mv secondjac.hdf5 secondjac2.hdf5 
