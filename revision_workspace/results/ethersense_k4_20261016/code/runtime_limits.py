"""Limits for lightweight processing on the shared project workstation."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
    try: value=int(os.environ.get(key,'4'))
    except ValueError: value=4
    os.environ[key]=str(max(1,min(4,value)))
if os.name=='nt':
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
else:
    try: os.nice(5)
    except OSError: pass
