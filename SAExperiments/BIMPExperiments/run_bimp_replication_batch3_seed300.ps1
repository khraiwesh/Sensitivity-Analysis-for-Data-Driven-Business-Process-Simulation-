# BIMP replication study - BATCH 3 (seed=300, ~55 experiments)
# Prerequisite: backend must already be running in another terminal:
#     cd backend
#     python app.py
param([string]$BackendUrl = "http://localhost:5000")

$ScriptDir = Split-Path -Parent $PSCommandPath
python "$ScriptDir\run_bimp_replication_batch.py" --seed 300 --backend-url $BackendUrl
