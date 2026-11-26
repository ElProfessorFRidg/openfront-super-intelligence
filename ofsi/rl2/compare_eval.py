"""Comparaison APPARIEE de deux evaluations eval2 (memes specs `_id`/`_seed`) : victoires par difficulte, McNemar exact bilateral. Usage : compare_eval.py A.json B.json"""
import sys, json, math
def mcnemar(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c); p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n; return min(1.0, 2 * p)
def load(f): d = json.load(open(f)); return {p["cfg"]["_id"]: p for p in d["parties"]}, d
if __name__ == "__main__":
    A, da = load(sys.argv[1]); B, db = load(sys.argv[2]); common = sorted(set(A) & set(B)); print(f"A={sys.argv[1]}\nB={sys.argv[2]}\nparties communes : {len(common)}")
    for diff in ("Easy", "Medium", "ALL"):
        ids = [i for i in common if diff == "ALL" or A[i]["cfg"]["difficulty"] == diff]
        wa = sum(A[i]["win"] for i in ids); wb = sum(B[i]["win"] for i in ids); b = sum(1 for i in ids if B[i]["win"] and not A[i]["win"]); c = sum(1 for i in ids if A[i]["win"] and not B[i]["win"])
        print(f"  {diff:7s} n={len(ids):2d}  A {wa:2d}  B {wb:2d}  | B gagne/A perd {b:2d}  A gagne/B perd {c:2d}  McNemar exact p={mcnemar(b, c):.3f}")
