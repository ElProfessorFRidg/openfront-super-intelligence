"""Preentrainement v2 : 3 methodes comparables a budget identique.
  bc   : imitation FILTREE (episodes gagnants uniquement, poids configurable pour les perdants)
  ssl  : auto-supervise 'modele du monde leger' sur TOUTES les trajectoires (gagnantes ET perdantes) : predit les consequences des actions
  both : multi-tache bc + ssl
Split train/validation PAR EPISODE (aucune fuite entre pas d'une meme partie)."""
import sys, glob, json, time, pathlib, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from ofsi.rl2 import space as S, ckpt
from ofsi.rl2.model import PolicyV2
from ofsi.rl2.collect_v2 import F16, unpack

SELF_IDX = [0, 1, 2, 3, 4, 5, 16, 17, 18]            # gold, troupes, troupes/max, part de terre, progres victoire, frontiere, attaque entrante, sortante, joueurs restants
HORIZONS = (1, 5, 20)


def load_all(pattern):
    shards = [np.load(p) for p in sorted(glob.glob(pattern))]
    keys = list(shards[0].keys()); D = {k: np.concatenate([s[k] for s in shards]) for k in keys}
    return D


class Data:
    def __init__(self, pattern, val_frac=0.15, seed=0):
        self.D = load_all(pattern); n = len(self.D["ep"]); eps = np.unique(self.D["ep"]); rng = np.random.default_rng(seed); rng.shuffle(eps)
        nv = max(1, int(len(eps) * val_frac)); self.val_eps = set(eps[:nv].tolist()); isval = np.array([e in self.val_eps for e in self.D["ep"]])
        self.tr, self.va = np.flatnonzero(~isval), np.flatnonzero(isval); self.n = n
        # cibles du modele du monde : etat futur a h pas dans le MEME episode
        ep, selfv = self.D["ep"], self.D["self"].astype(np.float32)[:, SELF_IDX]; self.fut = np.zeros((n, len(HORIZONS), len(SELF_IDX)), np.float32); self.fmask = np.zeros((n, len(HORIZONS)), bool)
        for hi, h in enumerate(HORIZONS):
            ok = np.zeros(n, bool); ok[:-h] = ep[:-h] == ep[h:]; self.fmask[:, hi] = ok
            self.fut[:-h, hi] = np.where(ok[:-h, None], selfv[h:] - selfv[:-h], 0.0)
        self.eps_tr = len(eps) - nv; self.eps_va = nv

    def batch(self, idx, dev):
        o = {k: torch.from_numpy(self.D[k][idx].astype(np.float32)).to(dev) for k in F16}
        for k, n in (("pmask", S.N_PLAYERS), ("umask", S.N_UNITS), ("amask", S.N_ATT), ("bmask", S.NB), ("type_mask", S.NT)): o[k] = torch.from_numpy(np.unpackbits(self.D[k][idx], axis=1)[:, :n].astype(bool)).to(dev)
        o["ptr_mask"] = torch.from_numpy(np.unpackbits(self.D["ptr_mask"][idx], axis=1)[:, :S.NT * S.NB].reshape(len(idx), S.NT, S.NB).astype(bool)).to(dev)
        act = {k: torch.from_numpy(self.D[k][idx].astype(np.int64)).to(dev) for k in ("types", "ptrs", "params")}
        extra = {"fut": torch.from_numpy(self.fut[idx]).to(dev), "fmask": torch.from_numpy(self.fmask[idx]).to(dev), "ret": torch.from_numpy(self.D["ret"][idx]).to(dev), "win": torch.from_numpy(self.D["win"][idx].astype(np.float32)).to(dev)}
        return o, act, extra


class WorldHead(nn.Module):
    """Predit, a partir du contexte et des actions executees : variation des grandeurs cles a 1/5/20 decisions, probabilite de victoire de la partie, retour actualise."""
    def __init__(self, d):
        super().__init__(); self.net = nn.Sequential(nn.Linear(2 * d, 2 * d), nn.GELU(), nn.Linear(2 * d, 2 * d), nn.GELU()); self.fut = nn.Linear(2 * d, len(HORIZONS) * len(SELF_IDX)); self.win = nn.Linear(2 * d, 1); self.ret = nn.Linear(2 * d, 1)

    def forward(self, ctx, act_emb): h = self.net(torch.cat([ctx, act_emb], -1)); return self.fut(h).view(-1, len(HORIZONS), len(SELF_IDX)), self.win(h).squeeze(-1), self.ret(h).squeeze(-1)


