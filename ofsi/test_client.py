import time, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
e = OFEnvProc(); t = time.time()
r = e.reset(map="World", seed="pytest001", agents=2, bots=50); print("reset", round(time.time() - t, 2), "s", r["mapW"], r["mapH"], r["agentIds"])
cands = e.spawn_candidates(); print("spawn candidates:", len(cands))
spawn = [{"type": "spawn", "tile": cands[len(cands) * (i + 1) // 3], "clientID": r["agentIds"][i]} for i in range(2)]
t = time.time(); n = 0; s = e.step(1, spawn); n = 1
while s["spawnPhase"]:
    s = e.step(1); n += 1
print("spawn phase ticks", n, "in", round(time.time() - t, 2), "s, tick", s["tick"])
t = time.time(); s = e.step(300); dt = time.time() - t
print("300 ticks:", round(dt, 2), "s ->", round(300 / dt), "ticks/s via IPC; ok", s["ok"])
o = e.observe(0); print("obs self gold/troops/tiles:", o["self"]["gold"], o["self"]["troops"], o["self"]["tiles"], "| others:", len(o["others"]))
sn = e.snapshot(); e.step(100); h1 = e.result()["hash"]; e.restore(sn); e.step(100); h2 = e.result()["hash"]
print("restore replay hash equal:", h1 == h2, h1)
e.close()
