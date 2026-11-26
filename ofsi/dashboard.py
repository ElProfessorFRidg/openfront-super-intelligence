"""Tableau de bord local (loopback uniquement). Affiche UNIQUEMENT des donnees reelles lues dans runs/ et benchmarks/.
Controles : fichiers STOP/PAUSE dans runs/<nom>/ (noms valides par liste blanche, aucune commande arbitraire)."""
import json, re, sys, shutil, pathlib, argparse, time, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
START = time.time()

PAGE = r"""<!doctype html><html lang="fr"><meta charset="utf-8"><title>OpenFront SI - tableau de bord</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font:14px system-ui,sans-serif;margin:0;background:#0f1419;color:#e6e6e6}
header{padding:12px 20px;background:#1a222c;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:18px;margin:0} main{padding:16px 20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}
.card{background:#1a222c;border-radius:8px;padding:12px 14px} .card h2{font-size:14px;margin:0 0 8px;color:#9fb3c8}
.kv{display:grid;grid-template-columns:auto 1fr;gap:2px 12px} .kv b{color:#9fb3c8;font-weight:500}
button,select{background:#2b3a4a;color:#e6e6e6;border:1px solid #3d5167;border-radius:5px;padding:5px 10px;cursor:pointer}
button:hover{background:#38506a} canvas{width:100%;height:150px;background:#10161c;border-radius:4px}
.warn{color:#f0b429}.na{color:#7b8794} table{border-collapse:collapse;width:100%} td,th{padding:3px 6px;border-bottom:1px solid #2b3a4a;text-align:right} th:first-child,td:first-child{text-align:left}
</style>
<header><h1>OpenFront Super Intelligence - local</h1>
<label>Run <select id="run"></select></label>
<button onclick="ctl('pause')">Suspendre</button><button onclick="ctl('resume')">Reprendre</button>
<button onclick="if(confirm('Arreter proprement (checkpoint sauvegarde) ?'))ctl('stop')">Arreter proprement</button>
<span id="status" class="na"></span></header>
<main>
<div class="card"><h2>Etat</h2><div class="kv" id="state"></div></div>
<div class="card"><h2>Taux de victoire (200 derniers episodes) - entrainement</h2><canvas id="c_wr"></canvas></div>
<div class="card"><h2>Retour moyen (200 derniers)</h2><canvas id="c_ret"></canvas></div>
<div class="card"><h2>Progression vers le seuil de victoire (200 derniers, 1.0 = victoire)</h2><canvas id="c_prog"></canvas></div>
<div class="card"><h2>Entropie de la politique</h2><canvas id="c_ent"></canvas></div>
<div class="card"><h2>Decisions / s (debit)</h2><canvas id="c_fps"></canvas></div>
<div class="card"><h2>Curriculum (etape courante)</h2><canvas id="c_stage"></canvas><div id="cur" class="na"></div></div>
<div class="card"><h2>Distribution des actions (derniere mise a jour)</h2><div id="acts"></div></div>
<div class="card"><h2>Benchmarks mesures</h2><div id="bench" class="na">aucun</div></div>
<div class="card"><h2>Materiel</h2><div class="kv" id="hw"></div></div>
</main>
<script>
const $=id=>document.getElementById(id); let run=null;
const ACT2=["STOP","Attaque terre neutre","Attaque joueur","Bateau (invasion)","Build City","Build Port","Build Defense Post","Build Factory","Build SAM","Build Silo","Upgrade","Bombe atomique","Bombe H","MIRV","Build Warship","Deplacer warships","Annuler attaque","Annuler bateau","Supprimer unite","Alliance: demande","Alliance: rejet","Alliance: prolongation","Alliance: rupture","Cibler joueur","Don d'or","Don de troupes","Embargo ON","Embargo OFF","Embargo global ON","Embargo global OFF","Spawn"];
const ACT=["noop","expand",...[0,1,2,3,4,5].map(i=>"attaque v"+i),"build City","build Port","build DefensePost","build Factory","build SAM","build Warship",...[0,1,2,3,4,5].map(i=>"alliance v"+i)];
function draw(id,xs,ys,color){const c=$(id),d=c.getContext('2d');c.width=c.clientWidth*2;c.height=300;d.clearRect(0,0,c.width,c.height);
 const v=ys.map((y,i)=>[xs[i],y]).filter(p=>p[1]!==null&&p[1]!==undefined);if(v.length<2){d.fillStyle='#7b8794';d.font='22px sans-serif';d.fillText('pas encore de donnees',20,60);return}
 const x0=v[0][0],x1=v[v.length-1][0],ymin=Math.min(...v.map(p=>p[1])),ymax=Math.max(...v.map(p=>p[1])),sp=(ymax-ymin)||1;
 d.strokeStyle=color;d.lineWidth=3;d.beginPath();v.forEach((p,i)=>{const X=(p[0]-x0)/((x1-x0)||1)*(c.width-70)+60,Y=c.height-20-(p[1]-ymin)/sp*(c.height-50);i?d.lineTo(X,Y):d.moveTo(X,Y)});d.stroke();
 d.fillStyle='#9fb3c8';d.font='22px sans-serif';d.fillText(ymax.toPrecision(3),2,28);d.fillText(ymin.toPrecision(3),2,c.height-22);}
async function ctl(a){if(!run)return;const r=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run,action:a})});$('status').textContent=(await r.json()).msg}
async function refresh(){
 const runs=await (await fetch('/api/runs')).json(); const sel=$('run'); if(!sel.options.length||sel.options.length!==runs.length){sel.innerHTML=runs.map(r=>`<option>${r}</option>`).join('')} if(!run&&runs.length){run=sel.value=runs[0]} run=sel.value||run;
 if(run){const m=await (await fetch('/api/metrics?run='+run+'&n=400')).json(); const last=m.rows[m.rows.length-1];
  if(last){const xs=m.rows.map(r=>r.env_steps);
   $('state').innerHTML=`<b>Etat</b><span>${m.state}</span><b>Update</b><span>${last.update}</span><b>Decisions cumulees</b><span>${last.env_steps}</span><b>Temps d'entrainement</b><span>${(last.t_total_s/3600).toFixed(2)} h</span><b>Debit</b><span>${last.decisions_per_s} decisions/s</span><b>Etape curriculum</b><span>${last.stage}</span><b>Win rate (200 derniers)</b><span>${last.recent200_winrate===null?'n/a':(last.recent200_winrate*100).toFixed(1)+' %'}</span><b>Actions inexecutables (candidat perime)</b><span>${(((last.invalid_exec_frac??last.invalid_build_exec_frac)||0)*100).toFixed(1)} %</span><b>Dernier checkpoint</b><span>${m.ckpt||'aucun'}</span>`;
   draw('c_wr',xs,m.rows.map(r=>r.recent200_winrate),'#4ade80');draw('c_ret',xs,m.rows.map(r=>r.recent200_mean_return),'#60a5fa');draw('c_prog',xs,m.rows.map(r=>r.recent200_progress??null),'#34d399');draw('c_ent',xs,m.rows.map(r=>r.entropy),'#f472b6');draw('c_fps',xs,m.rows.map(r=>r.decisions_per_s),'#fbbf24');draw('c_stage',xs,m.rows.map(r=>r.stage),'#c084fc');
   $('cur').textContent=m.curriculum_log.length?m.curriculum_log.map(c=>`update ${c.update}: etape ${c.from} -> ${c.to} (winrate ${(c.winrate*100).toFixed(0)} % sur ${c.n})`).join(' | '):'aucune montee d\'etape pour l\'instant';
   const H=last.type_hist||last.action_hist, L=last.type_hist?ACT2:ACT; $('acts').innerHTML='<table>'+H.map((p,i)=>`<tr><td>${L[i]||i}</td><td>${(p*100).toFixed(1)} %</td></tr>`).join('')+'</table>';
  } else $('state').innerHTML='<b>Etat</b><span class="na">aucune mesure encore</span>'}
 const b=await (await fetch('/api/benchmarks')).json(); $('bench').innerHTML=b.length?b.map(x=>`<div><b>${x.file}</b><br><span class="na">${x.summary}</span></div>`).join(''):'aucun';
 const h=await (await fetch('/api/hardware')).json(); $('hw').innerHTML=Object.entries(h).map(([k,v])=>`<b>${k}</b><span class="${String(v).startsWith('non')?'warn':''}">${v}</span>`).join('');}
refresh();setInterval(refresh,3000);$('run').onchange=e=>{run=e.target.value;refresh()};
</script></html>"""


