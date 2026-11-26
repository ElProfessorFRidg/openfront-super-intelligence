"""Topologie REELLE du processeur lue dans Windows (GetLogicalProcessorInformationEx) : classe d'efficacite de chaque coeur, threads logiques associes, masques d'affinite.
Sur Intel hybride : EfficiencyClass la plus haute = P-cores ; plus bas = E-cores / LP E-cores. Lecture seule, quelques ms."""
import ctypes, ctypes.wintypes as wt, json, sys

RelationProcessorCore = 0


class GROUP_AFFINITY(ctypes.Structure):
    _fields_ = [("Mask", ctypes.c_size_t), ("Group", wt.WORD), ("Reserved", wt.WORD * 3)]


def read():
    k = ctypes.windll.kernel32; n = wt.DWORD(0)
    k.GetLogicalProcessorInformationEx(RelationProcessorCore, None, ctypes.byref(n))
    buf = (ctypes.c_ubyte * n.value)()
    if not k.GetLogicalProcessorInformationEx(RelationProcessorCore, buf, ctypes.byref(n)): raise OSError("GetLogicalProcessorInformationEx a echoue")
    cores, off = [], 0
    while off < n.value:
        rel = ctypes.c_int.from_buffer(buf, off).value; size = ctypes.c_uint32.from_buffer(buf, off + 4).value
        if rel == RelationProcessorCore:
            flags = buf[off + 8]; eff = buf[off + 9]; gc = ctypes.c_uint16.from_buffer(buf, off + 8 + 2 + 20).value
            ga = GROUP_AFFINITY.from_buffer(buf, off + 8 + 2 + 20 + 2); mask = ga.Mask
            cores.append({"efficiency_class": int(eff), "smt": bool(flags & 1), "mask": mask, "threads": [i for i in range(64) if mask >> i & 1]})
        off += size
    return cores


def summarize(cores):
    classes = sorted({c["efficiency_class"] for c in cores}, reverse=True); out = {"cores": len(cores), "logical": sum(len(c["threads"]) for c in cores), "classes": {}}
    for cl in classes:
        cs = [c for c in cores if c["efficiency_class"] == cl]; th = sorted(t for c in cs for t in c["threads"]); mask = 0
        for t in th: mask |= 1 << t
        out["classes"][str(cl)] = {"cores": len(cs), "logical_threads": th, "smt": any(c["smt"] for c in cs), "affinity_mask": hex(mask)}
    return out


if __name__ == "__main__":
    c = read(); s = summarize(c); print(json.dumps(s, indent=1));
    if "--cores" in sys.argv: print(json.dumps(c, indent=1))
