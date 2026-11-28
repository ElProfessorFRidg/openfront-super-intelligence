"""Vérification du dashboard depuis un checkout Linux avec le vrai moteur."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen


def decode(url, data=None, headers=None):
    req = Request(url, data=data, headers=headers or {})
    with urlopen(req, timeout=5) as response:
        return json.load(response)


def verify():
    assets = Path(__file__).resolve().parent
    root = assets.parent
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, str(assets / "portable.py"), "dashboard", "--quick", "--no-browser", "--port", "0"],
            cwd=root, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and process.poll() is None:
                # Read without changing the write position inherited by the child.
                log.flush()
                with open(f"/proc/self/fd/{log.fileno()}", encoding="utf-8") as snapshot:
                    match = re.search(r"http://127\.0\.0\.1:\d+", snapshot.read())
                if match:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Le dashboard n'a pas ouvert de port.")
            base = match[0]
            with urlopen(base, timeout=5) as response:
                page = response.read().decode()
            token = re.search(r'const SESSION_TOKEN = "([^"]+)"', page)[1]
            assert "mapViewport" in page
            assert "World" in dict(decode(base + "/api/options")["maps"])
            config = {
                "map": "Onion", "difficulty": "Easy", "bots": 8, "nations": True,
                "seed": "rp000001", "device": "cpu", "retry": False,
            }
            decode(base + "/api/game", json.dumps(config).encode(),
                   {"Content-Type": "application/json", "X-OpenFront-Session": token})
            saw_live = False
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                status = decode(base + "/api/game")
                if status["status"] != "running":
                    break
                snapshot = decode(base + "/api/live").get("snapshot")
                if snapshot:
                    assert snapshot["frames"][0]["owners"]
                    saw_live = True
                time.sleep(0.08)
            assert saw_live, "Aucune image reçue pendant la partie."
            assert status["replay"], status
            replay = decode(base + "/api/replay?name=" + status["replay"])
            assert replay["cfg"]["map"] == "Onion"
            assert len(replay["frames"]) > 1 and len(replay["players"]) > 1
            assert replay["frames"][0]["owners"] and replay["frames"][0]["stats"]
            reports = decode(base + "/api/benchmarks")
            assert decode(base + "/reports/" + reports[0]["file"])["passed"]
            print("Dashboard Linux : vraie partie, direct, joueurs, rejeu et rapport OK.")
        except Exception:
            with open(f"/proc/self/fd/{log.fileno()}", encoding="utf-8") as snapshot:
                print(snapshot.read(), file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    verify()