def read_metrics(run, n):
    f = RUNS / run / "metrics.jsonl"
    rows = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines()[-n:]:
            try: rows.append(json.loads(line))
            except Exception: pass
    return rows


def run_state(run):
    d = RUNS / run
    if (d / "STOP").exists(): return "arret demande"
    if (d / "PAUSE").exists(): return "suspendu"
    f = d / "metrics.jsonl"
    if f.exists() and time.time() - f.stat().st_mtime < 120: return "en cours"
    return "inactif"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/": return self._send(200, PAGE, "text/html")
        if u.path == "/api/runs": return self._send(200, json.dumps(sorted(p.name for p in RUNS.iterdir() if p.is_dir() and not p.name.startswith("_") and ((p / "metrics.jsonl").exists() or (p / "ckpt_latest.pt").exists())) if RUNS.exists() else []))
        if u.path == "/api/metrics":
            run = q.get("run", [""])[0]
            if not NAME_RE.match(run): return self._send(400, '{"error":"nom invalide"}')
            ck = RUNS / run / "ckpt_latest.pt"
            cur = []
            if ck.exists():
                try:
                    import torch; cur = torch.load(ck, weights_only=False, map_location="cpu").get("cur_log", [])
                except Exception: cur = []
            return self._send(200, json.dumps({"rows": read_metrics(run, int(q.get("n", ["400"])[0])), "state": run_state(run), "curriculum_log": cur,
                                               "ckpt": (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ck.stat().st_mtime)) if ck.exists() else None)}))
        if u.path == "/api/benchmarks":
            out = []
            for f in sorted((ROOT / "benchmarks").glob("*.json")):
                try:
                    j = json.loads(f.read_text(encoding="utf-8")); rep = j.get("report", j)
                    s = rep.get("runs") and ", ".join(f"{r['envs']} envs: {r['agg_ticks_per_s']} t/s" for r in rep["runs"]) or (f"{rep.get('games_total')} parties, {rep.get('games_per_hour')}/h" if "games_total" in rep else "")
                    out.append({"file": f.name, "summary": s})
                except Exception: out.append({"file": f.name, "summary": "illisible"})
            return self._send(200, json.dumps(out))
        if u.path == "/api/hardware":
            du = shutil.disk_usage(ROOT)
            return self._send(200, json.dumps({"CPU logiques": os.cpu_count(), "Disque libre": f"{du.free / 2**30:.1f} Go", "GPU CUDA": "non disponible (cuInit=100, aucun peripherique)",
                                               "Temperatures": "non mesurees", "RAM/VRAM": "non mesurees par le tableau de bord"}))
        self._send(404, '{"error":"introuvable"}')
    def do_POST(self):
        if self.path != "/api/control": return self._send(404, '{"error":"introuvable"}')
        try: body = json.loads(self.rfile.read(min(4096, int(self.headers.get("Content-Length", "0")))))
        except Exception: return self._send(400, '{"msg":"json invalide"}')
        run, act = str(body.get("run", "")), str(body.get("action", ""))
        if not NAME_RE.match(run) or not (RUNS / run).is_dir() or act not in ("stop", "pause", "resume"): return self._send(400, '{"msg":"parametres invalides"}')
        d = RUNS / run
        if act == "stop": (d / "STOP").write_text("1"); msg = "arret propre demande (checkpoint sauvegarde a la fin de la mise a jour)"
        elif act == "pause": (d / "PAUSE").write_text("1"); msg = "suspendu"
        else:
            (d / "PAUSE").unlink(missing_ok=True); msg = "repris"
        self._send(200, json.dumps({"msg": msg}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8765); a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)   # loopback uniquement
    print(f"tableau de bord : http://127.0.0.1:{a.port}", flush=True); srv.serve_forever()
