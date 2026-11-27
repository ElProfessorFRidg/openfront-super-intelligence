"""Lanceur Windows x64 d'évaluation hors ligne."""
import argparse
import ctypes
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from urllib.parse import urlsplit
from uuid import uuid4
import webbrowser

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
MANIFEST = ROOT / "distribution.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def windows_inventory():
    executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = (
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "$c=@(Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,NumberOfCores);"
        "$g=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion);"
        "@{processors=$c; display_adapters=$g} | ConvertTo-Json -Compress -Depth 4"
    )
    try:
        out = subprocess.check_output(
            [str(executable), "-NoProfile", "-NonInteractive", "-Command", command],
            encoding="utf-8-sig", timeout=15,
        )
        return json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"cpu_fallback": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor())}


def hardware(torch):
    from ofsi.rl2.memguard import _MS

    ram = _MS()
    ram.dwLength = ctypes.sizeof(ram)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ram)):
        raise ctypes.WinError()
    inventory = windows_inventory()
    inventory.update({
        "os": platform.platform(),
        "architecture": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "ram_total_bytes": ram.ullTotalPhys,
        "ram_available_bytes": ram.ullAvailPhys,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "process_admin": bool(ctypes.windll.shell32.IsUserAnAdmin()),
    })
    gpus = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            gpu = {"name": properties.name, "vram_bytes": properties.total_memory,
                   "compute_capability": list(torch.cuda.get_device_capability(index))}
            try:
                left = torch.ones((16, 16), device=f"cuda:{index}")
                torch.mm(left, left)
                torch.cuda.synchronize(index)
                gpu["usable"] = True
            except RuntimeError as exc:
                gpu.update(usable=False, error=str(exc))
            gpus.append(gpu)
    inventory["cuda_devices"] = gpus
    return inventory


def benchmark(agent, torch, devices, quick):
    from ofsi.client import OFEnvProc
    from ofsi.rl2.env2 import Session
    from ofsi.rl2.league import NeuralAgent

    engine = OFEnvProc()
    try:
        initial = engine.reset(map="Onion", seed="pb000001", agents=1, bots=8, difficulty="Easy")
        candidates = engine.spawn_candidates()
        reply = engine.step(1, [{"type": "spawn", "tile": candidates[len(candidates) // 2],
                                 "clientID": initial["agentIds"][0]}])
        while reply["ok"] and reply["spawnPhase"]:
            reply = engine.step(1)
        if not reply["ok"]:
            raise RuntimeError(reply.get("error") or "échec du moteur pendant le benchmark")
        start_tick = reply["tick"]
        started = time.perf_counter()
        for _ in range(4 if quick else 16):
            reply = engine.step(25)
            if not reply["ok"]:
                raise RuntimeError(reply.get("error") or "échec du moteur pendant le benchmark")
        engine_seconds = time.perf_counter() - started
    finally:
        engine.close()

    session = Session()
    try:
        observation = session.start({"map": "Onion", "bots": 8, "difficulty": "Easy"}, "pb000002")
        if observation is None:
            raise RuntimeError("observation initiale indisponible")
    finally:
        session.close()

    measured = []
    for name, index in devices:
        if index is not None:
            torch.cuda.set_device(index)
        policy = NeuralAgent(agent, device=name)
        batch = policy.collate([observation], name)
        loops = 3 if quick else 40
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=policy.bf16):
            for _ in range(3):
                policy.m.act(batch, greedy=False)
            if index is not None:
                torch.cuda.synchronize(index)
            started = time.perf_counter()
            for _ in range(loops):
                policy.m.act(batch, greedy=False)
            if index is not None:
                torch.cuda.synchronize(index)
            duration = time.perf_counter() - started
        measured.append({
            "device": name, "cuda_index": index, "precision": "bf16" if policy.bf16 else "fp32",
            "batch_size": 1, "decisions": loops, "mean_latency_ms": 1000 * duration / loops,
            "decisions_per_second": loops / duration,
        })
        NeuralAgent._cache.clear()
    return {
        "engine": {"map": "Onion", "bots": 8, "ticks": reply["tick"] - start_tick,
                   "seconds": engine_seconds, "ticks_per_second": (reply["tick"] - start_tick) / engine_seconds},
        "inference": measured,
    }


