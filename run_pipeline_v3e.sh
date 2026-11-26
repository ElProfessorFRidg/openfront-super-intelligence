#!/bin/bash
# Orchestrateur v3e : RECETTE PPO CORRIGEE pour toutes les initialisations pre-entrainees (lr 1e-4, entropie 0,005, 8 mises a jour d'echauffement de la VALEUR seule).
# B_bc d'abord ; puis evaluation de B EN PARALLELE du re-preentrainement corrige (ssl select=dyn, both select=bc) ; puis D_both, C_ssl, A_random (sans echauffement).
cd "$(dirname "$0")"; LOG=pipeline_v3.log; RECIPE="--lr 1e-4 --ent 0.005 --envs 8 --T 64 --max-decisions 120000 --seed 0 --ckpt-every 10"
.venv-gpu/Scripts/python.exe ofsi/rl2/ppo2.py --name arm_B_bc --init runs/init_bc/ckpt_latest.pt --value-warmup 8 $RECIPE > runs_arm_B_bc.log 2>&1; echo "[$(date +%H:%M)] bras B_bc PPO termine (recette v2)" >> $LOG
.venv-gpu/Scripts/python.exe ofsi/rl2/eval2.py --agent runs/arm_B_bc/ckpt_latest.pt --per 2 --difficulties Easy,Medium --envs 6 --out benchmarks/arm_B_bc_eval.json > eval_arm_B_bc.log 2>&1 &
EVALPID=$!
./run_repretrain.sh
wait $EVALPID; echo "[$(date +%H:%M)] bras B_bc evalue ; re-preentrainement termine" >> $LOG
declare -A INIT=( [A_random]=random [C_ssl]=runs/init_ssl_v2/ckpt_latest.pt [D_both]=runs/init_both_v2/ckpt_latest.pt )
for arm in D_both C_ssl A_random; do
  WU=8; [ "$arm" == "A_random" ] && WU=0
  .venv-gpu/Scripts/python.exe ofsi/rl2/ppo2.py --name arm_$arm --init "${INIT[$arm]}" --value-warmup $WU $RECIPE > runs_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm PPO termine" >> $LOG
  .venv-gpu/Scripts/python.exe ofsi/rl2/eval2.py --agent runs/arm_$arm/ckpt_latest.pt --per 2 --difficulties Easy,Medium --envs 8 --out benchmarks/arm_${arm}_eval.json > eval_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm evalue" >> $LOG
done
echo "[$(date +%H:%M)] PIPELINE TERMINE" >> $LOG
