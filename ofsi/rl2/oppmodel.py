"""Modele individuel des adversaires (MISSION §24) — supervise, sur les demonstrations (aucun reseau, CPU suffisant).
Pour chaque adversaire (emplacement de joueur stable dans un episode) : a partir de son historique recent et du contexte, predit a h in {5, 20} decisions :
  regression : variation du log-territoire, du log-troupes et de la part de terre ;  evenements : elimination, devient allie, devient traitre (rupture).
Evaluation HONNETE (split par episode, jamais par pas) contre : persistance (delta 0 / taux de base), et ABLATION sans historique (seulement l'etat courant).
Usage : python ofsi/rl2/oppmodel.py --data "data/demos_v3/shard_*.npz" --out runs/oppmodel"""
import sys, glob, json, time, pathlib, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np
import torch, torch.nn as nn

HZ = (5, 20)
REG_F = (0, 1, 3)                     # log tuiles, log troupes, part de terre (indices de player_feat)
F_ALLY, F_TRAITOR = 11, 12
SELF_IDX = [0, 1, 2, 3, 4, 5, 16, 17, 18]


def load(pattern):
    sh = [np.load(p) for p in sorted(glob.glob(pattern))]
    return {k: np.concatenate([s[k] for s in sh]) for k in ("players", "self", "ep", "step")}


def track_ids(P, valid, ep):
    """Identites stables par episode. state2 ne garde que les joueurs VIVANTS (liste compactee a chaque elimination) : on reconstruit l'identite en alignant
    la liste du pas t+1 comme SOUS-SEQUENCE de celle du pas t (l'ordre du moteur est conserve) par DP de cout minimal sur (log tuiles, log troupes, type)."""
    T = len(ep); ids = np.full((T, P.shape[1]), -1, np.int16); nxt = {}
    cost = lambda a, b: abs(a[0] - b[0]) + abs(a[1] - b[1]) + 5.0 * float(np.argmax(a[8:11]) != np.argmax(b[8:11]))
    for t in range(T):
        n = int(valid[t].sum()); e = ep[t]
        if t == 0 or ep[t - 1] != e or n > int(valid[t - 1].sum()):                    # debut d'episode (ou joueurs ajoutes : rare) : nouvelles identites
            base = nxt.get(e, 0) if (t > 0 and ep[t - 1] == e) else 0; ids[t, :n] = np.arange(base, base + n); nxt[e] = base + n; continue
        m = int(valid[t - 1].sum())
        if n == m: ids[t, :n] = ids[t - 1, :n]; continue
        A, B = P[t - 1, :m], P[t, :n]; INF = 1e9; D = np.full((n + 1, m + 1), INF); D[0, :] = 0.0; back = np.zeros((n + 1, m + 1), np.int8)    # D[i,j]: B[:i] sous-sequence de A[:j]
        for i in range(1, n + 1):
            for j in range(i, m + 1):
                skip = D[i, j - 1]; take = D[i - 1, j - 1] + cost(B[i - 1], A[j - 1])
                if take <= skip: D[i, j] = take; back[i, j] = 1
                else: D[i, j] = skip
        i, j, match = n, m, [0] * n
        while i > 0 and j > 0:
            if back[i, j] == 1: match[i - 1] = j - 1; i -= 1; j -= 1
            else: j -= 1
        ids[t, :n] = ids[t - 1, match]
    return ids


