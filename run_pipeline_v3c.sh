#!/bin/bash
# Suite du pipeline v3b (script stoppe volontairement pour REORDONNER les bras du plus informatif au moins informatif).
# 1) attendre la fin du preentrainement SSL deja en cours ; 2) preentrainement "both" ; 3) bras PPO : B_bc, D_both, C_ssl, A_random ; chacun suivi de son evaluation.
cd "$(dirname "$0")"; LOG=pipeline_v3.log
while ! grep -q "^checkpoint:" pretrain_ssl.log 2>/dev/null; do sleep 20; done; echo "[$(date +%H:%M)] preentrainement ssl (meilleure validation) termine" >> $LOG
.venv-gpu/Scripts/python.exe ofsi/rl2/pretrain.py --method both --steps 2400 --out runs/init_both --data "data/demos_v3/shard_*.npz" > pretrain_both.log 2>&1; echo "[$(date +%H:%M)] preentrainement both (meilleure validation) termine" >> $LOG
declare -A INIT=( [A_random]=random [B_bc]=runs/init_bc/ckpt_latest.pt [C_ssl]=runs/init_ssl/ckpt_latest.pt [D_both]=runs/init_both/ckpt_latest.pt )
for arm in B_bc D_both C_ssl A_random; do
  .venv-gpu/Scripts/python.exe ofsi/rl2/ppo2.py --name arm_$arm --init "${INIT[$arm]}" --envs 8 --T 64 --max-decisions 120000 --seed 0 --ckpt-every 10 > runs_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm PPO termine" >> $LOG
  .venv-gpu/Scripts/python.exe ofsi/rl2/eval2.py --agent runs/arm_$arm/ckpt_latest.pt --per 2 --difficulties Easy,Medium --envs 8 --out benchmarks/arm_${arm}_eval.json > eval_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm evalue" >> $LOG
done
echo "[$(date +%H:%M)] PIPELINE TERMINE" >> $LOG
