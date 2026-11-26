import sys, time, json, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.client import OFEnvProc
e = OFEnvProc(); r = e.reset(map="Onion", seed="st2test01", agents=1, bots=6, difficulty="Easy"); cid = r["agentIds"][0]
c = e.spawn_candidates(); s = e.step_state(1, [{"type": "spawn", "tile": c[len(c)//2], "clientID": cid}])
while s["state"]["spawnPhase"]: s = e.step_state(1)
for k in range(150): s = e.step_state(40, [{"type": "attack", "targetID": None, "troops": int(s["state"]["self"]["troops"] * 0.3), "clientID": cid}])
st = s["state"]; me = st["self"]; print("self:", {k: me[k] for k in ("gold","troops","maxTroops","tiles","boats","boatsMax","tradingPartners","immune","units")})
print("outgoing", len(st["outgoingAttacks"]), "incoming", len(st["incomingAttacks"]), "| joueurs vus:", len(st["players"]), "| 1er:", {k: v for k, v in st["players"][0].items() if k != "allianceInfo"})
t = time.time(); s2 = e.step_state(1); print(f"step_state: {(time.time()-t)*1000:.1f} ms")
for kind, kw in [("build", dict(unit="City")), ("build", dict(unit="Port")), ("build", dict(unit="Factory")), ("build", dict(unit="DefensePost")), ("upgrade", {}), ("warship", {}), ("nuke", dict(unit="Atom Bomb"))]:
    t = time.time()
    try: cd = e.cands(kind, **kw); print(f"{kind:8s} {kw.get('unit',''):12s} {len(cd):3d} candidats  {(time.time()-t)*1000:6.1f} ms", (json.dumps(cd[0])[:150] if cd else ""))
    except Exception as ex: print(kind, kw, "ERREUR", str(ex)[:200])
e.close()