def run(a):
    dev = "cuda" if torch.cuda.is_available() else "cpu"; torch.manual_seed(a.seed); np.random.seed(a.seed); t0 = time.time()
    data = Data(a.data, seed=a.seed); print(f"donnees: {data.n} decisions, episodes train/val = {data.eps_tr}/{data.eps_va} ; victoires dans l'ensemble: {int((data.D['last'] == 1).sum() and data.D['win'][data.D['last'] == 1].sum())} / {int((data.D['last'] == 1).sum())} episodes", flush=True)
    model = PolicyV2().to(dev); wh = WorldHead(model.d).to(dev); params = list(model.parameters()) + (list(wh.parameters()) if a.method in ("ssl", "both") else [])
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=1e-4); amp = dict(device_type="cuda", dtype=torch.bfloat16, enabled=(dev == "cuda"))
    w_ep = np.where(data.D["win"] == 1, 1.0, a.loser_weight).astype(np.float32)               # poids par decision (filtrage)
    tr = data.tr if a.method in ("ssl", "both") else data.tr[w_ep[data.tr] > 0]             # bc seul : on retire les decisions de poids nul ; "both" : TOUTES les trajectoires (le terme BC est pondere par w, le modele du monde apprend aussi des defaites)
    print(f"methode={a.method} decisions d'entrainement utilisees={len(tr)} (poids perdants={a.loser_weight})", flush=True); hist = []

    def losses(idx, train):
        o, act, ex = data.batch(idx, dev); w = torch.from_numpy(w_ep[idx]).to(dev); out = {}
        with torch.autocast(**amp):
            r = model.act(o, actions=act); ctx, _, _ = model.encode(o)
            if a.method in ("bc", "both"): out["bc"] = -(r["logp"].float() * w).sum() / w.sum().clamp(min=1e-6)
            if a.method in ("ssl", "both"):
                emb = sum(model.type_emb(act["types"][:, k]) for k in range(S.M_SUB)); fut, wl, rt = wh(ctx, emb)
                m = ex["fmask"].float().unsqueeze(-1); out["wm_fut"] = (F.smooth_l1_loss(fut.float(), ex["fut"], reduction="none") * m).sum() / (m.sum() * len(SELF_IDX)).clamp(min=1)
                out["wm_win"] = a.wm_win_weight * F.binary_cross_entropy_with_logits(wl.float(), ex["win"]); out["wm_ret"] = F.smooth_l1_loss(rt.float(), ex["ret"])
        return out

    steps_done = 0; n_ep = a.epochs if not a.steps else 10**6; best = {"val": float("inf"), "epoch": -1, "state": None, "wh": None}
    for ep in range(n_ep):
        model.train(); perm = np.random.permutation(tr); acc = {}
        for i in range(0, len(perm), a.bs):
            idx = np.sort(perm[i:i + a.bs]); L = losses(idx, True); loss = sum(v for v in L.values()); opt.zero_grad(set_to_none=True); loss.backward(); nn.utils.clip_grad_norm_(params, 1.0); opt.step(); steps_done += 1
            for k, v in L.items(): acc.setdefault(k, []).append(v.item())
            if a.steps and steps_done >= a.steps: break
        model.eval(); vacc = {}
        with torch.no_grad():
            for i in range(0, len(data.va), a.bs):
                idx = data.va[i:i + a.bs]; L = losses(np.sort(idx), False)
                for k, v in L.items(): vacc.setdefault(k, []).append(v.item())
        if a.select == "bc": vtot = float(np.mean(vacc["bc"]))                                                          # objectif de politique
        elif a.select == "dyn": vtot = float(np.mean(vacc["wm_fut"])) + float(np.mean(vacc["wm_ret"]))                  # dynamique (hors tete victoire)
        else: vtot = sum(float(np.mean(v)) for v in vacc.values())
        if vtot < best["val"]: best.update(val=vtot, epoch=ep, state={k: v.detach().cpu().clone() for k, v in model.state_dict().items()})
        rec = {"epoch": ep, "steps": steps_done, "val_total": vtot, **{"train_" + k: float(np.mean(v)) for k, v in acc.items()}, **{"val_" + k: float(np.mean(v)) for k, v in vacc.items()}}; hist.append(rec); print({k: round(v, 4) for k, v in rec.items()}, flush=True)
        if a.steps and steps_done >= a.steps: break
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if best["state"] is not None: model.load_state_dict(best["state"]); print(f"checkpoint retenu = MEILLEURE validation : epoque {best['epoch']} (val_total={best['val']:.4f}) ; derniere epoque={ep}", flush=True)
    ckpt.save(str(out / "ckpt_latest.pt"), {"model": model.state_dict(), "update": 0, "env_steps": 0, "t_total": time.time() - t0, "stage": 0, "cur_log": [], "pretrain": {"method": a.method, "best_epoch": best["epoch"], "best_val": best["val"], "hist": hist, "n_train": int(len(tr)), "loser_weight": a.loser_weight}}, keep=0)
    json.dump({"method": a.method, "hist": hist, "seconds": round(time.time() - t0), "data": a.data, "n_train_decisions": int(len(tr))}, open(out / "pretrain_report.json", "w"), indent=1); print("checkpoint:", out / "ckpt_latest.pt")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--method", choices=["bc", "ssl", "both"], required=True); ap.add_argument("--data", default="data/demos_v2/shard_*.npz"); ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=8); ap.add_argument("--bs", type=int, default=256); ap.add_argument("--lr", type=float, default=3e-4); ap.add_argument("--loser-weight", type=float, default=0.0); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--select", choices=["total", "bc", "dyn"], default="total"); ap.add_argument("--wm-win-weight", type=float, default=1.0); ap.add_argument("--steps", type=int, default=0, help="nombre TOTAL de pas d'optimisation (comparaison a budget identique)")
    run(ap.parse_args())
