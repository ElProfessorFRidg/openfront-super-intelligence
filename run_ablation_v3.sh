#!/bin/bash
# Ablation par regle du professeur v3 sur les MEMES parties Medium (seeds fixes) que v2+alliance. Sequentiel.
cd "$(dirname "$0")"
ALL='"sam","warship","hbomb","cancel","embargo","extend","break","target","emoji","donate"'
run() { python ofsi/rl2/eval2.py --agent teacher3 --agent-params "{\"rules\":[$2]}" --per 2 --difficulties Easy,Medium --only Medium --envs 8 --out benchmarks/abl_$1.json > abl_$1.log 2>&1; }
run no_break_target '"sam","warship","hbomb","cancel","embargo","extend","emoji","donate"'
run no_break '"sam","warship","hbomb","cancel","embargo","extend","target","emoji","donate"'
run safe_only '"sam","extend","cancel","embargo","hbomb","warship"'
run none ''
