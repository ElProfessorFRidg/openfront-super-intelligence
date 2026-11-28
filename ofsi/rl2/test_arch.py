"""Tests de l'architecture configurable et auto-decrite : compatibilite des anciens checkpoints (sortie identique), aller-retour d'un autre reseau, refus d'un desaccord."""
import sys, os, pathlib, subprocess, tempfile, shutil
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import numpy as np, torch
from ofsi.rl2 import ckpt
from ofsi.rl2.model import PolicyV2
from ofsi.rl2.pretrain import Data
ok = []
def check(n, c): ok.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
torch.set_num_threads(2); ROOT = pathlib.Path(__file__).resolve().parents[2]
D = Data(str(ROOT / "data/demos_v3/shard_*.npz")); idx = np.sort(np.random.default_rng(0).choice(D.va, 32, replace=False)); o, act, _ = D.batch(idx, "cpu")
# 1. anciens checkpoints : build_model == construction historique PolicyV2() + load_state_dict (sortie identique au bit pres)
for name in ("runs/init_bc", "runs/arm_C_medium"):
    pl = ckpt.load(str(ROOT / name / "ckpt_latest.pt")); old = PolicyV2(); old.load_state_dict(pl["model"]); old.eval(); new = ckpt.build_model(pl); new.eval()
    with torch.no_grad(): a, b = old.act(o, actions=act)["logp"], new.act(o, actions=act)["logp"]
    check(f"{name}: ancien checkpoint charge a l'identique (max |dlogp| = {float((a - b).abs().max()):.1e}, arch deduite {ckpt.arch_from_state(pl['model'])})", torch.equal(a, b))
# 2. autre architecture : aller-retour sauvegarde/chargement, `arch` conserve (dont heads=2, non deductible des formes)
arch = {"d": 64, "layers": 2, "heads": 2, "ff": 128}; m = PolicyV2(**arch).eval(); T = tempfile.mkdtemp(); p = os.path.join(T, "ckpt_latest.pt"); ckpt.save(p, {"model": m.state_dict(), "arch": m.arch, "update": 1})
pl = ckpt.load(p); m2 = ckpt.build_model(pl).eval()
with torch.no_grad(): a, b = m.act(o, actions=act)["logp"], m2.act(o, actions=act)["logp"]
check(f"autre architecture {arch} : aller-retour identique, heads conserve ({pl['arch']['heads']})", torch.equal(a, b) and pl["arch"] == arch and m2.arch == arch)
# 3. verification de portabilite
sys.path.insert(0, str(ROOT)); from ofsi.rl2.ckpt_check import check as chk
r = chk(p); check("ckpt_check accepte le nouveau checkpoint", r["ok"] and r["architecture"] == arch)
# 4. refus d'un desaccord explicite d'architecture avec un checkpoint existant (avant tout lancement de moteur)
r = subprocess.run([sys.executable, "ofsi/rl2/ppo2.py", "--name", "_archtest_bad", "--init", "runs/init_bc/ckpt_latest.pt", "--layers", "6", "--updates", "1"], cwd=ROOT, capture_output=True, text=True)
check("desaccord d'architecture refuse avec un message explicite", r.returncode != 0 and "incompatible" in (r.stdout + r.stderr)); shutil.rmtree(ROOT / "runs/_archtest_bad", ignore_errors=True)
# 5. entrainement reel d'un petit reseau, puis reprise : l'architecture est conservee
env = dict(os.environ); name = "_archtest_small"; shutil.rmtree(ROOT / "runs" / name, ignore_errors=True)
c1 = [sys.executable, "ofsi/rl2/ppo2.py", "--name", name, "--d-model", "64", "--layers", "2", "--heads", "2", "--ff", "128", "--envs", "2", "--T", "16", "--mb", "16", "--epochs", "1", "--updates", "2", "--ckpt-every", "1"]
r1 = subprocess.run(c1, cwd=ROOT, capture_output=True, text=True, env=env); pl = ckpt.load(str(ROOT / "runs" / name / "ckpt_latest.pt"))
check("PPO d'un petit reseau depuis zero : checkpoint auto-decrit " + str(pl.get("arch")), r1.returncode == 0 and pl.get("arch") == arch)
r2 = subprocess.run(c1[:-4] + ["--updates", "4", "--ckpt-every", "1", "--resume"], cwd=ROOT, capture_output=True, text=True, env=env); pl2 = ckpt.load(str(ROOT / "runs" / name / "ckpt_latest.pt"))
check(f"reprise : architecture conservee, mise a jour {pl2.get('update')}", r2.returncode == 0 and pl2.get("arch") == arch and pl2.get("update") == 4); shutil.rmtree(ROOT / "runs" / name, ignore_errors=True)
print(f"{sum(ok)}/{len(ok)} PASS"); sys.exit(0 if all(ok) else 1)
