"""Joue une partie complète (agents scriptés vs bots/nations du moteur) et rapporte durée et résultat réels."""
import sys, time, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
from ofsi.agents import ExpansionAgent, IdleAgent

def play(map_name="World", seed="play00001", bots=30, nations="default", difficulty="Medium", agent_cls=ExpansionAgent, n_agents=2, max_ticks=40000, decide_every=10, log=True):
    e = OFEnvProc(); t0 = time.time()
    opts = dict(map=map_name, seed=seed, agents=n_agents, bots=bots, nations=nations, difficulty=difficulty)
    r = e.reset(**opts); ag = [agent_cls(i, r["agentIds"][i], rng_seed=i) for i in range(n_agents)]
    c = e.spawn_candidates(); sp = [x for a in ag for x in a.spawn(c)]
    s = e.step(1, sp)
    while s["spawnPhase"]: s = e.step(1)
    tick = s["tick"]; end = None; hist = []
    while tick < max_ticks:
        intents = []
        for a in ag: intents += a.act(tick, e.observe(a.idx))
        s = e.step(decide_every, intents); tick = s["tick"]
        if not s["ok"]: end = "engine_error:" + str(s.get("error"))[:200]; break
        res = e.result()
        alive = [p for p in res["players"] if p["alive"]]
        if tick % 1000 < decide_every: 
            hist.append({"tick": tick, "agent_tiles": [p["tiles"] for p in res["players"] if p["clientID"] in r["agentIds"]], "alive": len(alive)})
            if log: print("tick", tick, hist[-1], flush=True)
        if res["winner"] is not None: end = "winner"; break
    res = e.result(); e.close()
    return {"opts": opts, "agent": agent_cls.name, "ticks": tick, "end": end or "max_ticks", "winner": res["winner"], "wall_s": round(time.time() - t0, 1),
            "agents": [p for p in res["players"] if p["clientID"] in r["agentIds"]], "hist": hist}

if __name__ == "__main__":
    out = play(map_name=sys.argv[1] if len(sys.argv) > 1 else "World", bots=int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    print(json.dumps({k: v for k, v in out.items() if k != "hist"}, indent=1))
