"""Diagnostic : trace complete d'une partie du professeur (territoire, troupes, or, voisins, vainqueur)."""
import sys, pathlib, json; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
from ofsi.rl import spec
from ofsi.rl.teacher import teacher_action
seed, bots, diff = sys.argv[1], int(sys.argv[2]), sys.argv[3]
e = OFEnvProc(); r = e.reset(map="Onion", seed=seed, agents=1, bots=bots, difficulty=diff); cid = r["agentIds"][0]
c = e.spawn_candidates(); import random; tile = random.Random(seed).choice(c)
s = e.step_obs(1, [{"type": "spawn", "tile": tile, "clientID": cid}], costs=True)
while s["spawnPhase"]: s = e.step_obs(1, costs=True)
o = s["obs"][0]; n0 = 1 + len(o["others"]); noop_expand = 0; expands = 0; last_tiles = o["self"]["tiles"]; wasted = 0
print("land total", o["landTotal"], "joueurs au depart", n0)
for step in range(1500):
    x, m, nb = spec.featurize(o, n0); t, f = teacher_action(o, nb, m)
    it, _ = spec.decode_intent(o, cid, e, t, f, nb)
    before = o["self"]["tiles"]; s = e.step_obs(20, [it] if it else [], costs=True); o2 = s["obs"][0]
    if t == spec.T_EXPAND:
        expands += 1; wasted += int(o2["self"]["tiles"] <= before) if "self" in o2 else 0
    if step % 75 == 0 and "self" in o2:
        sf = o2["self"]; top = sorted(o2["others"], key=lambda z: -z["tiles"])[:3]
        print(f"t={s['tick']:6d} tiles={sf['tiles']:6d} ({sf['tiles']/o2['landTotal']*100:4.1f}%) troops={sf['troops']:8d} gold={sf['gold']:8d} units={sf['units']} alive={1+len(o2['others'])} border_neighbors={sum(1 for z in o2['others'] if z['border'])} top3={[(z['type'][:3], z['tiles'], z['troops']) for z in top]}")
    o = o2
    if s.get("winner") is not None or "self" not in o or not o["self"]["alive"]: break
res = e.result(); print("FIN tick", s["tick"], "winner", s.get("winner"), "agent id", o.get("self", {}).get("id"), "| expand decisions", expands, "dont sans gain de tuiles", wasted)
w = [p for p in res["players"] if p["id"] == s.get("winner")]; print("vainqueur:", w)
e.close()
