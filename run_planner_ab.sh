#!/bin/bash
# Evaluation appariee professeur vs professeur+planificateur (24 parties Medium). Protocole : docs/JOURNAL.md 2026-11-26.
cd "$(dirname "$0")"; . .venv/bin/activate; export PATH=$PWD/tools/node24/node_modules/.bin:$PATH
for ally in threats none; do
  nice -n 10 python ofsi/rl2/eval_planner.py --arm teacher --params "{\"ally_mode\":\"$ally\"}" --workers 2 --out benchmarks/plan_teacher_$ally.json > plan_teacher_$ally.log 2>&1
  nice -n 10 python ofsi/rl2/eval_planner.py --arm planner --params "{\"ally_mode\":\"$ally\"}" --workers 3 --out benchmarks/plan_planner_$ally.json > plan_planner_$ally.log 2>&1
done
echo FIN > plan_ab.done
