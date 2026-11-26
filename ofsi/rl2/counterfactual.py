"""Analyse de defaite par EXPERIENCES CONTREFACTUELLES : on rejoue la partie (graine + professeur deterministes), on prend des snapshots EXACTS du moteur, puis depuis chaque snapshot
on compare la suite sous la decision d'origine et sous des decisions alternatives (memes etats, meme graine) apres un horizon fixe. Rien n'est suppose : seul l'ecart mesure compte.
Limite : apres restauration la suite est jouee par un professeur NEUF (meme parametres) ; la comparaison est donc entre alternatives, toutes suivies du meme professeur."""
import sys, json, time, pathlib, argparse, random
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
from ofsi.rl2.env2 import Session
from ofsi.rl2 import space as S
from ofsi.rl2.teacher_v3 import TeacherV3
from ofsi.rl2.vecenv2 import potential

T = S.T


def alternatives(obs, st, cands):
    """Decisions alternatives (premiere decision seulement), toutes LEGALES d'apres les masques : une par grande famille utile."""
    tm, pm, alts = obs["type_mask"], obs["ptr_mask"], {"noop": []}
    sl = lambda t: np.flatnonzero(pm[T[t]])
    pl, po = st["players"], S.OFF["players"][0]
    if tm[T["ATTACK_NEUTRAL"]]: alts["expand_30%"] = [(T["ATTACK_NEUTRAL"], 0, 2)]
    if tm[T["ATTACK_PLAYER"]]:
        j = min(sl("ATTACK_PLAYER"), key=lambda j: pl[j - po]["troops"]); alts["attaque_plus_faible_50%"] = [(T["ATTACK_PLAYER"], int(j), 3)]
    if tm[T["BUILD_Defense Post"]]: alts["defense_post"] = [(T["BUILD_Defense Post"], int(sl("BUILD_Defense Post")[0]), 0)]
    if tm[T["BUILD_City"]]: alts["city"] = [(T["BUILD_City"], int(sl("BUILD_City")[0]), 0)]
    if tm[T["ALLY_REQUEST"]]:
        j = max(sl("ALLY_REQUEST"), key=lambda j: pl[j - po]["troops"]); alts["alliance_avec_le_plus_fort"] = [(T["ALLY_REQUEST"], int(j), 0)]
    if tm[T["CANCEL_ATTACK"]]: alts["rappel_attaque"] = [(T["CANCEL_ATTACK"], int(sl("CANCEL_ATTACK")[0]), 0)]
    if tm[T["BOAT"]]: alts["bateau_50%"] = [(T["BOAT"], int(sl("BOAT")[0]), 3)]
    return alts


def resume_from(sess):
    sess.cache = {}; sess.grid_at = -99; sess.last = sess.e.step_state(0); return sess.observe()


def play_from(sess, first_actions, teacher, horizon):
    """Joue `horizon` decisions : la 1re = `first_actions` (ou le professeur si None), puis le professeur. Retourne (progres final, vivant, victoire, decisions jouees)."""
    obs = resume_from(sess); win = False; played = 0
    for k in range(horizon):
        if obs is None: break
        st, costs, cands = sess.cur
        acts = teacher.act(obs, st, costs, cands) if (k > 0 or first_actions is None) else first_actions
        r = sess.apply(acts); played += 1; st2 = r["state"]
        if r.get("winner") is not None: win = ("self" in st2 and r["winner"] == st2["self"]["id"]); break
        obs = sess.observe()
    st = sess.last["state"]; alive = "self" in st and st["self"]["alive"]
    return (potential(st) if alive else 0.0), alive, win, played


def _run_once(sess, cfg, seed, params, teacher_seed, stride, max_steps, max_snaps, snap_from=0):
    obs = sess.start(cfg, seed); te = TeacherV3(seed=teacher_seed, **params); snaps = []; step = 0; end = None
    while step < max_steps:
        if obs is None: end = "mort"; break
        st, costs, cands = sess.cur
        if step >= snap_from and (step - snap_from) % stride == 0 and not st.get("spawnPhase") and len(snaps) < max_snaps:
            alts = alternatives(obs, st, cands); snaps.append({"step": step, "tick": st["tick"], "snap": sess.e.snapshot(), "alts": alts, "progress": potential(st), "tiles": st["self"]["tiles"], "troops": st["self"]["troops"], "maxTroops": st["self"]["maxTroops"], "incoming": sum(a["troops"] for a in st["incomingAttacks"])})
        was_spawn = bool(st.get("spawnPhase")); r = sess.apply(te.act(obs, st, costs, cands)); step += 1
        if was_spawn: sess.spawn_wait()
        if r.get("winner") is not None: end = "victoire" if r["winner"] == r["state"].get("self", {}).get("id") else "defaite_autre_vainqueur"; break
        obs = sess.observe()
    return end or "timeout", step, snaps


