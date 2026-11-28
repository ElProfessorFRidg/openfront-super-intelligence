"""Ordonnanceur de ressources local (MISSION §35). Chaque travail declare ses besoins (coeurs, RAM) et une priorite ; l'ordonnanceur ne lance un travail que si le budget courant
(coeurs non reserves, RAM libre mesuree - marge) le permet, sinon il attend. Evite la contention mesuree le 2026-11-26 (PPO 20 -> 1,8 dec/s quand des evaluations tournaient en parallele).
Travaux : liste de dicts {"name","cmd":[...],"cores":n,"ram_gb":x,"priority":p (plus grand = d'abord),"log":"fichier"}. Arret propre : fichier runs/_sched/STOP (plus aucun lancement).
Usage : python ofsi/scheduler.py jobs.json [--cores N] [--reserve-gb 2]   |   API : run_jobs(jobs, cores, reserve_gb)"""
import sys, os, json, time, pathlib, subprocess, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
ROOT = pathlib.Path(__file__).resolve().parents[1]; SDIR = pathlib.Path(os.environ.get("OFSI_SCHED", ROOT / "runs" / "_sched"))


def free_ram_gb():
    try:
        for l in open("/proc/meminfo"):
            if l.startswith("MemAvailable:"): return int(l.split()[1]) / 2**20
    except Exception: pass
    return float("inf")


def run_jobs(jobs, cores=None, reserve_gb=2.0, poll=1.0, ram_fn=free_ram_gb, trace=None):
    """Retourne la liste des resultats {name, code, start, end, cores, ram_gb}. `trace` (liste) recoit (t, cores_reserves, nb_jobs) a chaque changement : sert aux tests."""
    cores = cores or (os.cpu_count() or 1); SDIR.mkdir(parents=True, exist_ok=True); pending = sorted(jobs, key=lambda j: -j.get("priority", 0)); running, results, t0 = [], [], time.time()
    for j in pending:
        if j["cores"] > cores: raise ValueError(f"travail {j['name']} : {j['cores']} coeurs demandes > budget {cores}")
    used = lambda: sum(r["job"]["cores"] for r in running); reserved_ram = lambda: sum(r["job"]["ram_gb"] for r in running)
    while pending or running:
        for r in list(running):                                        # collecte des travaux termines
            code = r["p"].poll()
            if code is not None: r["f"].close(); running.remove(r); results.append({"name": r["job"]["name"], "code": code, "start": round(r["t"] - t0, 2), "end": round(time.time() - t0, 2), "cores": r["job"]["cores"], "ram_gb": r["job"]["ram_gb"]})
        stop = (SDIR / "STOP").exists(); started = False
        for j in list(pending):                                        # priorite d'abord ; un gros travail prioritaire qui ne rentre pas BLOQUE les suivants (pas de famine)
            if stop: break
            fits = used() + j["cores"] <= cores and (ram_fn() - 0 >= j["ram_gb"] + reserve_gb or (not running and ram_fn() >= j["ram_gb"]))
            if not fits: break
            f = open(j.get("log", os.devnull), "a"); p = subprocess.Popen(j["cmd"], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT); running.append({"p": p, "f": f, "job": j, "t": time.time()}); pending.remove(j); started = True
        if trace is not None: trace.append((round(time.time() - t0, 2), used(), len(running)))
        if stop and not running: break
        time.sleep(poll if not started else 0.05)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("jobs"); ap.add_argument("--cores", type=int, default=None); ap.add_argument("--reserve-gb", type=float, default=2.0); a = ap.parse_args()
    for r in run_jobs(json.load(open(a.jobs)), a.cores, a.reserve_gb): print(r)
