import sys, torch, numpy as np; sys.path.insert(0, '.')
from ofsi.rl2.test_model import fake
from ofsi.rl2.model import PolicyV2, collate
torch.manual_seed(0); m = PolicyV2().cuda(); o = collate(fake(64), "cuda")
for tf32 in (True, False):
    torch.backends.cudnn.allow_tf32 = tf32; torch.backends.cuda.matmul.allow_tf32 = tf32
    with torch.no_grad():
        r = m.act(o); r2 = m.act(o, actions={"types": r["types"], "ptrs": r["ptrs"], "params": r["params"]}); r3 = m.act(o, actions={"types": r["types"], "ptrs": r["ptrs"], "params": r["params"]})
    d = (r["logp"] - r2["logp"]).abs(); d2 = (r2["logp"] - r3["logp"]).abs()
    print(f"tf32={tf32}: |logp_echantillon - logp_teacherforcing| max={d.max():.2e} moy={d.mean():.2e} | deux passes teacher-forcing identiques: max={d2.max():.2e}")
    ratio = (r2["logp"] - r["logp"]).exp(); print("   ratio PPO min/max:", float(ratio.min()), float(ratio.max()))
