#!/bin/bash
# Capacite du reseau vs imitation : A (1,41 M) puis B (6,8 M), memes donnees/pas/graine, CPU. Protocole : docs/JOURNAL.md 2026-11-28.
cd "$(dirname "$0")"; . .venv/bin/activate; export PATH=$PWD/tools/node24/node_modules/.bin:$PATH
nice -n 5 python ofsi/rl2/pretrain.py --method bc --steps 2400 --seed 0 --out runs/cap_A_1m4 --data "data/demos_v3/shard_*.npz" > cap_A.log 2>&1
nice -n 5 python ofsi/rl2/pretrain.py --method bc --steps 2400 --seed 0 --d-model 256 --layers 6 --heads 8 --ff 1024 --out runs/cap_B_6m8 --data "data/demos_v3/shard_*.npz" > cap_B.log 2>&1
echo FIN > cap.done
