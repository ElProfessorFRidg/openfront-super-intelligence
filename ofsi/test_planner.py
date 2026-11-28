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

# --- injection de pannes : une restauration qui echoue ne doit JAMAIS laisser la partie continuer depuis un etat diverge ---
from ofsi.rl2.planner import PlannerAbort
def faulty(fail_on):
    s = Session(20, 400); o = s.start({"map": "Onion", "bots": 8, "difficulty": "Medium"}, "plan0001"); te = TeacherV2(seed=3, ally_mode="threats"); pl = Planner({"ally_mode": "threats"}, H=4, every=1, margin=0.0)
    for i in range(12):                                                            # avancer hors phase de spawn
        st, costs, cands = s.cur; was = bool(st.get("spawnPhase")); r = s.apply(te.act(o, st, costs, cands))
        if was: s.spawn_wait()
        o = s.observe()
    st, costs, cands = s.cur; a = te.act(o, st, costs, cands); real = s.e.restore; calls = [0]
    def wrapped(snap):
        calls[0] += 1
        if calls[0] == fail_on: raise RuntimeError("SnapshotError simule")
        return real(snap)
    s.e.restore = wrapped; fp = lambda: (lambda r: (r["tick"], tuple((q["id"], q["tiles"], q["troops"], q["gold"]) for q in r["players"])))(s.e.result()); before = fp()
    try: out = pl.choose(s, o, a, 0); exc = None
    except PlannerAbort as e: out, exc = None, e
    s.e.restore = real; after = fp(); s.close(); return pl, out, exc, before == after, a
pl, out, exc, same, a = faulty(1)        # 1er appel = validation du snapshot
check("snapshot invalide (validation) : pas de planification, action du professeur renvoyee, etat intact", exc is None and out == a and same and pl.n_snap_invalid == 1 and pl.n_plans == 0)
pl, out, exc, same, a = faulty(3)        # echec EN COURS de recherche
check("echec en cours de recherche : PlannerAbort leve (la partie est abandonnee, jamais poursuivie)", isinstance(exc, PlannerAbort))
print(f"{sum(ok)}/{len(ok)} PASS"); sys.exit(0 if all(ok) else 1)
