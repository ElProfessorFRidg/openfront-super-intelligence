"""Client Python du démon OpenFront headless (un processus Node par environnement)."""
import json, os, subprocess, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
NODE = ROOT / "tools/node24/node-v24.22.3-win-x64/node.exe"
ENGINE = ROOT / "vendor/openfront-engine"
TSX = ENGINE / "node_modules/tsx/dist/cli.mjs"


class OFEnvProc:
    def __init__(self):
        env = dict(os.environ)
        self.p = subprocess.Popen([str(NODE), str(TSX), "osi/daemon.mts"], cwd=ENGINE, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=(None if os.environ.get('OFSI_STDERR') else subprocess.DEVNULL), text=True, bufsize=1, env=env)
        self._id = 0

    def call(self, cmd, **kw):
        self._id += 1
        self.p.stdin.write(json.dumps({"id": self._id, "cmd": cmd, **kw}) + "\n"); self.p.stdin.flush()
        r = self._read_json()
        if not r.get("ok", False) and r.get("error") and cmd != "step":
            raise RuntimeError(r["error"])
        return r

    # --- mode asynchrone (vectorisation) : envoyer à tous, puis lire tous ---
    def send(self, cmd, **kw):
        self._id += 1; self.p.stdin.write(json.dumps({"id": self._id, "cmd": cmd, **kw}) + chr(10)); self.p.stdin.flush()
    def recv(self): return self._read_json()

    def _read_json(self):
        """Lit la prochaine reponse JSON ; toute ligne parasite (bruit du moteur sur stdout) est ignoree et comptee, jamais fatale."""
        while True:
            line = self.p.stdout.readline()
            if not line: raise RuntimeError("démon terminé")
            s = line.lstrip()
            if s.startswith("{"):
                try: return json.loads(s)
                except json.JSONDecodeError: pass
            self.noise_lines = getattr(self, "noise_lines", 0) + 1
    def step_obs(self, ticks=1, intents=None, agents=(0,), costs=False): return self.call("step_obs", ticks=ticks, intents=intents or [], agents=list(agents), costs=costs)
    def build_tiles(self, unit, agent=0, max_tiles=6): return self.call("build_tiles", agent=agent, unit=unit, max=max_tiles)["tiles"]

    def reset(self, **opts): return self.call("reset", opts=opts)
    def step(self, ticks=1, intents=None): return self.call("step", ticks=ticks, intents=intents or [])
    def observe(self, agent=0, grid=False): return self.call("observe", agent=agent, grid=grid)["obs"]
    def legal(self, agent=0): return self.call("legal", agent=agent)["legal"]
    def legal_at(self, tile, agent=0, units=None): return self.call("legal_at", agent=agent, tile=tile, units=units)["legal"]
    def spawn_candidates(self, stride=12, min_tiles=40): return self.call("spawn_candidates", stride=stride, minTiles=min_tiles)["tiles"]
    def landmasses(self, tiles=None): r = self.call("landmasses", tiles=tiles or []); return r["sizes"], r["of"]
    def cands(self, kind, agent=0, **kw): return self.call("cands", kind=kind, agent=agent, **kw)["cands"]
    def state2(self, agent=0, max_players=24): return self.call("state2", agent=agent, maxPlayers=max_players)
    def step_state(self, ticks=1, intents=None, agent=0, max_players=24): return self.call("step_state", ticks=ticks, intents=intents or [], agent=agent, maxPlayers=max_players)
    def grid2(self, agent=0, size=32): return self.call("grid2", agent=agent, size=size)
    def snapshot(self): return self.call("snapshot")["snap"]
    def restore(self, snap): return self.call("restore", snap=snap)
    def result(self): return self.call("result")["result"]

    def close(self):
        try: self.call("close")
        except Exception: pass
        self.p.kill()
