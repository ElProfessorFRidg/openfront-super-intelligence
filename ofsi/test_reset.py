import sys, time, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
e = OFEnvProc()
for i in range(4):
    t = time.time(); r = e.reset(map="Onion", seed=f"rst{i:05d}x", agents=1, bots=10); dt = time.time() - t
    c = e.spawn_candidates(); t2 = time.time(); s = e.step_obs(1, [{"type": "spawn", "tile": c[len(c)//2], "clientID": r["agentIds"][0]}])
    n = 1
    while s["spawnPhase"]: s = e.step_obs(1); n += 1
    t3 = time.time(); s = e.step_obs(500); dt3 = time.time() - t3
    print(f"reset#{i}: {dt:.2f}s | spawn phase {time.time()-t2:.2f}s | 500 ticks+obs {dt3:.2f}s ({500/dt3:.0f} t/s) | winner={s['winner']} obs_keys={list(s['obs'][0].keys())[:4]}")
e.close()
