#!/bin/bash
# Les 3 methodes de preentrainement, MEME nombre de pas d'optimisation (2400), memes donnees, meme seed.
cd "$(dirname "$0")"
for m in bc ssl both; do
  .venv-gpu/Scripts/python.exe ofsi/rl2/pretrain.py --method $m --steps 2400 --out runs/init_$m --data "data/demos_v2/shard_*.npz" 2>&1 | grep -v "Warning\|warn"
done
