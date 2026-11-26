#!/bin/bash
cd "$(dirname "$0")"
while [ ! -f benchmarks/abl_none.json ]; do sleep 20; done      # attendre la fin de la 1re serie (memoire)
python ofsi/rl2/eval2.py --agent teacher3 --agent-params '{"rules":["sam","warship","hbomb","cancel","embargo","extend","break","emoji","donate"]}' --per 2 --difficulties Easy,Medium --only Medium --envs 8 --out benchmarks/abl_no_target.json > abl_no_target.log 2>&1
