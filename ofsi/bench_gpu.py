"""Mesure REELLE CPU vs GPU : inference (batch de decisions) et entrainement (PPO-like) pour un petit MLP et un reseau plus gros."""
import time, sys, json, torch, torch.nn as nn

def sync(d):
    if d == "cuda": torch.cuda.synchronize()

def make(kind):
    if kind == "mlp256":  return nn.Sequential(nn.Linear(113,256), nn.ReLU(), nn.Linear(256,256), nn.ReLU(), nn.Linear(256,40))
    if kind == "mlp1024": return nn.Sequential(nn.Linear(113,1024), nn.ReLU(), nn.Linear(1024,1024), nn.ReLU(), nn.Linear(1024,1024), nn.ReLU(), nn.Linear(1024,40))
    if kind == "attn":    # encodeur d'ensemble (24 joueurs + 32 unites) type transformer
        class A(nn.Module):
            def __init__(s):
                super().__init__(); s.inp = nn.Linear(32, 256); l = nn.TransformerEncoderLayer(256, 8, 1024, batch_first=True, norm_first=True); s.enc = nn.TransformerEncoder(l, 4); s.out = nn.Linear(256, 40)
            def forward(s, x): return s.out(s.enc(s.inp(x)).mean(1))
        return A()

def run(kind, dev, batch_inf, batch_train, iters=30):
    torch.manual_seed(0); m = make(kind).to(dev); opt = torch.optim.Adam(m.parameters(), 3e-4)
    shape = (lambda b: (b, 56, 32)) if kind == "attn" else (lambda b: (b, 113))
    xi = torch.randn(*shape(batch_inf), device=dev); xt = torch.randn(*shape(batch_train), device=dev)
    with torch.no_grad():
        for _ in range(5): m(xi)
        sync(dev); t = time.perf_counter()
        for _ in range(iters): m(xi)
        sync(dev); inf = (time.perf_counter() - t) / iters
    for _ in range(3): l = m(xt).pow(2).mean(); opt.zero_grad(); l.backward(); opt.step()
    sync(dev); t = time.perf_counter()
    for _ in range(iters): l = m(xt).pow(2).mean(); opt.zero_grad(); l.backward(); opt.step()
    sync(dev); tr = (time.perf_counter() - t) / iters
    return {"inference_ms": round(inf*1000, 2), "train_step_ms": round(tr*1000, 2), "inf_samples_per_s": round(batch_inf/inf), "train_samples_per_s": round(batch_train/tr)}

out = {"torch": torch.__version__, "cuda": torch.cuda.is_available(), "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "cpu_threads": torch.get_num_threads(), "results": {}}
for kind in ("mlp256", "mlp1024", "attn"):
    for dev in (["cpu", "cuda"] if torch.cuda.is_available() else ["cpu"]):
        out["results"][f"{kind}/{dev}"] = run(kind, dev, batch_inf=16, batch_train=256)
        print(kind, dev, out["results"][f"{kind}/{dev}"], flush=True)
if torch.cuda.is_available(): out["vram_peak_mb"] = round(torch.cuda.max_memory_allocated() / 2**20)
json.dump(out, open("benchmarks/gpu_vs_cpu.json", "w"), indent=1); print("VRAM pic (Mo):", out.get("vram_peak_mb"))
