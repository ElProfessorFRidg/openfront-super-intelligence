#!/bin/bash
# Orchestrateur v3d : (1) attendre la fin du PPO du bras B (processus deja lance) ; (2) EVALUER B en parallele du RE-PREENTRAINEMENT corrige (ssl select=dyn, both select=bc) ;
# (3) bras D (init both_v2), C (init ssl_v2), A (aleatoire), chacun suivi de son evaluation. Garde-fous memoire dans ppo2/eval2.
cd "$(dirname "$0")"; LOG=pipeline_v3.log
isrunning() { powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match '$1' }) { exit 0 } else { exit 1 }"; }
while isrunning "name arm_B_bc"; do sleep 30; done; echo "[$(date +%H:%M)] bras B_bc PPO termine" >> $LOG
.venv-gpu/Scripts/python.exe ofsi/rl2/eval2.py --agent runs/arm_B_bc/ckpt_latest.pt --per 2 --difficulties Easy,Medium --envs 6 --out benchmarks/arm_B_bc_eval.json > eval_arm_B_bc.log 2>&1 &
EVALPID=$!
./run_repretrain.sh
wait $EVALPID; echo "[$(date +%H:%M)] bras B_bc evalue ; re-preentrainement termine" >> $LOG
declare -A INIT=( [A_random]=random [C_ssl]=runs/init_ssl_v2/ckpt_latest.pt [D_both]=runs/init_both_v2/ckpt_latest.pt )
for arm in D_both C_ssl A_random; do
  .venv-gpu/Scripts/python.exe ofsi/rl2/ppo2.py --name arm_$arm --init "${INIT[$arm]}" --envs 8 --T 64 --max-decisions 120000 --seed 0 --ckpt-every 10 > runs_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm PPO termine" >> $LOG
  .venv-gpu/Scripts/python.exe ofsi/rl2/eval2.py --agent runs/arm_$arm/ckpt_latest.pt --per 2 --difficulties Easy,Medium --envs 8 --out benchmarks/arm_${arm}_eval.json > eval_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm evalue" >> $LOG
done
echo "[$(date +%H:%M)] PIPELINE TERMINE" >> $LOG
