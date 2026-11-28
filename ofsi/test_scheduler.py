"""Tests de l'ordonnanceur avec de VRAIS sous-processus (sleep) : budget de coeurs jamais depasse, priorite, blocage RAM, STOP, erreur de configuration."""
import os, sys, tempfile, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
T = tempfile.mkdtemp(); os.environ["OFSI_SCHED"] = T
import ofsi.scheduler as S
ok = []
def check(n, c): ok.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
J = lambda n, c, pr=0, ram=0.1, d=1.0: {"name": n, "cmd": ["sleep", str(d)], "cores": c, "ram_gb": ram, "priority": pr}
# 1. budget de coeurs : 6 travaux de 2 coeurs, budget 4 -> jamais plus de 4 coeurs reserves, au plus 2 travaux simultanes
tr = []; t0 = time.time(); res = S.run_jobs([J(f"j{i}", 2) for i in range(6)], cores=4, trace=tr); el = time.time() - t0
check("tous les travaux termines avec code 0", len(res) == 6 and all(r["code"] == 0 for r in res)); check("budget de coeurs jamais depasse (max reserve=%d)" % max(u for _, u, _ in tr), max(u for _, u, _ in tr) <= 4)
check("parallelisme reel (2 simultanes ; duree %.1fs < sequentiel 6s)" % el, max(n for _, _, n in tr) == 2 and el < 5.0)
# 2. priorite : le travail prioritaire demarre avant les autres
res = S.run_jobs([J("bas", 4, 0, d=0.3), J("haut", 4, 9, d=0.3), J("moyen", 4, 5, d=0.3)], cores=4); order = [r["name"] for r in sorted(res, key=lambda r: r["start"])]; check("ordre de priorite " + str(order), order == ["haut", "moyen", "bas"])
# 3. RAM : memoire libre simulee insuffisante -> attente, puis lancement quand la RAM revient
state = {"ram": 1.0, "calls": 0}
def ram(): state["calls"] += 1; state["ram"] = 1.0 if state["calls"] < 6 else 50.0; return state["ram"]
tr = []; t0 = time.time(); res = S.run_jobs([J("gros", 1, 0, ram=10.0, d=0.2), J("deuxieme", 1, 0, ram=10.0, d=0.2)], cores=4, reserve_gb=2.0, poll=0.2, ram_fn=ram)
check("blocage RAM : lance apres le retour de la memoire (%d appels de mesure)" % state["calls"], len(res) == 2 and state["calls"] >= 6)
# 4. erreur de configuration : travail plus gros que le budget
try: S.run_jobs([J("trop", 8)], cores=4); err = False
except ValueError: err = True
check("travail > budget de coeurs : erreur explicite", err)
# 5. STOP : aucun lancement apres STOP
(pathlib.Path(T) / "STOP").write_text("1"); res = S.run_jobs([J("jamais", 1)], cores=4); check("STOP : aucun travail lance", res == []); os.remove(pathlib.Path(T) / "STOP")
# 6. echec d'un travail : code non nul rapporte, les autres continuent
res = S.run_jobs([{"name": "echec", "cmd": ["false"], "cores": 1, "ram_gb": 0.1, "priority": 1}, J("suite", 1, 0, d=0.2)], cores=4); d = {r["name"]: r["code"] for r in res}; check("echec rapporte (code %s) sans bloquer les autres" % d.get("echec"), d.get("echec") == 1 and d.get("suite") == 0)
print(f"{sum(ok)}/{len(ok)} PASS"); sys.exit(0 if all(ok) else 1)
