#!/usr/bin/env bash
# OpenFront Super Intelligence — lanceur local Linux/macOS (equivalent de OpenFront-SI.ps1). Aucune cle API, aucun compte, aucun service permanent.
# Usage : ./ofsi.sh <setup|doctor|repair|dashboard|train|stop|evaluate|skills|autotune|orchestrate|notify>
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"
ENGINE_URL="https://github.com/openfrontio/openfrontio"; ENGINE_COMMIT="db8bf7c4195bd3e2e4fb7936889dc406b42fe44a"
NODE_BIN="$ROOT/tools/node24/node_modules/.bin"; PY="$ROOT/.venv/bin/python"
say() { printf '[ofsi] %s\n' "$*"; }
use_env() { export PATH="$NODE_BIN:$PATH"; }

sync_adapter() { rm -rf vendor/openfront-engine/osi && cp -r adapter vendor/openfront-engine/osi; }

cmd_setup() {   # idempotent : ne refait que ce qui manque ; ne touche jamais aux checkpoints
  if [ ! -x "$NODE_BIN/node" ]; then say "Node 24 + npm 12 (paquets npm 'node@24', 'npm@12') dans tools/node24"; mkdir -p tools/node24 && (cd tools/node24 && npm init -y >/dev/null && npm i node@24 npm@12 >/dev/null) || { say "ECHEC installation Node"; return 1; }; fi
  use_env
  if [ ! -d vendor/openfront-engine/.git ] || [ "$(git -C vendor/openfront-engine rev-parse HEAD 2>/dev/null)" != "$ENGINE_COMMIT" ]; then
    say "Moteur officiel au commit epingle $ENGINE_COMMIT"; mkdir -p vendor/openfront-engine; (cd vendor/openfront-engine && { [ -d .git ] || git init -q; } && { git remote add origin "$ENGINE_URL" 2>/dev/null; true; } \
      && GIT_LFS_SKIP_SMUDGE=1 git fetch --depth=1 origin "$ENGINE_COMMIT" && git checkout -q FETCH_HEAD) || { say "ECHEC recuperation du moteur"; return 1; }; fi
  [ -d vendor/openfront-engine/node_modules ] || (cd vendor/openfront-engine && npm ci --ignore-scripts) || { say "ECHEC npm ci"; return 1; }
  if [ ! -x "$PY" ]; then say "venv Python (numpy + torch CPU ; pour un GPU CUDA installer le torch adapte dans .venv)"; python3 -m venv .venv && .venv/bin/pip install -q numpy && .venv/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu || return 1; fi
  sync_adapter; say "Smoke test moteur (snapshot/restore)"; (cd vendor/openfront-engine && ENGINE_COMMIT="$ENGINE_COMMIT" node node_modules/tsx/dist/cli.mjs osi/scripts/selftest_snapshot.mts 2>/dev/null | tail -1)
  cmd_doctor
}

cmd_doctor() {  # lecture seule
  use_env; local ok=0
  if [ -x "$NODE_BIN/node" ]; then say "Node : $("$NODE_BIN/node" -v)"; else say "Node 24 ABSENT : ./ofsi.sh setup"; ok=1; fi
  [ -d vendor/openfront-engine/node_modules ] && say "Moteur : dependances installees (commit $(git -C vendor/openfront-engine rev-parse --short HEAD 2>/dev/null))" || { say "Moteur : absent (./ofsi.sh setup)"; ok=1; }
  if [ -x "$PY" ]; then say "PyTorch : $("$PY" -c 'import torch;print(torch.__version__, "cuda "+torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu")' 2>&1 | tail -1)"; else say "venv ABSENT : ./ofsi.sh setup"; ok=1; fi
  say "CPU : $(nproc) coeurs ; RAM libre : $(awk '/MemAvailable/{printf "%.1f Go", $2/1048576}' /proc/meminfo) ; disque libre : $(df -BG --output=avail "$ROOT" | tail -1 | tr -d ' ')"
  for c in runs/*/ckpt_latest.pt; do [ -f "$c" ] || continue; local want got; want="$(cut -d' ' -f1 "$c.sha256" 2>/dev/null)"; got="$(sha256sum "$c" | cut -d' ' -f1)"
    if [ -z "$want" ]; then say "checkpoint $(basename "$(dirname "$c")") : pas de .sha256"; elif [ "$want" = "$got" ]; then say "checkpoint $(basename "$(dirname "$c")") : SHA-256 OK"; else say "checkpoint $(basename "$(dirname "$c")") : SHA-256 DIFFERENT (en cours d'ecriture ou corrompu)"; fi; done
  return $ok
}

cmd_dashboard() { sync_adapter; pgrep -f "ofsi/dashboard.py" >/dev/null && say "tableau de bord deja lance" || { nohup "$PY" ofsi/dashboard.py > dashboard.log 2>&1 & sleep 1; }; say "tableau de bord : http://127.0.0.1:8765 (loopback uniquement)"; }

cmd_train() {   # train [nom] [checkpoint_init] ; recette ANCREE (voir docs/JOURNAL.md)
  use_env; sync_adapter; local name="${1:-run_$(date +%Y%m%d_%H%M)}" init="${2:-}"; local extra=()
  [ -n "$init" ] && extra=(--init "$init" --value-warmup 8 --lr 3e-5 --ent 0.005 --kl-ref 1.0 --bc-coef 0.5)
  nohup "$PY" ofsi/rl2/ppo2.py --name "$name" --envs "$(( $(nproc) > 8 ? 8 : $(nproc) ))" --T 64 "${extra[@]}" > "runs_$name.log" 2>&1 &
  say "entrainement '$name' lance (PID $!) ; arret propre : ./ofsi.sh stop"
}
cmd_stop() { for d in runs/*/; do [ -f "$d/metrics.jsonl" ] && touch "$d/STOP" && say "STOP demande pour $(basename "$d") (checkpoint sauvegarde a la fin de la mise a jour)"; done; }
cmd_evaluate() { use_env; [ $# -ge 1 ] || { say "usage : ./ofsi.sh evaluate <checkpoint.pt> [sortie.json]"; return 2; }; sync_adapter; "$PY" ofsi/rl2/eval2.py --agent "$1" --per 2 --difficulties Easy,Medium --envs "${OFSI_ENVS:-6}" --out "${2:-benchmarks/eval_$(basename "$(dirname "$1")").json}"; }
cmd_skills() { use_env; sync_adapter; "$PY" ofsi/run_skills.py --out "${1:-benchmarks/skills_$(date +%Y%m%d).json}"; }
cmd_autotune() { use_env; sync_adapter; "$PY" ofsi/autotune.py "$@"; }
cmd_orchestrate() { use_env; sync_adapter; nohup "$PY" ofsi/orchestrator.py "$@" > runs_orchestrator.log 2>&1 & say "orchestrateur lance (PID $!) ; arret propre : touch runs/_orch/STOP ; journal : runs/_orch/cycles.jsonl"; }
cmd_notify() { "$PY" ofsi/notify.py; }

case "${1:-help}" in
  setup) cmd_setup;; doctor) cmd_doctor;; repair) sync_adapter; cmd_doctor;; dashboard) cmd_dashboard;; train) shift; cmd_train "$@";; stop) cmd_stop;;
  orchestrate) shift; cmd_orchestrate "$@";; autotune) shift; cmd_autotune "$@";; evaluate) shift; cmd_evaluate "$@";; skills) shift; cmd_skills "$@";; notify) cmd_notify;;
  *) sed -n 2,3p "$0";;
esac
