# BIMP replication study - BATCH 2 (seed=200, ~56 experiments)
# Prerequisite: backend must already be running in another terminal:
#     cd backend
#     python app.py
param([string]$BackendUrl = "http://localhost:5000")

$ScriptDir = Split-Path -Parent $PSCommandPath
python "$ScriptDir\run_bimp_replication_batch.py" --seed 200 --backend-url $BackendUrl
