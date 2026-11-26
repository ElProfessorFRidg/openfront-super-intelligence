"""PPO v2 : politique hierarchique a pointeurs (PolicyV2), masques exacts, GPU bf16, curriculum par difficulte, checkpoints verifies, reprise.
Initialisations comparables via --init : random | <chemin de checkpoint>. Arret propre : fichier runs/<nom>/STOP ; pause : PAUSE."""
import os, sys, json, time, random, argparse, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import torch
import torch.nn as nn
from ofsi.rl2 import space as S
from ofsi.rl2.model import PolicyV2, collate
from ofsi.rl2.vecenv2 import VecEnv2
from ofsi.rl2 import ckpt
from ofsi.rl2.memguard import wait_ram

MAPS_TRAIN = ["Onion", "Pangaea", "Caucasus", "BosphorusStraits", "Iceland", "BeringStrait", "DanishStraits", "BlackSea"]     # cartes d'ENTRAINEMENT
MAPS_HELDOUT = ["Africa", "Oceania", "MississippiRiver", "AmazonRiver"]                                                        # jamais vues a l'entrainement (validation/test)
STAGES = [dict(difficulty="Easy", bots=(4, 8)), dict(difficulty="Easy", bots=(8, 14)), dict(difficulty="Medium", bots=(6, 10)), dict(difficulty="Medium", bots=(10, 14)),
          dict(difficulty="Hard", bots=(6, 10)), dict(difficulty="Hard", bots=(10, 14)), dict(difficulty="Impossible", bots=(8, 14))]


class Curriculum:
    """Monte d'etape quand le taux de victoire glissant atteint le seuil ; 25 % d'echantillons de consolidation (etapes <= courante)."""
    def __init__(self, win=40, up=0.6, maps=None):
        self.stage, self.hist, self.win, self.up, self.log = 0, collections.deque(maxlen=win), win, up, []
        self.maps = maps or MAPS_TRAIN

    def sample(self, rng):
        st = self.stage if rng.random() > 0.25 else rng.randrange(0, self.stage + 1); c = STAGES[st]
        return {"map": rng.choice(self.maps), "bots": rng.randint(*c["bots"]), "difficulty": c["difficulty"], "_stage": st}

    def report(self, info, upd):
        if info["cfg"].get("_stage") != self.stage: return
        self.hist.append(1.0 if info["win"] else 0.0)
        if len(self.hist) == self.win and np.mean(self.hist) >= self.up and self.stage < len(STAGES) - 1:
            self.log.append({"update": upd, "from": self.stage, "to": self.stage + 1, "winrate": float(np.mean(self.hist)), "n": self.win}); self.stage += 1; self.hist.clear()


