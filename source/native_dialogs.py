"""Native dialogs for this standalone utility; no Tk dependency on Windows."""
import os
def choose_file(title,kind='pdf'):
 if os.name!='nt':
  import tkinter as tk
  from tkinter import filedialog
  w=tk.Tk();w.withdraw()
  try:return filedialog.askopenfilename(title=title,filetypes=[('PDF','*.pdf')] if kind=='pdf' else [('RGB images','*.png *.jpg *.jpeg')])
  finally:w.destroy()
 import ctypes
 from ctypes import wintypes as w
 class OPENFILENAMEW(ctypes.Structure):
  _fields_=[('lStructSize',w.DWORD),('hwndOwner',w.HWND),('hInstance',w.HINSTANCE),('lpstrFilter',w.LPCWSTR),('lpstrCustomFilter',w.LPWSTR),('nMaxCustFilter',w.DWORD),('nFilterIndex',w.DWORD),('lpstrFile',w.LPWSTR),('nMaxFile',w.DWORD),('lpstrFileTitle',w.LPWSTR),('nMaxFileTitle',w.DWORD),('lpstrInitialDir',w.LPCWSTR),('lpstrTitle',w.LPCWSTR),('Flags',w.DWORD),('nFileOffset',w.WORD),('nFileExtension',w.WORD),('lpstrDefExt',w.LPCWSTR),('lCustData',w.LPARAM),('lpfnHook',ctypes.c_void_p),('lpTemplateName',w.LPCWSTR),('pvReserved',ctypes.c_void_p),('dwReserved',w.DWORD),('FlagsEx',w.DWORD)]
 buffer=ctypes.create_unicode_buffer(32768);ofn=OPENFILENAMEW();ofn.lStructSize=ctypes.sizeof(ofn);ofn.lpstrFile=ctypes.cast(buffer,w.LPWSTR);ofn.nMaxFile=len(buffer);ofn.lpstrTitle=title;ofn.nFilterIndex=1
 ofn.lpstrFilter='PDF files (*.pdf)\0*.pdf\0\0' if kind=='pdf' else 'RGB images (*.png;*.jpg;*.jpeg)\0*.png;*.jpg;*.jpeg\0\0'
 ofn.Flags=0x80000|0x1000|0x800|0x8
 dlg=ctypes.windll.comdlg32;dlg.GetOpenFileNameW.argtypes=[ctypes.POINTER(OPENFILENAMEW)];dlg.GetOpenFileNameW.restype=w.BOOL
 if dlg.GetOpenFileNameW(ctypes.byref(ofn)):return buffer.value
 error=dlg.CommDlgExtendedError()
 if error:raise RuntimeError(f'Windows file selection failed: {error}')
 return ''
def notify(title,message,error=False):
 if os.name=='nt':
  import ctypes
  ctypes.windll.user32.MessageBoxW(None,message,title,0x10 if error else 0x40)
 else:
  from tkinter import messagebox
  (messagebox.showerror if error else messagebox.showinfo)(title,message)
