#!/bin/bash
# Comparaison des initialisations : PPO a BUDGET IDENTIQUE (120 000 decisions, 8 envs, meme seed, meme curriculum) puis evaluation sur les 48 parties de reference.
cd "$(dirname "$0")"
declare -A INIT=( [A_random]=random [B_bc]=runs/init_bc/ckpt_latest.pt [C_ssl]=runs/init_ssl/ckpt_latest.pt [D_both]=runs/init_both/ckpt_latest.pt )
for arm in A_random B_bc C_ssl D_both; do
  [ -f runs/arm_$arm/DONE ] && continue
  if [ "${INIT[$arm]}" != "random" ]; then while [ ! -f "${INIT[$arm]}.sha256" ]; do sleep 20; done; fi
  .venv-gpu/Scripts/python.exe ofsi/rl2/ppo2.py --name arm_$arm --init "${INIT[$arm]}" --envs 8 --T 64 --max-decisions 120000 --seed 0 --ckpt-every 10 > runs_arm_$arm.log 2>&1
  .venv-gpu/Scripts/python.exe ofsi/rl2/eval2.py --agent runs/arm_$arm/ckpt_latest.pt --per 2 --difficulties Easy,Medium --envs 8 --out benchmarks/arm_${arm}_eval.json > eval_arm_$arm.log 2>&1
  touch runs/arm_$arm/DONE
done
