"""PPO a actions masquees (baseline monolithique compacte), curriculum adaptatif, checkpoints atomiques, reprise."""
import os, sys, json, time, hashlib, random, argparse, pathlib, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np, torch, torch.nn as nn
from ofsi.rl import spec
from ofsi.rl.vecenv import VecEnv

STAGES = [dict(map="Onion", bots=3, difficulty="Easy"), dict(map="Onion", bots=6, difficulty="Easy"), dict(map="Onion", bots=10, difficulty="Easy"),
          dict(map="Onion", bots=10, difficulty="Medium"), dict(map="Onion", bots=10, difficulty="Hard"), dict(map="Onion", bots=14, difficulty="Impossible")]


class Policy(nn.Module):
    def __init__(self, hid=256):
        super().__init__()
        self.trunk = nn.Sequential(nn.Linear(spec.OBS_DIM, hid), nn.ReLU(), nn.Linear(hid, hid), nn.ReLU())
        self.t_head = nn.Linear(hid, spec.N_TYPES)
        self.f_head = nn.Linear(hid, len(spec.FRACS))
        self.v_head = nn.Linear(hid, 1)
        self.register_buffer("uses_frac", torch.tensor(spec.USES_FRAC, dtype=torch.float32))

    def forward(self, x, mask):
        h = self.trunk(x)
        tl = self.t_head(h).masked_fill(~mask, -1e9)
        return torch.distributions.Categorical(logits=tl), torch.distributions.Categorical(logits=self.f_head(h)), self.v_head(h).squeeze(-1)

    def evaluate(self, x, mask, at, af):
        dt, df, v = self(x, mask)
        uf = self.uses_frac[at]
        return dt.log_prob(at) + uf * df.log_prob(af), dt.entropy() + uf * df.entropy(), v


class Curriculum:
    """Etape = (carte, nb de bots, difficulte). Monte quand le taux de victoire glissant atteint le seuil ; 20 % de consolidation."""
    def __init__(self, win=40, up=0.6):
        self.stage = 0
        self.hist = collections.deque(maxlen=win)
        self.win, self.up = win, up
        self.log = []

    def sample(self, rng):
        st = self.stage if rng.random() > 0.2 else rng.randrange(0, self.stage + 1)
        return dict(STAGES[st], _stage=st)

    def report(self, info, upd):
        if info["cfg"].get("_stage") != self.stage:
            return
        self.hist.append(1.0 if info["win"] else 0.0)
        if len(self.hist) == self.win and np.mean(self.hist) >= self.up and self.stage < len(STAGES) - 1:
            self.log.append({"update": upd, "from": self.stage, "to": self.stage + 1, "winrate": float(np.mean(self.hist)), "n": self.win})
            self.stage += 1
            self.hist.clear()


def save_ckpt(path, model, opt, st):
    tmp = path + ".tmp"
    torch.save({"model": model.state_dict(), "opt": opt.state_dict(), **st}, tmp)
    h = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
    os.replace(tmp, path)
    open(path + ".sha256", "w").write(h)


