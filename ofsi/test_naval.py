"""Scenario de competence NAVALE : l'agent remplit sa masse terrestre puis envahit une autre masse. Verifie par le moteur (tuiles, masses, victoire possible)."""
import sys, time, random, pathlib, collections; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
e = OFEnvProc(); r = e.reset(map="Onion", seed="naval001x", agents=1, bots=3, difficulty="Easy"); cid = r["agentIds"][0]
c = e.spawn_candidates(); sizes, of = e.landmasses(c); big = max(range(len(sizes)), key=lambda i: sizes[i] if i == 0 else 0)
tile = [t for t, m in zip(c, of) if m == 0][0]          # masse 0 (35 % des terres)
s = e.step_obs(1, [{"type": "spawn", "tile": tile, "clientID": cid}], costs=True)
while s["spawnPhase"]: s = e.step_obs(1, costs=True)
for k in range(120):                                      # expansion terrestre jusqu'a saturation
    s = e.step_obs(40, [{"type": "attack", "targetID": None, "troops": int(s["obs"][0]["self"]["troops"] * 0.3), "clientID": cid}], costs=True)
o = s["obs"][0]["self"]; print("apres expansion terrestre: tuiles", o["tiles"], f"({o['tiles']/s['obs'][0]['landTotal']*100:.1f} %) troupes", o["troops"])
t = time.time(); cands = e.cands("boat", max=24); print(f"candidats navals: {len(cands)} en {(time.time()-t)*1000:.0f} ms")
for cd in cands[:8]: print("  masse", cd["landmass"], cd["landmassSize"], "proprio", cd["ownerType"], "tuiles proprio", cd["ownerTiles"], "src", cd["src"])
if cands:
    tgt = cands[0]; before = o["tiles"]
    s = e.step_obs(10, [{"type": "boat", "dst": tgt["tile"], "troops": int(o["troops"] * 0.5), "clientID": cid}], costs=True)
    for k in range(60): s = e.step_obs(20, costs=True)
    o2 = s["obs"][0]["self"]; sz, of2 = e.landmasses([tgt["tile"]])
    print("apres invasion: tuiles", before, "->", o2["tiles"], "| unites", o2["units"], "| gain", o2["tiles"] - before)
e.close()
