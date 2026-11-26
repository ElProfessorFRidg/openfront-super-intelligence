"""Comparaison appariee (memes parties, seeds fixes) : tableau + McNemar exact bilateral. Usage : compare_paired.py <reference.json> <variante.json>... [--difficulty Medium]"""
import sys, json
from math import comb
args = [a for a in sys.argv[1:] if not a.startswith("--")]; diff = "Medium"
if "--difficulty" in sys.argv: diff = sys.argv[sys.argv.index("--difficulty") + 1]; args = [a for a in args if a != diff]
L = lambda f: json.load(open(f, encoding="utf-8"))
ref = L(args[0]); R = {r["cfg"]["_id"]: r for r in ref["parties"] if r["cfg"]["difficulty"] == diff}
print(f"REFERENCE {args[0].split('/')[-1]} : {sum(r['win'] for r in R.values())}/{len(R)} victoires ({diff}), morts {sum(r['end']=='dead' for r in R.values())}")
for f in args[1:]:
    v = L(f); V = {r["cfg"]["_id"]: r for r in v["parties"] if r["cfg"]["difficulty"] == diff}; ids = [i for i in R if i in V]
    b01 = sum(1 for i in ids if (not R[i]["win"]) and V[i]["win"]); b10 = sum(1 for i in ids if R[i]["win"] and not V[i]["win"]); n = b01 + b10
    p = min(1.0, 2 * sum(comb(n, k) for k in range(0, min(b01, b10) + 1)) / 2 ** n) if n else 1.0
    print(f"  {f.split('/')[-1]:34s} {sum(V[i]['win'] for i in ids):2d}/{len(ids)} victoires | morts {sum(V[i]['end']=='dead' for i in ids):2d} | gagne seulement variante {b01} / seulement ref {b10} | McNemar p={p:.3f} | progression {sum(V[i]['progress'] for i in ids)/max(1,len(ids)):.2f}")
