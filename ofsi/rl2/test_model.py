"""Test du reseau v2 : forme des sorties, masques respectes, teacher-forcing coherent, gradients finis, vitesse CPU/GPU."""
import sys, time, torch, numpy as np; sys.path.insert(0, '.')
from ofsi.rl2 import space as S
from ofsi.rl2.model import PolicyV2, collate
rng = np.random.default_rng(0)
def fake(B):
    L = []
    for _ in range(B):
        tm = rng.random(S.NT) < 0.5; tm[0] = True; pm = np.zeros((S.NT, S.NB), bool)
        for t in range(S.NT):
            if t not in S.NO_PTR and tm[t]: pm[t, rng.choice(S.NB, 6, replace=False)] = True
        for t in range(S.NT):
            if t not in S.NO_PTR and not pm[t].any(): tm[t] = False
        L.append({"self": rng.normal(size=S.S_DIM).astype(np.float32), "players": rng.normal(size=(S.N_PLAYERS, S.FP)).astype(np.float32), "pmask": rng.random(S.N_PLAYERS) < 0.5,
                  "units": rng.normal(size=(S.N_UNITS, S.FU)).astype(np.float32), "umask": rng.random(S.N_UNITS) < 0.3, "atts": rng.normal(size=(S.N_ATT, S.FA)).astype(np.float32), "amask": rng.random(S.N_ATT) < 0.3,
                  "bank": rng.normal(size=(S.NB, S.FC)).astype(np.float32), "bmask": np.ones(S.NB, bool), "type_mask": tm, "ptr_mask": pm, "grid": rng.random((4, S.G, S.G)).astype(np.float32)})
    return L
if __name__ == "__main__":
    for dev in ["cpu"] + (["cuda"] if torch.cuda.is_available() else []):
        m = PolicyV2().to(dev); n = sum(p.numel() for p in m.parameters()); o = collate(fake(16), dev)
        with torch.no_grad(): r = m.act(o)
        # 1) masques respectes
        ok = True
        for b in range(16):
            used = set()
            for k in range(S.M_SUB):
                t = int(r["types"][b, k]); 
                if t != 0:
                    ok &= bool(o["type_mask"][b, t]) and t not in used; used.add(t)
                    if t not in S.NO_PTR: ok &= bool(o["ptr_mask"][b, t, int(r["ptrs"][b, k])])
        # 2) teacher forcing : meme logp
        with torch.no_grad(): r2 = m.act(o, actions={"types": r["types"], "ptrs": r["ptrs"], "params": r["params"]})
        same = torch.allclose(r["logp"], r2["logp"], atol=1e-4)
        # 3) gradients
        m.train(); r3 = m.act(o, actions={"types": r["types"], "ptrs": r["ptrs"], "params": r["params"]}); (r3["logp"].mean() + r3["value"].mean() - 0.01 * r3["entropy"].mean()).backward()
        gfin = all(torch.isfinite(p.grad).all() for p in m.parameters() if p.grad is not None)
        ob = collate(fake(256), dev); torch.cuda.synchronize() if dev == "cuda" else None
        with torch.autocast(dev, dtype=torch.bfloat16, enabled=(dev == "cuda")):
            t0 = time.perf_counter(); 
            for _ in range(5): rr = m.act(ob, actions={"types": torch.zeros(256, 3, dtype=torch.long, device=dev), "ptrs": torch.zeros(256, 3, dtype=torch.long, device=dev), "params": torch.zeros(256, 3, dtype=torch.long, device=dev)}); rr["logp"].mean().backward()
            torch.cuda.synchronize() if dev == "cuda" else None; dt = (time.perf_counter() - t0) / 5
        print(f"[{dev}] params={n/1e6:.2f}M masques_ok={ok} teacher_forcing_ok={same} grads_finis={gfin} train_step(batch256)={dt*1000:.0f} ms | logp moyen={r['logp'].mean():.2f}")
