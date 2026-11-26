#!/bin/bash
# Pipeline corrige (observations type-de-joueur OK, 32 types, professeur ally_mode=threats). SEQUENTIEL (contrainte memoire ~16 moteurs max).
cd "$(dirname "$0")"
LOG=pipeline_v3.log; echo "[$(date +%H:%M)] debut" > $LOG
# 0) preuves de competence completes (28+ scenarios)
python ofsi/run_skills.py "" --out benchmarks/skills_full.json --workers 8 > skills_full.log 2>&1; echo "[$(date +%H:%M)] skills_full termine" >> $LOG
# 1) collecte de demonstrations (cartes d'entrainement UNIQUEMENT ; difficultes Easy/Medium/Hard/Impossible)
python ofsi/rl2/collect_v2.py --maps Onion,Pangaea,Caucasus,BosphorusStraits,Iceland,BeringStrait,DanishStraits,BlackSea --difficulties Easy,Medium,Hard,Impossible --bots 6,10,14 --envs 12 --decisions 60000 --out data/demos_v3 --seed 1 --teacher-params '{"ally_mode":"threats"}' > collect_v3.log 2>&1; echo "[$(date +%H:%M)] collecte terminee" >> $LOG
# 2) preentrainement : 3 methodes, MEMES pas (2400), memes donnees
for m in bc ssl both; do .venv-gpu/Scripts/python.exe ofsi/rl2/pretrain.py --method $m --steps 2400 --out runs/init_$m --data "data/demos_v3/shard_*.npz" > pretrain_$m.log 2>&1; echo "[$(date +%H:%M)] preentrainement $m termine" >> $LOG; done
# 3) 4 bras PPO a budget identique (120 000 decisions, 8 envs, seed 0) + evaluation sur les 48 parties de reference
declare -A INIT=( [A_random]=random [B_bc]=runs/init_bc/ckpt_latest.pt [C_ssl]=runs/init_ssl/ckpt_latest.pt [D_both]=runs/init_both/ckpt_latest.pt )
for arm in A_random B_bc C_ssl D_both; do
  .venv-gpu/Scripts/python.exe ofsi/rl2/ppo2.py --name arm_$arm --init "${INIT[$arm]}" --envs 8 --T 64 --max-decisions 120000 --seed 0 --ckpt-every 10 > runs_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm PPO termine" >> $LOG
  .venv-gpu/Scripts/python.exe ofsi/rl2/eval2.py --agent runs/arm_$arm/ckpt_latest.pt --per 2 --difficulties Easy,Medium --envs 8 --out benchmarks/arm_${arm}_eval.json > eval_arm_$arm.log 2>&1; echo "[$(date +%H:%M)] bras $arm evalue" >> $LOG
done
echo "[$(date +%H:%M)] PIPELINE TERMINE" >> $LOG
