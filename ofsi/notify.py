"""Notifications locales (MISSION §45). Journal `runs/_notifications.jsonl` (lu par le tableau de bord) + notification systeme optionnelle
(Windows : toast PowerShell ; Linux : notify-send) — toujours « au mieux », jamais fatale. Aucun reseau.
Detecteurs : plateau, regression, record de debit, disque faible, nouveau champion (benchmark), arret/erreur d'un run. Chaque notification est un FAIT mesure
(valeur et fenetre incluses) ; deduplication par cle stable (une notification par evenement, pas une par scrutation)."""
import json, os, shutil, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS = pathlib.Path(os.environ.get("OFSI_RUNS", ROOT / "runs"))
LOG = RUNS / "_notifications.jsonl"
LEVELS = ("info", "success", "warning", "error")


def _seen():
    keys = set()
    if LOG.exists():
        for l in LOG.read_text(encoding="utf-8").splitlines():
            try: keys.add(json.loads(l)["key"])
            except Exception: pass
    return keys


def _os_toast(title, msg):
    try:
        if sys.platform.startswith("win"):
            ps = ("[void][Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];"
                  "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('ToastText02');"
                  f"$n=$t.GetElementsByTagName('text');$n.Item(0).AppendChild($t.CreateTextNode('{title}'))|Out-Null;$n.Item(1).AppendChild($t.CreateTextNode('{msg}'))|Out-Null;"
                  "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('OpenFront SI').Show([Windows.UI.Notifications.ToastNotification]::new($t))")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", title, msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def notify(key, title, detail, level="info", toast=False):
    """Ajoute une notification si `key` est nouvelle. Retourne True si ajoutee."""
    assert level in LEVELS
    RUNS.mkdir(exist_ok=True)
    if key in _seen(): return False
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "key": key, "level": level, "title": title, "detail": detail}, ensure_ascii=False) + "\n")
    if toast: _os_toast(title.replace("'", " "), detail.replace("'", " ")[:200])
    return True


def read(n=50):
    out = []
    if LOG.exists():
        for l in LOG.read_text(encoding="utf-8").splitlines()[-n:]:
            try: out.append(json.loads(l))
            except Exception: pass
    return out[::-1]


def _rows(run):
    f = RUNS / run / "metrics.jsonl"; rows = []
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            try: rows.append(json.loads(l))
            except Exception: pass
    return rows


def scan(plateau_updates=30, plateau_eps=0.02, regress_drop=0.15, min_free_gb=5.0, toast=False):
    """Passe unique sur l'etat reel ; retourne la liste des notifications NOUVELLES."""
    new = []

    def add(*a, **k):
        if notify(*a, toast=toast, **k): new.append(a[0])
    du = shutil.disk_usage(ROOT)
    if du.free / 2**30 < min_free_gb: add(f"disk:{int(du.free / 2**30)}", "Disque presque plein", f"{du.free / 2**30:.1f} Go libres (seuil {min_free_gb} Go)", "error")
    for d in sorted(p for p in RUNS.iterdir() if p.is_dir() and not p.name.startswith("_")) if RUNS.exists() else []:
        rows = _rows(d.name)
        if len(rows) < 2: continue
        last = rows[-1]
        dps = [r["decisions_per_s"] for r in rows if r.get("decisions_per_s")]
        if len(dps) >= 10 and dps[-1] >= max(dps[:-1]) * 1.0 and dps[-1] > 1.25 * (sum(dps[:-1]) / len(dps[:-1])): add(f"record:{d.name}:{int(dps[-1])}", f"Record de debit ({d.name})", f"{dps[-1]:.1f} decisions/s (moyenne precedente {sum(dps[:-1]) / len(dps[:-1]):.1f})", "success")
        wr = [r["recent200_winrate"] for r in rows if r.get("recent200_winrate") is not None]
        if len(wr) >= plateau_updates:                                         # plateau : variation de la fenetre < seuil
            w = wr[-plateau_updates:]
            if max(w) - min(w) < plateau_eps and last["env_steps"] > 20000: add(f"plateau:{d.name}:{last['update'] // plateau_updates}", f"Plateau ({d.name})", f"taux de victoire glissant stable ({min(w):.2f}-{max(w):.2f}) sur {plateau_updates} mises a jour", "warning")
        if len(wr) >= 20 and max(wr[-20:-5]) - wr[-1] > regress_drop: add(f"regress:{d.name}:{last['update']}", f"Regression ({d.name})", f"taux de victoire glissant {wr[-1]:.2f} contre un maximum recent de {max(wr[-20:-5]):.2f}", "warning")
        if not all(map(lambda x: x == x and abs(x) < 1e9, (last.get("pg_loss", 0), last.get("v_loss", 0)))): add(f"nan:{d.name}", f"Divergence numerique ({d.name})", "perte non finie", "error")
    return new


def status():
    """Banniere §45. 'IA LOCALE VALIDEE' UNIQUEMENT si docs/validation.json declare all_pass=true (ecrit par une validation reelle) ; sinon jamais."""
    running = False
    if RUNS.exists():
        for d in RUNS.iterdir():
            f = d / "metrics.jsonl"
            if d.is_dir() and not d.name.startswith("_") and f.exists() and time.time() - f.stat().st_mtime < 120: running = True
    v = pathlib.Path(os.environ.get("OFSI_VALIDATION", ROOT / "docs" / "validation.json"))
    try: ok = bool(json.loads(v.read_text(encoding="utf-8")).get("all_pass"))
    except Exception: ok = False
    if ok: return {"banner": "IA LOCALE VALIDÉE — PRÊTE POUR LA PROCHAINE PHASE", "level": "success", "training": running}
    return {"banner": "ENTRAÎNEMENT EN COURS" if running else "VALIDATION PARTIELLE — LIMITATIONS IDENTIFIÉES", "level": "info" if running else "warning", "training": running}


if __name__ == "__main__":
    print(json.dumps({"nouvelles": scan(toast="--toast" in sys.argv), "statut": status()}, ensure_ascii=False))