def dashboard(port, open_browser, inventory):
    from ofsi import dashboard as ui

    extra_css = """
        header label, header button, #status, #banner, main .card { display:none }
        main .card:has(#rp), main .card:has(#bench), main .card:has(#hw) { display:block }
        #rpCanvas { max-width:100%;height:auto !important;aspect-ratio:1 }
    """
    page = ui.PAGE.replace("</style>", extra_css + "</style>").replace(
        "Benchmarks mesures", "Rapports exportables"
    )
    page = page.replace("${x.file}</b>", '<a style="color:#93c5fd" href="/reports/${encodeURIComponent(x.file)}" download>${x.file}</a></b>')
    card = {
        "Processeur": ", ".join(x["Name"] for x in inventory.get("processors", [])) or inventory.get("cpu_fallback", ""),
        "Mémoire": f"{inventory['ram_total_bytes'] / 2**30:.1f} Gio",
        "CUDA": ", ".join(g["name"] for g in inventory["cuda_devices"] if g["usable"]) or "indisponible",
        "PyTorch": inventory["torch"],
    }

    class ReadOnlyDashboard(ui.H):
        def do_POST(self):
            self._send(405, '{"error":"lecture seule"}')

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                return self._send(200, page, "text/html")
            if path == "/api/hardware":
                return self._send(200, json.dumps({k: html.escape(v) for k, v in card.items()}))
            if path == "/api/status":
                return self._send(200, '{"banner":"Évaluation portable"}')
            if path in {"/api/notifications", "/api/runs"}:
                return self._send(200, "[]")
            if path == "/api/benchmarks":
                entries = [{"file": p.name, "summary": read_json(p).get("command", "")}
                           for p in sorted(REPORTS.glob("*.json"), reverse=True)
                           if ui.NAME_RE.fullmatch(p.stem)]
                return self._send(200, json.dumps(entries))
            if path.startswith("/reports/"):
                name = path.removeprefix("/reports/")
                if name.endswith(".json") and ui.NAME_RE.fullmatch(name[:-5]):
                    report = REPORTS / name
                    if report.is_file():
                        return self._send(200, report.read_bytes())
                return self._send(404, '{"error":"rapport introuvable"}')
            return super().do_GET()

    with ui.ThreadingHTTPServer(("127.0.0.1", port), ReadOnlyDashboard) as server:
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"Tableau de bord : {url}  (Ctrl+C pour fermer)", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("test", "benchmark", "dashboard", "replay"))
    parser.add_argument("--checkpoint", type=Path, help="checkpoint OpenFront SI v2 accompagné de son fichier .sha256")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--quick", action="store_true", help="vérification courte")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    os.environ["OFSI_NODE"] = str(ROOT / "node/node.exe")
    os.environ["OFSI_STDERR"] = "1"
    os.environ["TORCH_FORCE_WEIGHTS_ONLY_LOAD"] = "1"
    for key in ("NODE_PATH", "NODE_OPTIONS", "TSX_TSCONFIG_PATH", "ESBUILD_BINARY_PATH"):
        os.environ.pop(key, None)
    import torch

    inventory = hardware(torch)
    torch.set_num_threads(max(1, min(8, (os.cpu_count() or 1) // 2)))
    inventory["torch_threads"] = torch.get_num_threads()
    if args.command == "dashboard":
        dashboard(args.port, not args.no_browser, inventory)
        return

    from ofsi.rl2 import ckpt
    from ofsi.rl2 import eval2
    from ofsi import replay

    manifest = read_json(MANIFEST)
    checkpoint = (args.checkpoint or ROOT / manifest["checkpoint"]).resolve()
    agent = str(checkpoint)
    digest = ckpt.sha(agent)
    if digest != Path(agent + ".sha256").read_text(encoding="ascii").strip():
        raise RuntimeError("SHA-256 du checkpoint différent")
    if args.checkpoint is None and digest != manifest["checkpoint_sha256"]:
        raise RuntimeError("SHA-256 du champion différent du manifeste")
    usable = [i for i, gpu in enumerate(inventory["cuda_devices"]) if gpu["usable"]]
    if args.device == "cuda" and not usable:
        raise RuntimeError("CUDA indisponible sur ce PC. Vérifie le pilote NVIDIA ou utilise le ZIP CPU.")
    selected = "cuda" if usable and args.device != "cpu" else "cpu"
    if selected == "cuda":
        torch.cuda.set_device(usable[0])
    print(f"Modèle : {checkpoint.name} | Exécution : {selected.upper()}", flush=True)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    report = {
        "date_utc": now.isoformat(), "command": args.command, "quick": args.quick,
        "distribution": manifest, "hardware": inventory, "device": selected,
        "checkpoint_name": checkpoint.name, "checkpoint_sha256": digest,
    }
    with torch.serialization.safe_globals([torch.torch_version.TorchVersion]):
        if args.command == "test":
            maps = ["Onion"] if args.quick else eval2.TRAIN_MAPS + eval2.HELDOUT_MAPS
            specs = eval2.make_specs(maps, ["Easy"] if args.quick else ["Medium"], [8, 12],
                                     1 if args.quick else 2, 3000000)
            free_gib = inventory["ram_available_bytes"] / 2**30
            if free_gib < 2.45:
                raise RuntimeError(f"RAM libre insuffisante pour le test : {free_gib:.1f} Gio (minimum 2,45 Gio)")
            envs = min(len(specs), 4, max(1, (os.cpu_count() or 1) // 4), max(1, int((free_gib - 2.0) / 0.7)))
            games, usage, seconds = eval2.evaluate(
                agent, specs, envs=envs, max_steps=8 if args.quick else 1500, device=selected, sample=True,
            )
            failed = any(game["end"] in {"engine_error", "spawn_failed"} for game in games)
            report["result"] = {"games": games, "summary": eval2.summarize(games), "seconds": seconds,
                                "envs": envs, "torch_seed": 0, "sampled": True, "action_counts": dict(usage)}
            report["passed"] = not failed and len(games) == len(specs)
        elif args.command == "benchmark":
            devices = [("cpu", None)]
            if args.device != "cpu":
                devices.extend(("cuda", i) for i in usable)
            report["result"] = benchmark(agent, torch, devices, args.quick)
            report["passed"] = True
        else:
            name = "replay-" + run_id
            cfg = {"map": "Onion", "bots": 8, "difficulty": "Easy"}
            rec = replay.record(agent, cfg, "rp000001", name, max_steps=12 if args.quick else 1500, device=selected)
            report["result"] = {"file": f"runs/_replays/{name}.json", "frames": len(rec["frames"]),
                                "cfg": cfg, "seed": rec["seed"], "end": rec["end"], "win": rec["win"]}
            report["passed"] = len(rec["frames"]) > 0
    if ckpt.sha(agent) != digest:
        raise RuntimeError("Le fichier checkpoint a changé pendant l'exécution")
    output = REPORTS / f"{args.command}-{run_id}.json"
    write_json(output, report)
    print(f"Rapport : {output}", flush=True)
    if args.command == "replay":
        print(f"Rejeu : {ROOT / report['result']['file']} | Ouvrir DASHBOARD.bat", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
