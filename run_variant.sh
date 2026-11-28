#!/bin/bash
# Confirmation de la variante prudente (scriptee) sur 96 parties Medium neuves. Attend la fin du pipeline de diversite. Protocole : docs/JOURNAL.md 2026-11-29.
cd "$(dirname "$0")"; while [ ! -f div.done ]; do sleep 30; done
. .venv/bin/activate; export PATH=$PWD/tools/node24/node_modules/.bin:$PATH
nice -n 5 python ofsi/rl2/eval_planner.py --arm teacher --params '{"ally_mode":"threats"}' --difficulty Medium --per 8 --seed0 8000000 --workers 4 --out benchmarks/var_default.json > var_default.log 2>&1
nice -n 5 python ofsi/rl2/eval_planner.py --arm teacher --params '{"ally_mode":"threats","ratio":2.5,"defend":0.8}' --difficulty Medium --per 8 --seed0 8000000 --workers 4 --out benchmarks/var_prudent.json > var_prudent.log 2>&1
echo FIN > var.done
