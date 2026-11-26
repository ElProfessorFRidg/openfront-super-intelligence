"""Pretrain par imitation du professeur (amorcage) avec split train/validation par blocs (pas de fuite entre pas voisins d'une meme partie)."""
import sys, pathlib, argparse, json, numpy as np, torch, torch.nn as nn
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ofsi.rl import spec
from ofsi.rl.ppo import Policy, save_ckpt

ap = argparse.ArgumentParser(); ap.add_argument("--data", default="data/demos_v1.npz"); ap.add_argument("--out", default="runs/bc_v1"); ap.add_argument("--epochs", type=int, default=30); ap.add_argument("--envs", type=int, default=16)
a = ap.parse_args(); torch.manual_seed(0); torch.set_num_threads(4)
d = np.load(a.data); X, M, T, F = map(torch.from_numpy, (d["x"], d["m"], d["t"], d["f"])); n = len(X)
# les echantillons sont ordonnes par pas puis par env : un bloc contigu de pas = sequences completes -> validation sur les 15 % de pas finaux
cut = int(n * 0.85) // a.envs * a.envs; tr, va = slice(0, cut), slice(cut, n)
model = Policy(); opt = torch.optim.Adam(model.parameters(), lr=1e-3); hist = []
def metrics(sl):
    with torch.no_grad():
        dt, df, _ = model(X[sl], M[sl]); acc = (dt.logits.argmax(-1) == T[sl]).float().mean().item()
        uf = model.uses_frac[T[sl]]; facc = ((df.logits.argmax(-1) == F[sl]).float() * uf).sum().item() / max(1.0, uf.sum().item())
        return acc, facc
for ep in range(a.epochs):
    perm = torch.randperm(cut)
    for i in range(0, cut, 256):
        idx = perm[i:i + 256]; dt, df, _ = model(X[idx], M[idx]); uf = model.uses_frac[T[idx]]
        loss = -dt.log_prob(T[idx]).mean() - (uf * df.log_prob(F[idx])).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    ta, tf = metrics(tr); va_, vf = metrics(va); hist.append({"epoch": ep, "train_type_acc": ta, "val_type_acc": va_, "train_frac_acc": tf, "val_frac_acc": vf})
    if ep % 5 == 4 or ep == a.epochs - 1: print(hist[-1], flush=True)
pathlib.Path(a.out).mkdir(parents=True, exist_ok=True)
save_ckpt(a.out + "/ckpt_latest.pt", model, opt, {"update": 0, "env_steps": 0, "t_total": 0.0, "stage": 0, "cur_log": []})
json.dump({"n": n, "n_train": cut, "n_val": n - cut, "hist": hist}, open(a.out + "/bc_report.json", "w"), indent=1)
