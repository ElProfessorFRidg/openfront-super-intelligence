#!/bin/bash
# Evaluation sur HARD, 96 parties jamais utilisees. Sequentiel. Protocole : docs/JOURNAL.md 2026-11-29.
cd "$(dirname "$0")"; . .venv/bin/activate; export PATH=$PWD/tools/node24/node_modules/.bin:$PATH
nice -n 5 python ofsi/rl2/eval_planner.py --arm teacher --params '{"ally_mode":"threats"}' --difficulty Hard --per 8 --seed0 6000000 --workers 4 --out benchmarks/hard_teacher.json > hard_teacher.log 2>&1
for pair in "champion:runs/arm_C_medium/ckpt_latest.pt" "s1:runs/orch_c32654699_s1/ckpt_latest.pt" "weak:runs/orch_c32654699_s0_weak/ckpt_latest.pt"; do
  n=${pair%%:*}; c=${pair#*:}
  nice -n 5 python ofsi/rl2/eval2.py --agent $c --per 8 --difficulties Hard --seed0 6000000 --envs 6 --sample --out benchmarks/hard_$n.json > hard_$n.log 2>&1
done
echo FIN > hard.done
