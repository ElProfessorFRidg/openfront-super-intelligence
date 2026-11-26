import sys, time, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
e = OFEnvProc(); r = e.reset(map="Onion", seed="bld00001x", agents=1, bots=10); cid = r["agentIds"][0]
c = e.spawn_candidates(); s = e.step_obs(1, [{"type": "spawn", "tile": c[len(c)//2], "clientID": cid}], costs=True)
while s["spawnPhase"]: s = e.step_obs(1, costs=True)
for k in range(40): s = e.step_obs(50, [{"type": "attack", "targetID": None, "troops": 20000, "clientID": cid}], costs=True)
o = s["obs"][0]; print("gold", o["self"]["gold"], "tiles", o["self"]["tiles"], "costs", o["costs"], "landTotal", o["landTotal"])
for u in ["City", "Port", "Defense Post", "Factory", "SAM Launcher", "Warship"]:
    t = time.time(); tl = e.build_tiles(u); print(u, "tiles", tl[:3], f"{(time.time()-t)*1000:.1f} ms")
tile = e.build_tiles("City")[0]; g0 = o["self"]["gold"]
s = e.step_obs(20, [{"type": "build_unit", "unit": "City", "tile": tile, "clientID": cid}], costs=True); o2 = s["obs"][0]
print("après build City: gold", g0, "->", o2["self"]["gold"], "units", o2["self"]["units"])
t = time.time(); [e.step_obs(1, costs=True) for _ in range(20)]; print(f"step_obs(costs) 1 tick: {(time.time()-t)/20*1000:.1f} ms/appel")
e.close()
