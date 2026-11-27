"""Auto-optimisation du parallelisme (MISSION §34/§35) : MESURE le debit soutenu (decisions/s) pour plusieurs nombres de moteurs avec le professeur scripte,
choisit le meilleur sous contrainte de RAM, ecrit config/autotune.json avec l'empreinte materielle (re-mesure automatique si le materiel change).
Usage : python ofsi/autotune.py [--seconds 45] [--candidates 1,2,3,4,6,8]  ;  lecture : autotune.load() -> dict ou None si absent/perime."""
import sys, os, json, time, pathlib, argparse, platform
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
ROOT = pathlib.Path(__file__).resolve().parents[1]; OUT = ROOT / "config" / "autotune.json"


def fingerprint():
    mem = 0
    try: mem = int([l for l in open("/proc/meminfo") if l.startswith("MemTotal")][0].split()[1]) // 1024 // 1024
    except Exception: pass
    return {"cpus": os.cpu_count(), "ram_gb": mem, "platform": platform.platform()[:40], "machine": platform.machine()}


def load():
    try: d = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception: return None
    return d if d.get("fingerprint") == fingerprint() else None                    # perime si le materiel a change


def measure(n, seconds):
    from ofsi.rl2.vecenv2 import VecEnv2
    from ofsi.rl2.teacher_v2 import TeacherV2
    cnt = [0]
    def cfg(): cnt[0] += 1; return {"map": ["Onion", "Pangaea", "Caucasus", "Iceland"][cnt[0] % 4], "bots": 8, "difficulty": "Easy"}
    env = VecEnv2(n, cfg, max_steps=1500); te = [TeacherV2(seed=i, ally_mode="threats") for i in range(n)]
    def step():
        acts = []
        for i in range(n):
            o = env.obs[i]
            if o is None: acts.append([]); continue
            st, costs, cands = env.sess[i].cur; acts.append(te[i].act(o, st, costs, cands))
        env.step(acts); return n
    for _ in range(5): step()                                                       # echauffement
    t0 = time.time(); d = 0; lat = []
    while time.time() - t0 < seconds: t1 = time.time(); d += step(); lat.append(time.time() - t1)
    env.close(); lat.sort(); return {"envs": n, "decisions_per_s": round(d / (time.time() - t0), 1), "step_p50_ms": round(1000 * lat[len(lat) // 2]), "step_p95_ms": round(1000 * lat[int(len(lat) * 0.95)])}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seconds", type=int, default=45); ap.add_argument("--candidates", default="1,2,3,4,6,8"); ap.add_argument("--gb-per-env", type=float, default=0.45)
    a = ap.parse_args(); fp = fingerprint(); res = []
    for n in [int(x) for x in a.candidates.split(",")]:
        if fp["ram_gb"] and n * a.gb_per_env + 3.5 > fp["ram_gb"]: print(f"{n} moteurs : ignore (RAM)"); continue
        r = measure(n, a.seconds); res.append(r); print(r, flush=True)
    best = max(res, key=lambda r: r["decisions_per_s"]); OUT.parent.mkdir(exist_ok=True)
    # parmi les configurations a moins de 5 % du meilleur debit, on prefere la moins gourmande (moins de RAM/CPU pour un gain negligeable)
    near = [r for r in res if r["decisions_per_s"] >= 0.95 * best["decisions_per_s"]]; pick = min(near, key=lambda r: r["envs"])
    rep = {"fingerprint": fp, "mesures": res, "meilleur_brut": best["envs"], "choisi_envs": pick["envs"], "regle": "moins de moteurs parmi ceux a >=95 % du meilleur debit", "date": time.strftime("%Y-%m-%d %H:%M"), "seconds_par_mesure": a.seconds, "politique": "professeur scripte (sans reseau) : le debit avec reseau neuronal CPU est plus bas et peut changer l'optimum"}
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8"); print("choisi:", pick["envs"], "moteurs ->", OUT)
