"""Lanceur des scenarios de competence (lot 1 + lot 2). Usage : python ofsi/run_skills.py [nom1,nom2,...] [--out fichier.json]"""
import sys, json, pathlib, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import multiprocessing as mp
import ofsi.skills as S
import ofsi.skills2  # noqa: F401  (enregistre le lot 2 dans S.TESTS)
import ofsi.skills3  # noqa: F401  (lot 3 : hypotheses a verifier)


def run(name):
    return S.run_one(name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="?", default="")
    ap.add_argument("--out", default="benchmarks/skills.json")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    names = a.names.split(",") if a.names else list(S.TESTS)
    with mp.Pool(min(a.workers, len(names))) as pool:
        res = pool.map(run, names, chunksize=1)
    pathlib.Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for r in res:
        print(("PASS " if r["passed"] else "FAIL ") + r["skill"].ljust(30), r["evidence"][:300])
    print("PASS", sum(r["passed"] for r in res), "/", len(res))
