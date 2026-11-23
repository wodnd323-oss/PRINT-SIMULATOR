"""Isolated Ghostscript DLL runner; no shell and no global system changes."""
import ctypes as C
import os
import sys
from pathlib import Path

def main():
    root=Path(__file__).resolve().parent/'runtime/ghostscript'
    os.environ['GS_LIB']=';'.join(str(root/x) for x in ('lib','Resource/Init','Resource/Font'))
    dll=C.CDLL(str(root/'bin/gsdll64.dll'))
    dll.gsapi_new_instance.argtypes=[C.POINTER(C.c_void_p),C.c_void_p]
    dll.gsapi_new_instance.restype=C.c_int
    dll.gsapi_set_arg_encoding.argtypes=[C.c_void_p,C.c_int]
    dll.gsapi_init_with_args.argtypes=[C.c_void_p,C.c_int,C.POINTER(C.c_char_p)]
    dll.gsapi_exit.argtypes=[C.c_void_p]
    dll.gsapi_delete_instance.argtypes=[C.c_void_p]
    dll.gsapi_delete_instance.restype=None
    context=C.c_void_p()
    if dll.gsapi_new_instance(C.byref(context),None)<0:return 1
    try:
        if dll.gsapi_set_arg_encoding(context,1)<0:return 1
        values=[v.encode('utf8') for v in ['gs',*sys.argv[1:]]]
        code=dll.gsapi_init_with_args(context,len(values),(C.c_char_p*len(values))(*values))
        ended=dll.gsapi_exit(context)
        return 0 if code in (0,-101) and ended==0 else 1
    finally:dll.gsapi_delete_instance(context)

if __name__=='__main__':raise SystemExit(main())
