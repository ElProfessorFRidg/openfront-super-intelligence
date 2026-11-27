"""Orchestrateur autonome (MISSION §42/§43) : cycles  entrainer un candidat ANCRE depuis le champion -> evaluer (ECHANTILLONNE, memes parties) -> promouvoir seulement si
l'amelioration est SIGNIFICATIVE (McNemar exact apparie) -> notifier.  Aucun LLM, aucun reseau. Reprenable : toute etape dont le fichier de sortie existe est reutilisee.
Etat : runs/_orch/champion.json (champion courant + historique), runs/_orch/cycles.jsonl, evaluations en cache runs/_orch/eval_<sha8>_<tag>.json.
Arret propre : creer runs/_orch/STOP (verifie entre les etapes). Usage : python ofsi/orchestrator.py --init runs/arm_C_medium/ckpt_latest.pt --cycles 3 --budget 60000"""
import sys, os, json, time, pathlib, argparse, hashlib, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ofsi.rl2.compare_eval import mcnemar
from ofsi import notify

ROOT = pathlib.Path(__file__).resolve().parents[1]; ORCH = pathlib.Path(os.environ.get("OFSI_ORCH", ROOT / "runs" / "_orch")); CHAMP = ORCH / "champion.json"; CYCLES = ORCH / "cycles.jsonl"


def sha8(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()[:8]
def stop_requested(): return (ORCH / "STOP").exists()
def log(rec): ORCH.mkdir(parents=True, exist_ok=True); open(CYCLES, "a", encoding="utf-8").write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), **rec}, ensure_ascii=False) + "\n"); print(rec, flush=True)
def run(cmd, logf):
    with open(logf, "a", encoding="utf-8") as f: return subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode


def evaluate(ckpt, a, tag):
    """Evaluation echantillonnee en cache (cle = contenu du checkpoint + parametres d'evaluation)."""
    out = ORCH / f"eval_{sha8(ckpt)}_{tag}.json"
    if out.exists(): return out
    cmd = [sys.executable, "ofsi/rl2/eval2.py", "--agent", str(ckpt), "--per", str(a.eval_per), "--difficulties", a.difficulties, "--maps", a.eval_maps, "--envs", str(a.envs), "--sample", "--out", str(out)]
    rc = run(cmd, ORCH / "eval.log")
    if rc != 0 or not out.exists(): raise RuntimeError(f"evaluation en echec (code {rc}) : voir {ORCH / 'eval.log'}")
    return out


def paired(fa, fb):
    A = {p["cfg"]["_id"]: bool(p["win"]) for p in json.load(open(fa))["parties"]}; B = {p["cfg"]["_id"]: bool(p["win"]) for p in json.load(open(fb))["parties"]}
    ids = sorted(set(A) & set(B)); b = sum(1 for i in ids if B[i] and not A[i]); c = sum(1 for i in ids if A[i] and not B[i])
    return {"n": len(ids), "champion": sum(A[i] for i in ids), "candidat": sum(B[i] for i in ids), "cand_seul": b, "champ_seul": c, "p": mcnemar(b, c)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--init", help="checkpoint du champion initial (ignore si un champion existe deja)"); ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--budget", type=int, default=60000, help="decisions d'entrainement par candidat"); ap.add_argument("--envs", type=int, default=6); ap.add_argument("--stage0", type=int, default=2)
    ap.add_argument("--difficulties", default="Easy,Medium"); ap.add_argument("--eval-maps", default="train+heldout"); ap.add_argument("--eval-per", type=int, default=2); ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--lr", default="3e-5"); ap.add_argument("--kl-ref", default="1.0"); ap.add_argument("--bc-coef", default="0.5")
    a = ap.parse_args(); ORCH.mkdir(parents=True, exist_ok=True); tag = f"{a.difficulties.replace(',', '+')}_{a.eval_maps.replace('+', '')}_per{a.eval_per}"
    if CHAMP.exists(): champ = json.loads(CHAMP.read_text(encoding="utf-8"))
    elif a.init: champ = {"ckpt": a.init, "sha": sha8(a.init), "history": [{"event": "init", "ckpt": a.init, "t": time.strftime("%Y-%m-%d %H:%M:%S")}]}; CHAMP.write_text(json.dumps(champ, indent=1), encoding="utf-8")
    else: sys.exit("aucun champion : fournir --init")
    done = sum(1 for _ in open(CYCLES)) if CYCLES.exists() else 0
    for cyc in range(a.cycles):
        if stop_requested(): log({"event": "stop"}); break
        cid = f"orch_c{sha8(champ['ckpt'])}_s{cyc}"; rd = ROOT / "runs" / cid; cand = rd / "ckpt_latest.pt"
        if not cand.exists() or not (rd / "metrics.jsonl").exists():
            cmd = [sys.executable, "ofsi/rl2/ppo2.py", "--name", cid, "--init", champ["ckpt"], "--envs", str(a.envs), "--T", "64", "--max-decisions", str(a.budget), "--seed", str(100 + cyc), "--ckpt-every", "5",
                   "--lr", a.lr, "--ent", "0.005", "--value-warmup", "8", "--kl-ref", a.kl_ref, "--bc-coef", a.bc_coef, "--stage0", str(a.stage0)]
            if (rd / "ckpt_latest.pt").exists(): cmd.append("--resume")
            rc = run(cmd, ORCH / f"{cid}.log")
            if rc != 0 or not cand.exists(): log({"event": "train_fail", "cycle": cid, "code": rc}); notify.notify(f"orch_train_fail:{cid}", "Entrainement en echec", f"{cid} code {rc}", "error"); break
        if stop_requested(): log({"event": "stop"}); break
        try: fe_champ = evaluate(champ["ckpt"], a, tag); fe_cand = evaluate(cand, a, tag)
        except RuntimeError as e: log({"event": "eval_fail", "cycle": cid, "error": str(e)}); notify.notify(f"orch_eval_fail:{cid}", "Evaluation en echec", str(e)[:200], "error"); break
        r = paired(fe_champ, fe_cand); promote = r["cand_seul"] > r["champ_seul"] and r["p"] < a.alpha
        log({"event": "cycle", "cycle": cid, "candidat": str(cand), **r, "promu": promote, "alpha": a.alpha})
        if promote:
            champ = {"ckpt": str(cand), "sha": sha8(cand), "history": champ["history"] + [{"event": "promotion", "ckpt": str(cand), "vs": r, "t": time.strftime("%Y-%m-%d %H:%M:%S")}]}; CHAMP.write_text(json.dumps(champ, indent=1), encoding="utf-8")
            notify.notify(f"champion:{sha8(cand)}", "Nouveau champion", f"{cid} : {r['candidat']}/{r['n']} contre {r['champion']}/{r['n']} (p={r['p']:.3f})", "success")
        else: notify.notify(f"nochamp:{cid}", "Candidat non promu", f"{cid} : {r['candidat']}/{r['n']} contre champion {r['champion']}/{r['n']} (p={r['p']:.3f}) : difference non demontree", "info")
    log({"event": "fin", "champion": champ["ckpt"]})


if __name__ == "__main__":
    main()