def actions_from(out, i):
    A = []
    for k in range(S.M_SUB):
        t = int(out["types"][i, k])
        if t == S.T["STOP"]: break
        A.append((t, int(out["ptrs"][i, k]), int(out["params"][i, k])))
    return A


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="v2_run0"); ap.add_argument("--envs", type=int, default=12); ap.add_argument("--T", type=int, default=64)
    ap.add_argument("--updates", type=int, default=100000); ap.add_argument("--max-decisions", type=int, default=0, help="budget : arret apres N decisions d'environnement (0 = illimite)")
    ap.add_argument("--lr", type=float, default=2.5e-4); ap.add_argument("--ent", type=float, default=0.01); ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--epochs", type=int, default=3); ap.add_argument("--mb", type=int, default=192); ap.add_argument("--gamma", type=float, default=0.997); ap.add_argument("--lam", type=float, default=0.95)
    ap.add_argument("--init", default="random"); ap.add_argument("--value-warmup", type=int, default=0, help="N premieres mises a jour : on n'entraine QUE la tete de valeur (politique gelee) pour ne pas detruire une initialisation pre-entrainee"); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--resume", action="store_true"); ap.add_argument("--ckpt-every", type=int, default=10)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu"); ap.add_argument("--max-steps", type=int, default=1500); ap.add_argument("--stage0", type=int, default=0)
    ap.add_argument("--kl-ref", type=float, default=0.0, help="coefficient de la penalite KL vers la politique INITIALE gelee (ancrage ; 0 = desactive)")
    ap.add_argument("--bc-coef", type=float, default=0.0, help="coefficient de la perte d'imitation auxiliaire sur les demonstrations gagnantes (0 = desactive)"); ap.add_argument("--bc-data", default="data/demos_v3/shard_*.npz"); ap.add_argument("--bc-bs", type=int, default=64)
    a = ap.parse_args(); dev = a.device
    torch.manual_seed(a.seed); np.random.seed(a.seed); rng = random.Random(a.seed)
    if dev == "cuda": torch.backends.cuda.matmul.allow_tf32 = True; torch.backends.cudnn.allow_tf32 = True
    rd = pathlib.Path("runs") / a.name; rd.mkdir(parents=True, exist_ok=True); latest = str(rd / "ckpt_latest.pt")
    model = PolicyV2().to(dev); opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4, eps=1e-6)
    cur = Curriculum(); cur.stage = a.stage0; upd0, steps_total, t_total = 0, 0, 0.0
    if a.resume and os.path.exists(latest):
        c = ckpt.load(latest, dev); model.load_state_dict(c["model"]); opt.load_state_dict(c["opt"]); upd0, steps_total, t_total = c["update"], c["env_steps"], c["t_total"]; cur.stage, cur.log = c["stage"], c["cur_log"]
        print(f"reprise update {upd0}, etape {cur.stage}", flush=True)
    elif a.init != "random":
        c = ckpt.load(a.init, dev); model.load_state_dict(c["model"], strict=False); print(f"initialise depuis {a.init}", flush=True)
    ref = None
    if a.kl_ref > 0:                                    # politique de reference = poids d'initialisation, gelee (jamais mise a jour)
        import copy; ref = copy.deepcopy(model).eval()
        for p_ in ref.parameters(): p_.requires_grad_(False)
    demo = None
    if a.bc_coef > 0:
        from ofsi.rl2.pretrain import Data
        demo = Data(a.bc_data, seed=a.seed); wins = demo.tr[demo.D["win"][demo.tr] == 1]; print(f"imitation auxiliaire : {len(wins)} decisions gagnantes (split train par episode)", flush=True)
    json.dump({"args": vars(a), "init": a.init, "torch": torch.__version__, "device": dev}, open(rd / "config.json", "w"), indent=1)
    wait_ram(0.45 * a.envs + 3.5, tag=" ppo2")       # MESURE : ~0,4 Go par moteur (18 processus Node = 3,3 Go) + ~3,3 Go pour Python/PyTorch + marge
    env = VecEnv2(a.envs, lambda: cur.sample(rng), max_steps=a.max_steps); N, T = a.envs, a.T; metf = open(rd / "metrics.jsonl", "a"); ep_buf = collections.deque(maxlen=200); t_run = time.time()
    obs = env.obs; upd = upd0; amp = dict(device_type="cuda", dtype=torch.bfloat16, enabled=(dev == "cuda"))
    for upd in range(upd0 + 1, a.updates + 1):
        if (rd / "STOP").exists(): print("STOP demande", flush=True); upd -= 1; break
        while (rd / "PAUSE").exists(): time.sleep(1)
        if a.max_decisions and steps_total >= a.max_decisions: print("budget atteint", flush=True); upd -= 1; break
        t0 = time.time(); R = collections.defaultdict(list); ends = []; model.eval()
        for t in range(T):
            batch = collate(obs, dev)
            with torch.no_grad(), torch.autocast(**amp): out = model.act(batch)
            R["obs"].append(obs); R["types"].append(out["types"].cpu()); R["ptrs"].append(out["ptrs"].cpu()); R["params"].append(out["params"].cpu()); R["logp"].append(out["logp"].float().cpu()); R["val"].append(out["value"].float().cpu())
            rew, done, info = env.step([actions_from(out, i) for i in range(N)])
            R["rew"].append(torch.tensor(rew, dtype=torch.float32)); R["done"].append(torch.tensor(done, dtype=torch.float32)); obs = env.obs
            for inf in info:
                if inf: ends.append(inf); ep_buf.append(inf); cur.report(inf, upd)
        with torch.no_grad(), torch.autocast(**amp): last_v = model.act(collate(obs, dev))["value"].float().cpu()
        rew, done, val = torch.stack(R["rew"]), torch.stack(R["done"]), torch.stack(R["val"]); adv = torch.zeros(T, N); lastg = torch.zeros(N); nv = last_v
        for t in reversed(range(T)):
            nt = 1.0 - done[t]; delta = rew[t] + a.gamma * nv * nt - val[t]; lastg = delta + a.gamma * a.lam * nt * lastg; adv[t] = lastg; nv = val[t]
        ret = adv + val; B = T * N; flat = [R["obs"][t][i] for t in range(T) for i in range(N)]
        types, ptrs, params = (torch.stack(R[k]).reshape(B, S.M_SUB) for k in ("types", "ptrs", "params")); old_lp = torch.stack(R["logp"]).reshape(B); adv_f = adv.reshape(B); ret_f = ret.reshape(B)
        adv_f = (adv_f - adv_f.mean()) / (adv_f.std() + 1e-8); st = collections.defaultdict(list); model.train(); t_upd = time.time()
        for ep in range(a.epochs):
            perm = torch.randperm(B)
            for i in range(0, B, a.mb):
                idx = perm[i:i + a.mb].tolist(); mb = collate([flat[j] for j in idx], dev); sel = torch.tensor(idx)
                act = {"types": types[sel].to(dev), "ptrs": ptrs[sel].to(dev), "params": params[sel].to(dev)}
                with torch.autocast(**amp): o = model.act(mb, actions=act)
                lp, en, v = o["logp"].float(), o["entropy"].float(), o["value"].float(); ratio = (lp - old_lp[sel].to(dev)).exp(); A = adv_f[sel].to(dev)
                pg = -torch.min(ratio * A, ratio.clamp(1 - a.clip, 1 + a.clip) * A).mean(); vl = 0.5 * (v - ret_f[sel].to(dev)).pow(2).mean(); loss = (0.5 * vl) if upd <= a.value_warmup else (pg + 0.5 * vl - a.ent * en.mean())      # echauffement : politique gelee, critique seul
                if upd > a.value_warmup and ref is not None:      # ancrage : estimateur k3 de KL(pi || pi_ref) sur les actions echantillonnees
                    with torch.no_grad(), torch.autocast(**amp): rlp = ref.act(mb, actions=act)["logp"].float()
                    lr_ = rlp - lp; kl_ref = (lr_.exp() - 1 - lr_).mean(); loss = loss + a.kl_ref * kl_ref; st["klref"].append(kl_ref.item())
                if upd > a.value_warmup and demo is not None:     # imitation auxiliaire : log-vraisemblance des actions gagnantes de demonstration
                    di = np.sort(np.random.choice(wins, a.bc_bs, replace=False)); do, dact, _ = demo.batch(di, dev)
                    with torch.autocast(**amp): dl = -model.act(do, actions=dact)["logp"].float().mean()
                    loss = loss + a.bc_coef * dl; st["bc"].append(dl.item())
                opt.zero_grad(set_to_none=True); loss.backward(); gn = nn.utils.clip_grad_norm_(model.parameters(), 0.5)
                if upd <= a.value_warmup:                                   # echauffement : SEULE la tete de valeur est mise a jour (l'encodeur partage avec la politique reste fige)
                    for n_, p_ in model.named_parameters():
                        if not n_.startswith("value."): p_.grad = None
                opt.step()
                st["pg"].append(pg.item()); st["vl"].append(vl.item()); st["ent"].append(en.mean().item()); st["gn"].append(float(gn)); st["kl"].append((old_lp[sel].to(dev) - lp).mean().item()); st["clipfrac"].append(((ratio - 1).abs() > a.clip).float().mean().item())
        steps_total += B; dt = time.time() - t0; t_total += dt
        th = np.bincount(types.reshape(-1).numpy(), minlength=S.NT) / types.numel()
        rec = {"update": upd, "env_steps": steps_total, "decisions_per_s": round(B / dt, 1), "collect_s": round(t_upd - t0, 1), "train_s": round(time.time() - t_upd, 1), "stage": cur.stage, "episodes_finished": len(ends), "wins": int(sum(e["win"] for e in ends)),
               "recent200_winrate": (float(np.mean([e["win"] for e in ep_buf])) if ep_buf else None), "recent200_mean_return": (float(np.mean([e["ret"] for e in ep_buf])) if ep_buf else None),
               "recent200_progress": (float(np.mean([e["progress"] for e in ep_buf])) if ep_buf else None), "pg_loss": float(np.mean(st["pg"])), "v_loss": float(np.mean(st["vl"])), "entropy": float(np.mean(st["ent"])),
               "grad_norm": float(np.mean(st["gn"])), "approx_kl": float(np.mean(st["kl"])), "clipfrac": float(np.mean(st["clipfrac"])), "kl_ref": (float(np.mean(st["klref"])) if st["klref"] else None), "bc_aux": (float(np.mean(st["bc"])) if st["bc"] else None), "type_hist": [round(float(x), 4) for x in th],
               "invalid_exec_frac": sum(s.invalid_exec for s in env.sess) / max(1, sum(s.exec_n for s in env.sess)), "t_total_s": round(t_total, 1), "wall_s": round(time.time() - t_run, 1)}
        metf.write(json.dumps(rec) + "\n"); metf.flush()
        if upd % 3 == 0: print({k: rec[k] for k in ("update", "env_steps", "decisions_per_s", "stage", "recent200_winrate", "recent200_progress", "recent200_mean_return", "entropy")}, flush=True)
        if not np.isfinite(rec["pg_loss"]) or not np.isfinite(rec["v_loss"]): print("DIVERGENCE (NaN) : arret, dernier checkpoint conserve", flush=True); break
        if upd % a.ckpt_every == 0:
            ckpt.save(latest, {"model": model.state_dict(), "opt": opt.state_dict(), "update": upd, "env_steps": steps_total, "t_total": t_total, "stage": cur.stage, "cur_log": cur.log})
    ckpt.save(latest, {"model": model.state_dict(), "opt": opt.state_dict(), "update": upd, "env_steps": steps_total, "t_total": t_total, "stage": cur.stage, "cur_log": cur.log})
    env.close(); print("arret propre, checkpoint sauvegarde", flush=True)


if __name__ == "__main__":
    main()
