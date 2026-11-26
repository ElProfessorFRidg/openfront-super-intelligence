#!/bin/bash
# Reprise du pipeline v3 : preentrainement avec SELECTION PAR VALIDATION (meme regle pour les 3 methodes), puis 4 bras PPO a budget identique + evaluation.
cd "$(dirname "$0")"; LOG=pipeline_v3.log
for m in bc ssl both; do .venv-gpu/Scripts/python.exe ofsi/rl2/pretrain.py --method $m --steps 2400 --out runs/init_$m --data "data/demos_v3/shard_*.npz" > pretrain_$m.log 2>&1; echo "[$(date +%H:%M)] preentrainement $m (meilleure validation) termine" >> $LOG; done
declare -A INIT=( [A_random]=random [B_bc]=runs/init_bc/ckpt_latest.pt [C_ssl]=runs/init_ssl/ckpt_latest.pt [D_both]=runs/init_both/ckpt_latest.pt )
for arm in A_random B_bc C_ssl D_both; do
  .venv-gpu/Scripts/python.exe ofsi/rl2/ppo2.py --name arm_$arm --init "${INIT[$arm]}" --envs 8 --T 64 --max-decisions 120000 --seed 0 --ckpt-every 10 > runs_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm PPO termine" >> $LOG
  .venv-gpu/Scripts/python.exe ofsi/rl2/eval2.py --agent runs/arm_$arm/ckpt_latest.pt --per 2 --difficulties Easy,Medium --envs 8 --out benchmarks/arm_${arm}_eval.json > eval_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm evalue" >> $LOG
done
echo "[$(date +%H:%M)] PIPELINE TERMINE" >> $LOG
