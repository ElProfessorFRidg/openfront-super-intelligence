"""Optimisations GPU mesurees sur l'encodeur d'ensemble (attention) : fp32, TF32, fp16 autocast, bf16 autocast. Releve aussi temperature/puissance GPU."""
import time, json, subprocess, torch, torch.nn as nn
torch.manual_seed(0); dev = "cuda"
class A(nn.Module):
    def __init__(s):
        super().__init__(); s.inp = nn.Linear(32, 256); l = nn.TransformerEncoderLayer(256, 8, 1024, batch_first=True, norm_first=True); s.enc = nn.TransformerEncoder(l, 4, enable_nested_tensor=False); s.out = nn.Linear(256, 40)
    def forward(s, x): return s.out(s.enc(s.inp(x)).mean(1))
def smi():
    r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu,power.draw,clocks.sm,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip(); return r
def bench(mode, iters=40, B=256):
    torch.backends.cuda.matmul.allow_tf32 = mode == "tf32"; torch.backends.cudnn.allow_tf32 = mode == "tf32"
    m = A().to(dev); opt = torch.optim.Adam(m.parameters(), 3e-4); x = torch.randn(B, 56, 32, device=dev); sc = torch.amp.GradScaler(enabled=(mode == "fp16"))
    dt = {"fp16": torch.float16, "bf16": torch.bfloat16}.get(mode)
    def step():
        with torch.autocast("cuda", dtype=dt, enabled=dt is not None): l = m(x).float().pow(2).mean()
        opt.zero_grad(); sc.scale(l).backward(); sc.step(opt); sc.update()
    for _ in range(5): step()
    torch.cuda.synchronize(); t = time.perf_counter()
    for _ in range(iters): step()
    torch.cuda.synchronize(); tr = (time.perf_counter() - t) / iters
    with torch.no_grad(), torch.autocast("cuda", dtype=dt, enabled=dt is not None):
        xi = x[:16]; [m(xi) for _ in range(5)]; torch.cuda.synchronize(); t = time.perf_counter(); [m(xi) for _ in range(iters)]; torch.cuda.synchronize(); inf = (time.perf_counter() - t) / iters
    return {"train_step_ms": round(tr * 1000, 1), "train_samples_per_s": round(B / tr), "inference_ms_b16": round(inf * 1000, 2), "smi_temp_C_power_W_clock_util": smi()}
out = {}
for mode in ("fp32", "tf32", "fp16", "bf16"):
    out[mode] = bench(mode); print(mode, out[mode], flush=True)
json.dump(out, open("benchmarks/gpu_opt.json", "w"), indent=1)
