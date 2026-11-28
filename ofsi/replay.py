"""Enregistrement d'une partie decision par decision pour le visualiseur du tableau de bord (MISSION §38). Aucun etat n'est invente : tout vient du moteur.
Chaque image : tick, tuiles/troupes/or de l'agent, adversaires vivants, actions emises (noms), grille grossiere codee en 1 caractere par cellule
(0 mer, 1 terre neutre, 2 moi, 3 allie, 4 ennemi ; majorite des fractions de grid2). Usage : python ofsi/replay.py --agent teacher_threats --map Onion --bots 8 --difficulty Easy --seed rp000001 --name demo"""
import sys, json, time, pathlib, argparse, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.rl2.env2 import Session
from ofsi.rl2.league import make_agent
from ofsi.rl2 import space as S

ROOT = pathlib.Path(__file__).resolve().parents[1]; DIR = ROOT / "runs" / "_replays"


def code_grid(g):
    d, out = g["data"], []
    for i in range(g["gw"] * g["gh"]):
        land, mine, ally, foe = d[4 * i:4 * i + 4]
        if land < 0.15 and mine + ally + foe < 0.15: out.append("0")
        elif mine + ally + foe < 0.15 * max(land, 0.2): out.append("1")
        else: out.append("2" if mine >= ally and mine >= foe else ("3" if ally >= foe else "4"))
    return "".join(out)


def record(agent, cfg, seed, name, max_steps=1500, grid=40, every=1, *, device=None):
    DIR.mkdir(parents=True, exist_ok=True)
    ag = make_agent(agent, device=device)
    sess = Session(20, max_steps)
    try:
        obs = sess.start(cfg, seed)
        frames, step, end, win = [], 0, "timeout", False
        g = None
        # Replay World Plus
        plus = bool(cfg.get("_replay_plus"))
        players = {}
        # Live Dashboard
        live_path = pathlib.Path(os.environ["OFSI_LIVE_PATH"]) if plus and os.environ.get("OFSI_LIVE_PATH") else None
        next_image = time.monotonic()
        history = []
        started = next_update = time.monotonic()
        if plus:
            print(f"{cfg['map']} : {cfg['bots']} bots. Calcul du rejeu...", flush=True)
        while max_steps is None or step < max_steps:
            if obs is None: end = "dead"; break
            st, costs, cands = sess.cur; acts = ag.act(obs, st, costs, cands); was = bool(st.get("spawnPhase")); names = [S.TYPES[t] for t, _, _ in acts]
            r = sess.apply(acts); step += 1
            if not r["ok"]:
                raise RuntimeError(r.get("error") or "erreur du moteur pendant le rejeu")
            if was: sess.spawn_wait(); r = sess.last
            st2 = r["state"]; me = st2.get("self")
            terminal = r.get("winner") is not None or (me is not None and not me["alive"] and not st2.get("spawnPhase"))
            if plus and len(frames) >= 1500:
                every *= 2
                frames = [f for i, f in enumerate(frames) if i == 0 or f["step"] % every == 0]
            keep = step % every == 0 or terminal
            now = time.monotonic()
            stream = live_path is not None and (now >= next_image or terminal)
            if live_path and names:
                history.append({"tick": r.get("tick", 0), "actions": names})
                del history[:-14]
            if keep or stream:
                g = (sess.e.call("replay_view", size=grid) if plus else sess.e.grid2(size=grid))
                if plus:
                    players.update(g["players"])
                frame = {
                    "step": step, "tick": r.get("tick", 0), "tiles": me["tiles"] if me else 0,
                    "troops": int(me["troops"]) if me else 0, "gold": int(me["gold"]) if me else 0,
                    "others": st2.get("nOthersAlive", 0), "actions": names,
                }
                if plus:
                    frame.update(owners=g["owners"], buildings=g["units"], stats=g.get("stats", []),
                                 incoming=st2.get("incomingAttacks", []), outgoing=st2.get("outgoingAttacks", []))
                else:
                    frame["grid"] = code_grid(g)
                if keep:
                    frames.append(frame)
                if stream:
                    state = {"name": name, "cfg": cfg, "seed": seed, "end": "en cours", "frames": [frame],
                             "gw": g["gw"], "gh": g["gh"], "mw": g["width"], "mh": g["height"],
                             "self": g["self"], "players": sorted(players.items()), "history": history}
                    staged_live = live_path.with_suffix(".tmp")
                    try:
                        staged_live.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                        staged_live.replace(live_path)
                    except PermissionError:
                        staged_live.unlink(missing_ok=True)
                    next_image = now + 0.35
            limit_label = f"/{max_steps}" if max_steps is not None else ""
            now = time.monotonic()
            if plus and (now >= next_update or r.get("winner") is not None):
                tiles = me["tiles"] if me else 0
                owned = sum(me.get("units", {}).values()) if me else 0
                print(f"[{now-started:6.1f}s] Decision {step}{limit_label} | tick {r.get('tick', 0)} | "
                      f"{tiles:,} tuiles | {owned} unites | {st2.get('nOthersAlive', 0)} adversaires",
                      flush=True)
                next_update = now + 2.0
            wid = r.get("winner")
            if wid is not None: win = bool(me and wid == me["id"]); end = "win" if win else "loss_winner_other"; break
            if me is not None and not me["alive"] and not st2.get("spawnPhase"): end = "dead"; break
            obs = sess.observe()
        if g is None:
            raise RuntimeError("aucune image de rejeu produite")
        gw, gh = g["gw"], g["gh"]
    finally:
        sess.close()
    rec = {"name": name, "agent": agent, "cfg": cfg, "seed": seed, "end": end, "win": win, "gw": gw, "gh": gh, "frames": frames, "date": time.strftime("%Y-%m-%d %H:%M")}
    if plus:
        rec.update(format=2, players=sorted(players.items()), self=g["self"], mw=g["width"], mh=g["height"])
        print(f"Partie terminee ({end}), sauvegarde de {len(frames)} images...", flush=True)
    output = DIR / f"{name}.json"
    staged = output.with_suffix(".json.tmp")
    try:
        staged.write_text(json.dumps(rec), encoding="utf-8")
        staged.replace(output)
    finally:
        staged.unlink(missing_ok=True)
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--agent", default="teacher_threats"); ap.add_argument("--map", default="Onion"); ap.add_argument("--bots", type=int, default=8); ap.add_argument("--difficulty", default="Easy")
    ap.add_argument("--seed", default="rp000001"); ap.add_argument("--name", default=None); a = ap.parse_args()
    r = record(a.agent, {"map": a.map, "bots": a.bots, "difficulty": a.difficulty}, a.seed, a.name or f"{a.map}_{a.difficulty}_{a.seed}")
    print(f"{r['name']}: {r['end']} en {len(r['frames'])} images, grille {r['gw']}x{r['gh']}")
