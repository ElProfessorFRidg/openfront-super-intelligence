"""Garde-fou memoire : attend qu'assez de RAM physique soit libre avant de lancer des moteurs (chaque moteur ~0,7 Go). Evite l'incident de saturation (jobs tues a < 4 Go libres)."""
import ctypes, time, sys


class _MS(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_gb():
    m = _MS(); m.dwLength = ctypes.sizeof(m); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); return m.ullAvailPhys / 2**30


def wait_ram(needed_gb, timeout_s=7200, tag=""):
    """Bloque jusqu'a free_gb() >= needed_gb (ou timeout). Retourne la RAM libre finale."""
    t0 = time.time(); warned = False
    while free_gb() < needed_gb and time.time() - t0 < timeout_s:
        if not warned: print(f"[memguard{tag}] RAM libre {free_gb():.1f} Go < {needed_gb} Go requis : attente", flush=True); warned = True
        time.sleep(15)
    if warned: print(f"[memguard{tag}] reprise apres {time.time()-t0:.0f} s, RAM libre {free_gb():.1f} Go", flush=True)
    return free_gb()
