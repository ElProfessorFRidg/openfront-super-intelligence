"""NB : le champ `hash` du demon est un cache (derniere valeur calculee) remis a None par une restauration ; il n'est PAS comparable avant/apres. La preuve d'identite est (a) l'etat de tous les joueurs a l'identique et (b) le hash FINAL apres poursuite de la partie.
Propriete critique du planificateur : l'etat du moteur apres `choose` est IDENTIQUE a celui d'avant (meme hash, meme tick), et la partie continue de maniere identique
avec ou sans planification quand le planificateur ne change pas l'action (margin infinie)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.rl2.env2 import Session
from ofsi.rl2.teacher_v2 import TeacherV2
from ofsi.rl2.planner import Planner
ok = []
def check(n, c): ok.append(bool(c)); print(("PASS " if c else "FAIL ") + n)

def run(margin, plan_every, steps=60):
    s = Session(20, 400); o = s.start({"map": "Onion", "bots": 8, "difficulty": "Medium"}, "plan0001"); te = TeacherV2(seed=3, ally_mode="threats"); pl = Planner({"ally_mode": "threats"}, H=6, every=plan_every, margin=margin)
    hashes = []; viol = 0
    for i in range(steps):
        if o is None: break
        st, costs, cands = s.cur; was = bool(st.get("spawnPhase")); a = te.act(o, st, costs, cands)
        fp = lambda: (lambda r: (r["tick"], tuple((q["id"], q["tiles"], q["troops"], q["gold"], q["alive"]) for q in r["players"])))(s.e.result())
        before = fp(); a2 = pl.choose(s, o, a, i); after = fp()
        if before != after: viol += 1
        r = s.apply(a2)
        if was: s.spawn_wait(); r = s.last
        hashes.append(r["tick"]); o = s.observe()
    final = s.e.result()["hash"]; s.close(); return final, hashes, viol, pl

h_no, t_no, v0, _ = run(1e9, 10**9)           # pas de planification
h_pl, t_pl, v1, p1 = run(1e9, 3)              # planification mais marge infinie : ne change jamais l'action
check("l'etat moteur (tick + tuiles/troupes/or/vivant de TOUS les joueurs) est identique avant/apres la recherche", v1 == 0 and p1.n_plans > 0)
check("marge infinie : la partie est IDENTIQUE a celle sans planification (hash final)", h_no == h_pl and t_no == t_pl)
print(f"plans effectues : {p1.n_plans}")
print(f"{sum(ok)}/{len(ok)} PASS"); sys.exit(0 if all(ok) else 1)
