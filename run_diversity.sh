#!/bin/bash
# Diversite des donnees : collecte v4 (4 variantes du professeur), imitation v3+v4, evaluation. Protocole : docs/JOURNAL.md 2026-11-29. Reprenable par etape (fichiers *.done).
cd "$(dirname "$0")"; . .venv/bin/activate; export PATH=$PWD/tools/node24/node_modules/.bin:$PATH
M=Onion,Pangaea,Caucasus,BosphorusStraits,Iceland,BeringStrait,DanishStraits,BlackSea
i=0
for P in '{"ally_mode":"all"}' '{"ally_mode":"threats","ratio":1.773,"reserve":0.292,"defend":0.511,"ally_ratio":0.554,"city_per_tiles":1500}' '{"ally_mode":"threats","ratio":1.0,"reserve":0.15}' '{"ally_mode":"threats","ratio":2.5,"defend":0.8}'; do
  i=$((i+1)); [ -f div_collect_$i.done ] && continue
  nice -n 5 python ofsi/rl2/collect_v2.py --maps $M --difficulties Easy,Medium,Hard --bots 6,10,14 --envs 12 --decisions 15000 --out data/demos_v4 --seed $((i+1)) --teacher-params "$P" > div_collect_$i.log 2>&1 && echo ok > div_collect_$i.done
done
[ -f runs/div_C/ckpt_latest.pt ] || nice -n 5 python ofsi/rl2/pretrain.py --method bc --steps 2400 --seed 0 --out runs/div_C --data "data/demos_v[34]/shard_*.npz" > div_C.log 2>&1
nice -n 5 python ofsi/rl2/eval_planner.py --arm teacher --params '{"ally_mode":"threats"}' --difficulty Medium --per 8 --seed0 7000000 --workers 4 --out benchmarks/div_teacher.json > div_teacher.log 2>&1
for pair in "A:runs/cap_A_1m4/ckpt_latest.pt" "C:runs/div_C/ckpt_latest.pt"; do n=${pair%%:*}; c=${pair#*:}
  nice -n 5 python ofsi/rl2/eval2.py --agent $c --per 8 --difficulties Medium --seed0 7000000 --envs 6 --sample --out benchmarks/div_$n.json > div_$n.log 2>&1; done
echo FIN > div.done
