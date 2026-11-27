import os
from pathlib import Path
import sys
import json
import re
import secrets
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ASSETS = Path(__file__).resolve().parent
ROOT = ASSETS.parent if ASSETS.name == "portable-windows" and (ASSETS.parent / "ofsi" / "rl2").is_dir() else ASSETS
REPLAY_DIR = ROOT / "runs" / "_replays"
LIVE_DIR = ROOT / "runs" / "_live"
ENGINE_DIR = ROOT / "vendor" / "openfront-engine"
SAFE_NAME = re.compile(r"[A-Za-z0-9_-]{1,40}")
DIFFICULTIES = {"Easy", "Medium", "Hard", "Impossible"}
STEP_LINE = re.compile(r"Decision (\d+)(?:/(\d+))?")
RUN_TOKEN = secrets.token_urlsafe(24)


def available_maps():
    path = ENGINE_DIR / "packages/engine-api/src/game/Maps.gen.ts"
    source = path.read_text(encoding="utf-8")
    enum = source.split("export enum GameMapType {", 1)[1].split("\n}", 1)[0]
    pairs = re.findall(r'^\s*([A-Za-z]\w*)\s*=\s*("(?:[^"\\]|\\.)*")', enum, re.M)
    maps = {key: json.loads(value) for key, value in pairs
            if (ENGINE_DIR / "resources/maps" / key.lower() / "map.bin").is_file()}
    if not maps:
        raise RuntimeError("Aucune carte du moteur trouvee.")
    return maps


def validate_game(data, maps, cuda):
    if not isinstance(data, dict):
        raise ValueError("Reglages invalides.")
    map_id = data.get("map")
    difficulty = data.get("difficulty")
    bots = data.get("bots")
    nations = data.get("nations")
    retry = data.get("retry", False)
    seed = data.get("seed", "")
    device = data.get("device", "auto")
    if not isinstance(map_id, str) or map_id not in maps:
        raise ValueError("Choisis une carte disponible.")
    if not isinstance(difficulty, str) or difficulty not in DIFFICULTIES:
        raise ValueError("Difficulte invalide.")
    if type(bots) is not int or not 0 <= bots <= 60:
        raise ValueError("Choisis entre 0 et 60 bots.")
    if type(nations) is not bool or (not nations and bots == 0):
        raise ValueError("Active les nations ou ajoute au moins un bot.")
    if type(retry) is not bool:
        raise ValueError("Option de relance invalide.")
    if not isinstance(seed, str) or (seed and not re.fullmatch("[A-Za-z0-9]{8,10}", seed)):
        raise ValueError("La graine doit avoir 8 a 10 lettres ou chiffres.")
    if not isinstance(device, str) or device not in {"auto", "cpu", "cuda"} or (device == "cuda" and not cuda):
        raise ValueError("Peripherique indisponible dans ce ZIP.")
    return {
        "map": map_id, "difficulty": difficulty, "bots": bots, "nations": nations,
        "seed": seed or secrets.token_hex(4), "device": device, "retry": retry,
    }


