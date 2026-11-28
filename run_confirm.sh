#!/bin/bash
# Confirmation sur parties JAMAIS utilisees (seed0 5 000 000, Medium, 96 parties) : professeur, champion, candidat faible. Sequentiel. Protocole : docs/JOURNAL.md 2026-11-28.
cd "$(dirname "$0")"; . .venv/bin/activate; export PATH=$PWD/tools/node24/node_modules/.bin:$PATH
nice -n 5 python ofsi/rl2/eval_planner.py --arm teacher --params '{"ally_mode":"threats"}' --difficulty Medium --per 8 --seed0 5000000 --workers 4 --out benchmarks/confirm_teacher.json > confirm_teacher.log 2>&1
for pair in "champion:runs/arm_C_medium/ckpt_latest.pt" "weak:runs/orch_c32654699_s0_weak/ckpt_latest.pt"; do
  n=${pair%%:*}; c=${pair#*:}
  nice -n 5 python ofsi/rl2/eval2.py --agent $c --per 8 --difficulties Medium --seed0 5000000 --envs 6 --sample --out benchmarks/confirm_$n.json > confirm_$n.log 2>&1
done
echo FIN > confirm.done