def load_ckpt(path):
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if open(path + ".sha256").read().strip() != h:
        raise RuntimeError("checkpoint corrompu : somme de controle differente")
    return torch.load(path, weights_only=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="run0"); ap.add_argument("--envs", type=int, default=16); ap.add_argument("--T", type=int, default=64)
    ap.add_argument("--updates", type=int, default=100000); ap.add_argument("--lr", type=float, default=3e-4); ap.add_argument("--ent", type=float, default=0.01)
    ap.add_argument("--threads", type=int, default=4); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--resume", action="store_true")
    ap.add_argument("--ckpt-every", type=int, default=20)
    a = ap.parse_args()
    torch.set_num_threads(a.threads); torch.manual_seed(a.seed); rng = random.Random(a.seed)
    rd = pathlib.Path("runs") / a.name; rd.mkdir(parents=True, exist_ok=True); latest = str(rd / "ckpt_latest.pt")
    model = Policy(); opt = torch.optim.Adam(model.parameters(), lr=a.lr, eps=1e-5)
    cur = Curriculum(); upd0 = 0; env_steps = 0; t_total = 0.0
    if a.resume and os.path.exists(latest):
        c = load_ckpt(latest)
        model.load_state_dict(c["model"]); opt.load_state_dict(c["opt"])
        upd0, env_steps, t_total = c["update"], c["env_steps"], c["t_total"]
        cur.stage, cur.log = c["stage"], c["cur_log"]
        print(f"reprise depuis update {upd0}, etape curriculum {cur.stage}", flush=True)
    venv = VecEnv(a.envs, lambda: cur.sample(rng)); N, T = a.envs, a.T
    X, M, nbs = venv.featurize()
    gamma, lam = 0.997, 0.95
    metf = open(rd / "metrics.jsonl", "a"); ep_buf = collections.deque(maxlen=200); t_run = time.time(); upd = upd0
    for upd in range(upd0 + 1, a.updates + 1):
        if (rd / "STOP").exists():
            print("STOP demande", flush=True); upd -= 1; break
        while (rd / "PAUSE").exists():
            time.sleep(1)
        t0 = time.time()
        bx = np.zeros((T, N, spec.OBS_DIM), np.float32); bm = np.zeros((T, N, spec.N_TYPES), bool)
        bat = np.zeros((T, N), np.int64); baf = np.zeros((T, N), np.int64)
        blp = np.zeros((T, N), np.float32); bv = np.zeros((T, N), np.float32); br = np.zeros((T, N), np.float32); bd = np.zeros((T, N), np.float32); ends = []
        for t in range(T):
            with torch.no_grad():
                dt, df, v = model(torch.from_numpy(X), torch.from_numpy(M))
                at = dt.sample(); af = df.sample()
                lp = dt.log_prob(at) + model.uses_frac[at] * df.log_prob(af)
            bx[t], bm[t], bat[t], baf[t], blp[t], bv[t] = X, M, at.numpy(), af.numpy(), lp.numpy(), v.numpy()
            rew, done, info = venv.step(at.numpy(), af.numpy(), nbs)
            br[t], bd[t] = rew, done
            for inf in info:
                if inf:
                    ends.append(inf); cur.report(inf, upd); ep_buf.append(inf)
            X, M, nbs = venv.featurize()
        with torch.no_grad():
            _, _, lv = model(torch.from_numpy(X), torch.from_numpy(M))
        adv = np.zeros((T, N), np.float32); last = 0; nv = lv.numpy()
        for t in reversed(range(T)):
            nonterm = 1.0 - bd[t]
            delta = br[t] + gamma * nv * nonterm - bv[t]
            last = delta + gamma * lam * nonterm * last
            adv[t] = last; nv = bv[t]
        ret = adv + bv; B = T * N
        fl = lambda z: torch.from_numpy(z.reshape(B, *z.shape[2:]))
        tx, tm, tat, taf, tlp, tadv, tret = fl(bx), fl(bm), fl(bat), fl(baf), fl(blp), fl(adv), fl(ret)
        tadv = (tadv - tadv.mean()) / (tadv.std() + 1e-8)
        stats = collections.defaultdict(list)
        for ep in range(4):
            perm = torch.randperm(B)
            for i in range(0, B, 256):
                idx = perm[i:i + 256]
                nlp, ent, nv_ = model.evaluate(tx[idx], tm[idx], tat[idx], taf[idx])
                ratio = (nlp - tlp[idx]).exp()
                pg = -torch.min(ratio * tadv[idx], ratio.clamp(0.8, 1.2) * tadv[idx]).mean()
                vl = 0.5 * (nv_ - tret[idx]).pow(2).mean()
                loss = pg + 0.5 * vl - a.ent * ent.mean()
                opt.zero_grad(); loss.backward()
                gn = nn.utils.clip_grad_norm_(model.parameters(), 0.5); opt.step()
                stats["pg"].append(pg.item()); stats["vl"].append(vl.item()); stats["ent"].append(ent.mean().item())
                stats["gn"].append(float(gn)); stats["kl"].append((tlp[idx] - nlp).mean().item())
        env_steps += B; dt_u = time.time() - t0; t_total += dt_u
        at_hist = np.bincount(bat.reshape(-1), minlength=spec.N_TYPES) / B
        rec = {"update": upd, "env_steps": env_steps, "decisions_per_s": round(B / dt_u, 1), "stage": cur.stage, "episodes_finished": len(ends),
               "wins": int(sum(e["win"] for e in ends)),
               "recent200_winrate": (float(np.mean([e["win"] for e in ep_buf])) if ep_buf else None),
               "recent200_mean_return": (float(np.mean([e["ret"] for e in ep_buf])) if ep_buf else None),
               "pg_loss": float(np.mean(stats["pg"])), "v_loss": float(np.mean(stats["vl"])), "entropy": float(np.mean(stats["ent"])),
               "grad_norm": float(np.mean(stats["gn"])), "approx_kl": float(np.mean(stats["kl"])),
               "action_hist": [round(float(x), 4) for x in at_hist], "invalid_build_exec_frac": venv.invalid_exec / max(1, venv.exec_actions),
               "t_total_s": round(t_total, 1), "wall_s": round(time.time() - t_run, 1)}
        metf.write(json.dumps(rec) + "\n"); metf.flush()
        if upd % 5 == 0:
            print({k: rec[k] for k in ("update", "env_steps", "decisions_per_s", "stage", "recent200_winrate", "recent200_mean_return", "entropy")}, flush=True)
        if upd % a.ckpt_every == 0:
            save_ckpt(latest, model, opt, {"update": upd, "env_steps": env_steps, "t_total": t_total, "stage": cur.stage, "cur_log": cur.log})
    save_ckpt(latest, model, opt, {"update": upd, "env_steps": env_steps, "t_total": t_total, "stage": cur.stage, "cur_log": cur.log})
    venv.close()
    print("arret propre, checkpoint sauvegarde", flush=True)


if __name__ == "__main__":
    main()
