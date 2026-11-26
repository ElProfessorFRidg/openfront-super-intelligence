#!/bin/bash
# Variantes du professeur sur Medium, memes parties (cartes d'entrainement uniquement), memes seeds.
cd "$(dirname "$0")"
i=0
for P in '{"reserve":0.3}' '{"reserve":0.55,"send":2,"expand":2}' '{"reserve":0.6,"send":2,"expand":1,"ratio":2.0}' '{"reserve":0.45,"send":3,"expand":2,"ratio":2.2,"defend":0.25}'; do
  i=$((i+1)); python ofsi/rl2/eval2.py --agent teacher --agent-params "$P" --maps train --per 2 --difficulties Medium --envs 8 --out benchmarks/sweep_teacher_$i.json > /dev/null 2>&1
done
