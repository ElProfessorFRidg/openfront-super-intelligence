#!/bin/bash
# Re-preentrainement avec selection FONDEE sur ce que chaque methode optimise (ssl: dynamique hors victoire ; both: perte d'imitation), tete victoire ponderee 0,1.
cd "$(dirname "$0")"; LOG=pipeline_v3.log
.venv-gpu/Scripts/python.exe ofsi/rl2/pretrain.py --method ssl  --steps 2400 --select dyn --wm-win-weight 0.1 --out runs/init_ssl_v2  --data "data/demos_v3/shard_*.npz" > pretrain_ssl_v2.log 2>&1;  echo "[$(date +%H:%M)] re-preentrainement ssl (select=dyn) termine" >> $LOG
.venv-gpu/Scripts/python.exe ofsi/rl2/pretrain.py --method both --steps 2400 --select bc  --wm-win-weight 0.1 --out runs/init_both_v2 --data "data/demos_v3/shard_*.npz" > pretrain_both_v2.log 2>&1; echo "[$(date +%H:%M)] re-preentrainement both (select=bc) termine" >> $LOG