def build(D, max_rows=400000, seed=0, history=True):
    """Retourne X, Yreg [n,H,3], Yev [n,H,3], masques Mreg/Mev [n,H,3], ep [n]. Cibles par IDENTITE de joueur (pas par emplacement)."""
    P = D["players"].astype(np.float32); S = D["self"].astype(np.float32)[:, SELF_IDX]; ep = D["ep"]; T = len(ep); valid = np.abs(P).sum(2) > 0
    ids = track_ids(P, valid, ep); NID = int(ids.max()) + 2
    slot_of = np.full((T, NID), -1, np.int16)
    tt, jj = np.nonzero(valid); slot_of[tt, ids[tt, jj]] = jj
    idx_in_ep = np.zeros(T, int); ep_end = np.zeros(T, int)
    for e in np.unique(ep):
        w = np.flatnonzero(ep == e); idx_in_ep[w] = np.arange(len(w)); ep_end[w] = len(w) - 1 - np.arange(len(w))             # nb de pas restants dans l'episode
    rt, rj = np.nonzero(valid & (ep_end > max(HZ))[:, None])                                                                 # lignes dont TOUS les horizons existent dans l'episode
    if len(rt) > max_rows: sel = np.random.default_rng(seed).choice(len(rt), max_rows, replace=False); rt, rj = rt[sel], rj[sel]
    rid = ids[rt, rj].astype(int); cur = P[rt, rj]; feats = [cur]
    if history:
        for k in (1, 5):
            tk = np.maximum(rt - k, 0); okk = (idx_in_ep[rt] >= k); sl = slot_of[tk, rid]; okk &= sl >= 0
            past = np.where(okk[:, None], P[tk, np.maximum(sl, 0)], cur); feats.append(cur - past)
    nact = valid.sum(1).astype(np.float32) / 24.0
    X = np.concatenate(feats + [S[rt], nact[rt, None], idx_in_ep[rt, None].astype(np.float32) / 500.0], 1)
    Yr = np.zeros((len(rt), len(HZ), len(REG_F)), np.float32); Ye = np.zeros((len(rt), len(HZ), 3), np.float32); Mr = np.zeros_like(Yr); Me = np.zeros_like(Ye)
    for hi, h in enumerate(HZ):
        sl = slot_of[rt + h, rid]; alive = sl >= 0; Pf = P[rt + h, np.maximum(sl, 0)]
        for fi, f in enumerate(REG_F): Yr[:, hi, fi] = np.where(alive, Pf[:, f] - cur[:, f], 0.0); Mr[:, hi, fi] = alive
        Ye[:, hi, 0] = ~alive; Me[:, hi, 0] = 1.0
        Ye[:, hi, 1] = alive & (Pf[:, F_ALLY] > 0.5) & (cur[:, F_ALLY] < 0.5); Ye[:, hi, 2] = alive & (Pf[:, F_TRAITOR] > 0.5) & (cur[:, F_TRAITOR] < 0.5); Me[:, hi, 1] = Me[:, hi, 2] = alive
    return X, Yr, Ye, Mr, Me, ep[rt]


class Net(nn.Module):
    def __init__(self, d, hid=192):
        super().__init__(); self.b = nn.Sequential(nn.Linear(d, hid), nn.GELU(), nn.Linear(hid, hid), nn.GELU(), nn.Linear(hid, hid), nn.GELU())
        self.reg = nn.Linear(hid, len(HZ) * len(REG_F)); self.ev = nn.Linear(hid, len(HZ) * 3)
    def forward(self, x): h = self.b(x); return self.reg(h).view(-1, len(HZ), len(REG_F)), self.ev(h).view(-1, len(HZ), 3)


def auc(score, y):
    y = y.astype(bool); n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0: return None
    order = np.argsort(score, kind="mergesort"); ranks = np.empty(len(score)); ranks[order] = np.arange(1, len(score) + 1)
    # rangs moyens pour les ex-aequo
    s_sorted = score[order]; i = 0
    while i < len(s_sorted):
        j = i
        while j + 1 < len(s_sorted) and s_sorted[j + 1] == s_sorted[i]: j += 1
        if j > i: ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2
        i = j + 1
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def lossf(r, ev, R, E, Mr, Me, pw):
    lr = (nn.functional.smooth_l1_loss(r, R, reduction='none') * Mr).sum() / Mr.sum().clamp(min=1)
    le = (nn.functional.binary_cross_entropy_with_logits(ev, E, pos_weight=pw, reduction='none') * Me).sum() / Me.sum().clamp(min=1)
    return lr + le


