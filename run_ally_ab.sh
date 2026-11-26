#!/bin/bash
# A/B : politique d'alliance du professeur, MEMES 48 parties que eval2_teacher (seeds fixes). Sequentiel (memoire).
cd "$(dirname "$0")"
for mode in threats all; do
  python ofsi/rl2/eval2.py --agent teacher --agent-params "{\"ally_mode\":\"$mode\"}" --per 2 --difficulties Easy,Medium --envs 8 --out benchmarks/eval2_teacher_ally_$mode.json > eval_ally_$mode.log 2>&1
done
