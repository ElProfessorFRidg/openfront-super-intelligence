"""Banc d'essai du PARALLELISME des moteurs (lecture seule du code du pipeline : n'importe que ; ne modifie rien).
Mesure le debit SOUTENU (apres echauffement) pour N moteurs, mode synchrone (comme PPO : pas en lockstep) ou asynchrone (chaque moteur a son rythme), avec affinite CPU choisie.
Politique : professeur scripte (sans GPU) pour isoler le cout moteur+IPC+Python ; le cout d'inference neuronale se mesure a part.
Un 'decision' = un pas d'environnement de 20 ticks avec observation complete (rien n'est gonfle ; decide_every n'est jamais modifie)."""
import sys, time, json, pathlib, argparse, threading, random, statistics as st, ctypes, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.rl2.env2 import Session
from ofsi.rl2.teacher_v2 import TeacherV2
from ofsi.rl2 import space as S
from ofsi.rl2.memguard import free_gb, wait_ram

MASKS = {"all": 0x3FFFFF, "p": 0xFFC03, "p_nosmt": 0x00403 | (1 << 10) | (1 << 12) | (1 << 14) | (1 << 16) | (1 << 18), "e": 0x3003FC, "pe": 0x3FFFFF & ~0x300000}
MAPS = ["Onion", "Pangaea", "Caucasus", "BosphorusStraits", "Iceland", "BeringStrait", "DanishStraits", "BlackSea"]


def set_affinity(mask):
    k = ctypes.windll.kernel32; return bool(k.SetProcessAffinityMask(k.GetCurrentProcess(), ctypes.c_size_t(mask)))


def pct(a, p): a = sorted(a); return a[min(len(a) - 1, int(p / 100 * len(a)))] if a else None


def make_cfg(rng, diff, bots):
    return {"map": rng.choice(MAPS), "bots": bots, "difficulty": diff}


def run(n, mode, affinity, seconds, warmup, diff, bots, seed):
    rng = random.Random(seed); wait_ram(0.45 * n + 2.0, tag=" bench")
    set_affinity(MASKS[affinity])                                  # les moteurs lances HERITENT de l'affinite
    sess = [Session(20, 1500) for _ in range(n)]; cnt = [0]
    def start(i):
        cnt[0] += 1; c = make_cfg(rng, diff, bots); o = sess[i].start(c, f"b{seed}{cnt[0]:07d}"); sess[i].cfg = c; return o
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=n); obs = list(pool.map(start, range(n))); set_affinity(MASKS["p"] if affinity != "e" else MASKS["e"])   # le processus Python reste sur des coeurs rapides
    tea = [TeacherV2(seed=i, ally_mode="threats") for i in range(n)]; lat, per_engine = [], collections.defaultdict(list); games = [0]; steps = [0]; t_start = time.time(); stop = [False]; lock = threading.Lock()

    def one(i):
        s = sess[i]; o = obs[i]
        if o is None: obs[i] = start(i); return
        st_, costs, cands = s.cur; a = tea[i].act(o, st_, costs, cands); t0 = time.perf_counter(); was_spawn = bool(s.last["state"].get("spawnPhase")); r = s.apply(a)
        if was_spawn: s.spawn_wait()
        stt = s.last["state"]; ended = (r.get("winner") is not None) or ("self" not in stt) or (not stt["self"]["alive"]) or (not r.get("ok", True))
        obs[i] = start(i) if ended else s.observe()
        if ended: tea[i] = TeacherV2(seed=cnt[0], ally_mode="threats");
        dt = time.perf_counter() - t0
        with lock:
            if time.time() - t_start >= warmup:
                lat.append(dt); per_engine[i].append(dt); steps[0] += 1; games[0] += int(ended)

    t_meas0 = None
    try:
        if mode == "sync":
            while time.time() - t_start < warmup + seconds:
                list(pool.map(one, range(n)))
        else:
            def loop(i):
                while not stop[0]: one(i)
            ths = [threading.Thread(target=loop, args=(i,), daemon=True) for i in range(n)]; [t.start() for t in ths]
            while time.time() - t_start < warmup + seconds: time.sleep(0.5)
            stop[0] = True; [t.join(timeout=30) for t in ths]
        wall = seconds; res = {"n": n, "mode": mode, "affinity": affinity, "mask": hex(MASKS[affinity]), "seconds": seconds, "decisions": steps[0], "decisions_per_s": round(steps[0] / wall, 2), "ticks_per_s": round(20 * steps[0] / wall),
                               "games_finished": games[0], "games_per_hour": round(games[0] / wall * 3600, 1), "lat_ms": {"p50": round(1000 * pct(lat, 50), 1), "p95": round(1000 * pct(lat, 95), 1), "p99": round(1000 * pct(lat, 99), 1)} if lat else None,
                               "engine_spread": round(max(st.mean(v) for v in per_engine.values()) / max(1e-9, min(st.mean(v) for v in per_engine.values())), 2) if per_engine else None, "ram_free_gb": round(free_gb(), 1)}
    finally:
        pool.shutdown(wait=False)
        for s in sess:
            try: s.close()
            except Exception: pass
        set_affinity(MASKS["all"])
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", default="1,2,4,6,8,12,16,22,32"); ap.add_argument("--mode", default="sync", choices=["sync", "async"]); ap.add_argument("--affinity", default="all", choices=list(MASKS))
    ap.add_argument("--seconds", type=int, default=180); ap.add_argument("--warmup", type=int, default=60); ap.add_argument("--difficulty", default="Medium"); ap.add_argument("--bots", type=int, default=10); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="perf/out/bench_workers.json"); a = ap.parse_args(); out = []
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    for n in [int(x) for x in a.n.split(",")]:
        r = run(n, a.mode, a.affinity, a.seconds, a.warmup, a.difficulty, a.bots, a.seed); out.append(r); print(json.dumps(r), flush=True); pathlib.Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
