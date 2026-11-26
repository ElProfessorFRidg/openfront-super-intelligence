import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
from ofsi.rl import spec
e = OFEnvProc(); r = e.reset(map="Onion", seed="ftr00001x", agents=1, bots=10); cid = r["agentIds"][0]
c = e.spawn_candidates(); s = e.step_obs(1, [{"type": "spawn", "tile": c[len(c)//2], "clientID": cid}], costs=True)
while s["spawnPhase"]: s = e.step_obs(1, costs=True)
nbmax = 0
for k in range(60):
    s = e.step_obs(50, [{"type": "attack", "targetID": None, "troops": 15000, "clientID": cid}], costs=True); o = s["obs"][0]
    v, m, nb = spec.featurize(o, 14); nbmax = max(nbmax, len(nb))
print("dim", v.shape, "neighbors max", nbmax, "mask", m.astype(int).tolist(), "finite", bool((v == v).all()))
e.close()
