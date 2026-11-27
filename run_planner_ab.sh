#!/bin/bash
# Bras planificateur (les bras professeur seul sont deja mesures : benchmarks/plan_teacher_*.json). Protocole + amendement : docs/JOURNAL.md 2026-11-27. Reprenable (.partial.jsonl).
cd "$(dirname "$0")"; . .venv/bin/activate; export PATH=$PWD/tools/node24/node_modules/.bin:$PATH
for ally in threats none; do
  nice -n 10 python ofsi/rl2/eval_planner.py --arm planner --params "{\"ally_mode\":\"$ally\"}" --workers 4 --every 8 --out benchmarks/plan_planner_$ally.json >> plan_planner_$ally.log 2>&1
done
echo FIN > plan_ab.done