class ReplayJobs:
    def __init__(self, quick=False):
        self.quick = quick
        self.lock = threading.Lock()
        self.process = None
        self.stopping = False
        self.state = {"status": "ready", "message": "Choisis tes reglages, puis lance une partie."}

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def spawn(self, game):
        name = "game-" + game["map"].lower()[:20] + "-" + secrets.token_hex(4)
        command = [sys.executable, "-X", "utf8", "-B", str(ASSETS / "portable.py"), "replay",
                   "--map", game["map"], "--difficulty", game["difficulty"], "--bots", str(game["bots"]),
                   "--seed", game["seed"], "--device", game["device"], "--replay-name", name,
                   "--enhanced", "--live"]
        if not game["nations"]:
            command.append("--no-nations")
        command.append("--quick" if self.quick else "--unlimited")
        process = subprocess.Popen(
            command,
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=os.name != "nt",
            encoding="utf-8", errors="replace",
        )
        self.process = process
        return process, name

    def start(self, game):
        with self.lock:
            if self.process is not None:
                raise RuntimeError("Une partie est deja en cours.")
            self.stopping = False
            process, name = self.spawn(game)
            self.state = {"status": "running", "message": "Chargement du champion et de la carte...",
                          "step": 0, "limit": 0, "attempt": 1, "stopping": False, "replay": None, "live_name": name}
            threading.Thread(target=self.track, args=(process, name, game), daemon=True).start()

    def track(self, process, name, game):
        while True:
            tail = ""
            assert process.stdout is not None
            with process.stdout:
                for line in process.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    tail = line
                    if line.startswith(("Rapport", "Rejeu")):
                        continue
                    with self.lock:
                        if not self.stopping:
                            self.state["message"] = line
                            if match := STEP_LINE.search(line):
                                self.state["step"] = int(match[1])
                                self.state["limit"] = int(match[2] or 0)
            code = process.wait()
            result = {}
            if code == 0:
                try:
                    result = json.loads((REPLAY_DIR / f"{name}.json").read_text(encoding="utf-8"))
                except (OSError, ValueError) as error:
                    tail = str(error)
            if self.finish(result, name, tail or f"code {code}", game):
                with self.lock:
                    process, name = self.process, self.pending_name
                continue
            return

    def finish(self, result, name, reason, game):
        with self.lock:
            self.process = None
            live_path = LIVE_DIR / f"{name}.json"
            for path in (live_path, live_path.with_suffix(".tmp")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            self.state["live_name"] = None
            if result:
                self.state["replay"] = name
            if self.stopping:
                self.state.update(status="stopped", stopping=False, message="Arret demande.")
                return False
            if result.get("win") is True and result.get("end") == "win":
                self.state.update(status="won", message="Victoire confirmee par le moteur.")
                return False
            if result.get("end") in {"dead", "loss_winner_other"}:
                if game["retry"]:
                    try:
                        _, self.pending_name = self.spawn(dict(game, seed=secrets.token_hex(4)))
                    except OSError as error:
                        self.state.update(status="error", message=f"Relance impossible : {error}")
                        return False
                    self.state.update(message="Defaite. Nouvelle partie avec une autre graine.",
                                      attempt=self.state["attempt"] + 1, step=0, limit=0, live_name=self.pending_name)
                    return True
                self.state.update(status="lost", message="Defaite. Le rejeu est disponible.")
                return False
            self.state.update(status="error", message=f"Partie interrompue : {reason}")
            return False

    def stop(self):
        with self.lock:
            proc = self.process
            if proc is None or self.stopping:
                return
            self.stopping = True
            self.state.update(stopping=True, message="Arret en cours...")
        if proc.poll() is None:
            if os.name == "nt":
                exe = Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"
                subprocess.run([str(exe), "/PID", str(proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if proc.poll() is None:
                if os.name == "nt":
                    proc.terminate()
                else:
                    import signal
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass

    def close(self):
        self.stop()


def make_handler(maps, jobs, cuda, inventory):
    setup = "const SESSION_TOKEN = " + json.dumps(RUN_TOKEN) + ";\n"
    html = (ASSETS / "dashboard-live.html").read_text(encoding="utf-8")
    page = html + "<script>" + setup + (ASSETS / "dashboard-live.js").read_text(encoding="utf-8") + "</script></html>"
    reports = ROOT / "reports"
    replay_labels = {key.lower()[:20]: label for key, label in maps.items()}

    class DashboardHandler(BaseHTTPRequestHandler):
        def live(self, url):
            state = jobs.snapshot()
            name = state.get("live_name")
            if not name or not SAFE_NAME.fullmatch(name):
                return self.respond(200, {"snapshot": None})
            path = LIVE_DIR / f"{name}.json"
            try:
                metadata = path.stat()
                cursor = f"{name}-{metadata.st_mtime_ns}"
                if parse_qs(url.query).get("cursor", [""])[0] == cursor:
                    return self.respond(200, {"cursor": cursor})
                data = json.loads(path.read_bytes())
            except (OSError, ValueError):
                return self.respond(200, {"snapshot": None})
            if jobs.snapshot().get("live_name") != name:
                return self.respond(200, {"snapshot": None})
            return self.respond(200, {"snapshot": data, "cursor": cursor})

        def log_message(self, *args):
            pass

        def respond(self, status, value, html=False):
            raw = (value.encode("utf-8") if html else
                   value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8"))
            self.send_response(status)
            self.send_header("Content-Type", ("text/html" if html else "application/json") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def own_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            if not self.own_host():
                return self.respond(403, {"error": "Adresse locale attendue."})
            url = urlsplit(self.path)
            if url.path == "/":
                return self.respond(200, page, html=True)
            if url.path == "/api/options":
                return self.respond(200, {"maps": list(maps.items()), "cuda": cuda})
            if url.path == "/api/hardware":
                return self.respond(200, inventory)
            if url.path == "/api/benchmarks":
                return self.respond(200, [{"file": p.name} for p in sorted(reports.glob("*.json"), reverse=True)
                                          if SAFE_NAME.fullmatch(p.stem)])
            if url.path.startswith("/reports/"):
                name = url.path.removeprefix("/reports/")
                if name.endswith(".json") and SAFE_NAME.fullmatch(name[:-5]):
                    path = reports / name
                    if path.is_file():
                        return self.respond(200, path.read_bytes())
            if url.path == "/api/live":
                return self.live(url)
            if url.path == "/api/game":
                return self.respond(200, jobs.snapshot())
            if url.path == "/api/replays":
                paths = sorted(REPLAY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                entries = []
                for path in paths:
                    if not SAFE_NAME.fullmatch(path.stem):
                        continue
                    label = replay_labels.get(path.stem.split("-")[1]) if path.stem.startswith("game-") else None
                    entries.append({"name": path.stem, "map": label})
                return self.respond(200, entries)
            if url.path == "/api/replay":
                name = parse_qs(url.query).get("name", [""])[0]
                if SAFE_NAME.fullmatch(name):
                    path = REPLAY_DIR / f"{name}.json"
                    if path.is_file():
                        return self.respond(200, path.read_bytes())
            return self.respond(404, {"error": "Page introuvable."})

        def do_POST(self):
            if (not self.own_host() or self.headers.get("X-OpenFront-Session") != RUN_TOKEN):
                return self.respond(403, {"error": "Session locale invalide. Actualise la page."})
            if self.path == "/api/game/stop":
                jobs.stop()
                return self.respond(202, jobs.snapshot())
            if self.path != "/api/game":
                return self.respond(404, {"error": "Page introuvable."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("Taille de requete invalide.")
                game = validate_game(json.loads(self.rfile.read(size)), maps, cuda)
            except (ValueError, UnicodeError) as error:
                return self.respond(400, {"error": str(error)})
            try:
                jobs.start(game)
            except (OSError, RuntimeError) as error:
                return self.respond(409, {"error": str(error)})
            return self.respond(202, jobs.snapshot())

    return DashboardHandler


def serve(port, open_browser, inventory, quick=False):
    jobs = ReplayJobs(quick=quick)
    cuda = any(device["usable"] for device in inventory["cuda_devices"])
    handler = make_handler(available_maps(), jobs, cuda, inventory)
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"OpenFront SI : {url}", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            jobs.close()