def analyze(cfg, seed, params, stride=15, horizon=40, max_steps=1500, max_snaps=12, out=None, tries=8, window=200):
    """Rejoue avec des graines de professeur differentes jusqu'a obtenir une PARTIE PERDUE (mort ou autre vainqueur), puis compare les alternatives depuis ses snapshots."""
    sess = Session(20, max_steps); t0 = time.time(); history = []
    for ts in range(1, tries + 1):
        end, step, snaps = _run_once(sess, cfg, seed, params, ts, stride, max_steps, max_snaps); history.append({"graine_professeur": ts, "fin": end, "decisions": step})
        if end in ("mort", "defaite_autre_vainqueur"):
            # le moteur est deterministe : on REJOUE la meme partie perdue en ne prenant les snapshots que dans les `window` dernieres decisions
            n_lost = step; end, step, snaps = _run_once(sess, cfg, seed, params, ts, stride, max_steps, max_snaps, snap_from=max(1, n_lost - window))
            history.append({"graine_professeur": ts, "fin": end, "decisions": step, "rejeu_snapshots_depuis": max(1, n_lost - window), "identique_a_la_premiere_passe": step == n_lost}); break
    rep = {"cfg": cfg, "seed": seed, "essais": history, "fin": end, "decisions": step, "graine_professeur": ts, "snapshots": []}
    if end not in ("mort", "defaite_autre_vainqueur"): rep["note"] = f"AUCUNE defaite obtenue en {tries} essais : analyse a titre de reference seulement"
    for sn in snaps:
        sess.e.restore(sn["snap"]); base = play_from(sess, None, TeacherV3(seed=ts, **params), horizon)
        row = {"step": sn["step"], "tick": sn["tick"], "progress_avant": round(sn["progress"], 3), "troupes/max": round(sn["troops"] / max(1, sn["maxTroops"]), 2), "attaque_entrante": sn["incoming"], "base": {"progress": round(base[0], 3), "vivant": base[1], "victoire": base[2]}, "alternatives": {}}
        for name, acts in sn["alts"].items():
            sess.e.restore(sn["snap"]); r = play_from(sess, acts, TeacherV3(seed=ts, **params), horizon); row["alternatives"][name] = {"progress": round(r[0], 3), "vivant": r[1], "victoire": r[2], "delta_vs_base": round(r[0] - base[0], 3)}
        rep["snapshots"].append(row)
    sess.close(); rep["secondes"] = round(time.time() - t0)
    if out: pathlib.Path(out).write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--map", default="Onion"); ap.add_argument("--difficulty", default="Medium"); ap.add_argument("--bots", type=int, default=8); ap.add_argument("--seed", default="cf000001")
    ap.add_argument("--params", default='{"rules":[],"ally_mode":"none"}'); ap.add_argument("--stride", type=int, default=15); ap.add_argument("--horizon", type=int, default=40); ap.add_argument("--max-snaps", type=int, default=10); ap.add_argument("--window", type=int, default=200)
    ap.add_argument("--out", default="benchmarks/counterfactual.json"); a = ap.parse_args()
    r = analyze({"map": a.map, "bots": a.bots, "difficulty": a.difficulty}, a.seed, json.loads(a.params), a.stride, a.horizon, max_snaps=a.max_snaps, out=a.out, window=a.window)
    print("essais:", [(h["graine_professeur"], h["fin"], h["decisions"], h.get("identique_a_la_premiere_passe")) for h in r["essais"]])
    print(f"partie analysee: {r['fin']} apres {r['decisions']} decisions ; {len(r['snapshots'])} instants ; {r['secondes']} s ; {r.get('note', '')}")
    for s in r["snapshots"]:
        best = max(s["alternatives"].items(), key=lambda kv: kv[1]["delta_vs_base"]) if s["alternatives"] else None
        print(f"  t={s['tick']:6d} etape {s['step']:4d} progress {s['progress_avant']:.2f} troupes/max {s['troupes/max']:.2f} menace {s['attaque_entrante']:>8d} | base -> {s['base']['progress']:.2f} vivant={s['base']['vivant']} | meilleure alt: {best[0] if best else '-'} ({best[1]['delta_vs_base'] if best else 0:+.2f}, vivant={best[1]['vivant'] if best else '-'})")