def fit(Xtr, Rtr, Etr, Mrt, Met, Xva, Rva, Eva, Mrv, Mev, epochs, seed, label):
    torch.manual_seed(seed); mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6; f = lambda a: torch.from_numpy(((a - mu) / sd).astype(np.float32))
    xt, xv = f(Xtr), f(Xva); rt, et, mrt, met = (torch.from_numpy(a) for a in (Rtr, Etr, Mrt, Met)); mrv, mev, rv, ev_ = (torch.from_numpy(a) for a in (Mrv, Mev, Rva, Eva)); net = Net(Xtr.shape[1]); opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=1e-4)
    rate = (Etr * Met).sum(0) / np.maximum(Met.sum(0), 1); pw = torch.from_numpy(np.clip((1 - rate) / np.maximum(rate, 1e-4), 1, 50).astype(np.float32))           # reequilibrage des evenements rares
    best, bs = 1e9, None
    for e in range(epochs):
        net.train(); perm = torch.randperm(len(xt))
        for i in range(0, len(perm), 1024):
            b = perm[i:i + 1024]; r, ev = net(xt[b]); loss = lossf(r, ev, rt[b], et[b], mrt[b], met[b], pw)
            opt.zero_grad(); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad(): r, ev = net(xv); vl = lossf(r, ev, rv, ev_, mrv, mev, pw).item()
        print(f"[{label}] epoch {e} val_loss {vl:.4f}", flush=True)
        if vl < best: best, bs = vl, {k: v.clone() for k, v in net.state_dict().items()}
    net.load_state_dict(bs); net.eval()
    with torch.no_grad(): r, ev = net(xv)
    return net, (mu, sd), r.numpy(), ev.sigmoid().numpy(), best


def report(Rva, Eva, Mrv, Mev, r, ev):
    out = {"regression": {}, "evenements": {}}
    for hi, h in enumerate(HZ):
        for fi, f in enumerate(REG_F):
            m = Mrv[:, hi, fi] > 0; y = Rva[m, hi, fi]; mse = float(np.mean((r[m, hi, fi] - y) ** 2)); base = float(np.mean(y ** 2))            # persistance = predire delta 0
            out["regression"][f"h{h}_feat{f}"] = {"mse": mse, "mse_persistance": base, "gain_vs_persistance": 1 - mse / max(base, 1e-12)}
        for ei, nm in enumerate(("elimination", "devient_allie", "devient_traitre")):
            m = Mev[:, hi, ei] > 0; y = Eva[m, hi, ei]; out["evenements"][f"h{h}_{nm}"] = {"taux_base": float(y.mean()), "positifs": int(y.sum()), "auc": auc(ev[m, hi, ei], y)}
    return out


DIPLO_FLAGS = (19, 20, 21, 22, 23, 24, 25, 26)       # incomingRequest, canAlly, canDonate*, canTarget, canBreak, canEmbargo, canEmoji : drapeaux d'INTERACTION (dependent de mes propres actions)


def run(a):
    torch.set_num_threads(a.threads); t0 = time.time(); D = load(a.data); eps = np.unique(D["ep"]); rng = np.random.default_rng(a.seed); rng.shuffle(eps); val = set(eps[:max(1, int(len(eps) * 0.2))].tolist())
    res = {}
    for name, hist in (("avec_historique", True), ("sans_historique", False)):
        X, R, E, MR, ME, ep = build(D, a.max_rows, a.seed, history=hist)
        if a.drop_diplo:                                              # ablation anti-fuite : on masque les drapeaux d'interaction dans TOUS les blocs de caracteristiques joueur
            for b in range(3 if hist else 1):
                for f in DIPLO_FLAGS: X[:, b * 28 + f] = 0.0
        isv = np.array([e in val for e in ep]); tr, va = ~isv, isv
        print(f"[{name}] lignes train/val = {tr.sum()}/{va.sum()} ; dim={X.shape[1]}", flush=True)
        net, norm, r, ev, best = fit(X[tr], R[tr], E[tr], MR[tr], ME[tr], X[va], R[va], E[va], MR[va], ME[va], a.epochs, a.seed, name); res[name] = report(R[va], E[va], MR[va], ME[va], r, ev); res[name]["n_val"] = int(va.sum()); res[name]["best_val_loss"] = best
        if hist:
            out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True); torch.save({"state": net.state_dict(), "mu": norm[0], "sd": norm[1], "d": X.shape[1]}, out / "oppmodel.pt")
    res["secondes"] = round(time.time() - t0); res["episodes_train_val"] = [len(eps) - len(val), len(val)]
    pathlib.Path(a.out).mkdir(parents=True, exist_ok=True); json.dump(res, open(pathlib.Path(a.out) / "report.json", "w"), indent=1); print(json.dumps(res, indent=1)); return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--data", default="data/demos_v3/shard_*.npz"); ap.add_argument("--out", default="runs/oppmodel"); ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--max-rows", type=int, default=400000); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--threads", type=int, default=1); ap.add_argument("--drop-diplo", action="store_true"); run(ap.parse_args())
