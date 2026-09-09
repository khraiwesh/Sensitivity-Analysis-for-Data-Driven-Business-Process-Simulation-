"""
run_simulations_datamining_v3.py
-----------------------------------
Runs Prosimos simulations for the DataMining individual-group perturbed
models created by create_models_datamining_v3.py.

IMPORTANT: the "original" baseline used here is
model_original_datamining_v3_padded.json (produced by create_models_
datamining_v3.py), NOT the raw ConsultaDataMining201618_train.json.
The raw file has 14 of its 17 resource-calendar templates missing one or
more weekdays entirely, which crashes a plain (unpatched) local Prosimos
install -- Samira's own cluster pipeline has a custom fix for this that
our pip-installed Prosimos does not have. The padded copy applies the
exact same workaround (zero-length periods on empty weekdays) without
changing the model's behaviour, so it is the correct "unperturbed"
baseline to compare every perturbed model against.

Output goes to datamining_v3/ (a sibling folder next to this script).

Run:
    conda activate thesis_env
    python3 run_simulations_datamining_v3.py
"""

import os
import time
import pandas as pd
from prosimos.simulation_engine import run_simulation

# ─────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────

# EDIT if your files live somewhere else
BPMN_PATH = os.path.expanduser(
    "~/Desktop/datamining_eval/ConsultaDataMining201618_train.bpmn"
)

# script lives in datamining_eval/, alongside all the model_*.json files
_script_dir = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_JSON_PATH = os.path.join(_script_dir, "model_original_datamining_v3_padded.json")
MODELS_DIR = _script_dir
OUTPUT_DIR = os.path.join(_script_dir, "datamining_v3")

TOTAL_CASES = 3000  # matches Samira's SA runs (see DataMining README)
SEEDS = [1, 2, 3, 4, 5]

MODELS = [
    ("original", None),  # handled specially below (uses ORIGINAL_JSON_PATH)
    ("RC", "model_RC_datamining_v3.json"),
    ("AD", "model_AD_datamining_v3.json"),
    ("RN", "model_RN_datamining_v3.json"),
    ("TR", "model_TR_datamining_v3.json"),
    ("AC", "model_AC_datamining_v3.json"),
]


# ─────────────────────────────────────────────
# 2. SETUP OUTPUT FOLDERS
# ─────────────────────────────────────────────

def setup_output_dirs():
    logs_dir = os.path.join(OUTPUT_DIR, "logs")
    kpis_dir = os.path.join(OUTPUT_DIR, "kpis")
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(kpis_dir, exist_ok=True)
    print("Output directories ready:")
    print(f"  Logs: {logs_dir}")
    print(f"  KPIs: {kpis_dir}")
    return logs_dir, kpis_dir


# ─────────────────────────────────────────────
# 3. KPI EXTRACTION (identical to the other run_simulations_*_v3.py scripts)
# ─────────────────────────────────────────────

def extract_kpis_from_log(log_path):
    df = pd.read_csv(log_path)
    df.columns = [c.lower().strip() for c in df.columns]

    case_col = None
    for col in ["case_id", "caseid", "case"]:
        if col in df.columns:
            case_col = col
            break
    if case_col is None:
        print(f"  [!] Could not find case_id column. Columns: {list(df.columns)}")
        return None

    start_col = None
    end_col = None
    for col in df.columns:
        if "start" in col:
            start_col = col
        if "end" in col or "complete" in col:
            end_col = col

    if start_col is None or end_col is None:
        print(f"  [!] Could not find start/end time columns. Columns: {list(df.columns)}")
        return None

    df[start_col] = pd.to_datetime(df[start_col])
    df[end_col] = pd.to_datetime(df[end_col])

    case_times = df.groupby(case_col).agg(
        case_start=(start_col, "min"),
        case_end=(end_col, "max")
    )
    case_times["cycle_time_sec"] = (
        case_times["case_end"] - case_times["case_start"]
    ).dt.total_seconds()

    avg_cycle_time = case_times["cycle_time_sec"].mean()
    throughput = len(case_times)

    avg_waiting_time = None
    avg_processing_time = None
    for col in df.columns:
        if "waiting" in col or "wait_time" in col:
            avg_waiting_time = df[col].mean()
        if "processing" in col or "proc_time" in col:
            avg_processing_time = df[col].mean()

    return {
        "avg_cycle_time_sec": round(avg_cycle_time, 2),
        "avg_waiting_time_sec": round(avg_waiting_time, 2) if avg_waiting_time else None,
        "avg_processing_time_sec": round(avg_processing_time, 2) if avg_processing_time else None,
        "throughput": throughput
    }


# ─────────────────────────────────────────────
# 4. RUN ONE SIMULATION
# ─────────────────────────────────────────────

def run_one_simulation(model_name, json_path, seed, logs_dir, kpis_dir):
    log_filename = f"log_{model_name}_seed{seed}.csv"
    log_path = os.path.join(logs_dir, log_filename)

    print(f"  Running: {model_name} | seed={seed} | cases={TOTAL_CASES}")
    start_time = time.time()

    try:
        run_simulation(
            bpmn_path=BPMN_PATH,
            json_path=json_path,
            total_cases=TOTAL_CASES,
            log_out_path=log_path,
            starting_at="2018-01-01T00:00:00+00:00",
        )

        elapsed = round(time.time() - start_time, 1)
        print(f"    Done in {elapsed}s -> {log_filename}")

        kpis = extract_kpis_from_log(log_path)

        if kpis:
            print(f"    KPIs: cycle={kpis['avg_cycle_time_sec']}s | "
                  f"throughput={kpis['throughput']}")

            kpi_filename = f"kpi_{model_name}_seed{seed}.csv"
            kpi_path = os.path.join(kpis_dir, kpi_filename)
            kpi_row = {"model": model_name, "seed": seed, **kpis}
            pd.DataFrame([kpi_row]).to_csv(kpi_path, index=False)

        return kpis

    except Exception as e:
        print(f"    FAILED: {e}")
        return None


# ─────────────────────────────────────────────
# 5. MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DataMining (v3, quantile-based) -- Running simulations")
    print(f"Models: {len(MODELS)} | Seeds: {len(SEEDS)} | Cases: {TOTAL_CASES}")
    print(f"Total runs: {len(MODELS) * len(SEEDS)}")
    print(f"Baseline JSON: {ORIGINAL_JSON_PATH}")
    print("=" * 60)

    if not os.path.exists(ORIGINAL_JSON_PATH):
        print(f"\n[!] Padded baseline not found at {ORIGINAL_JSON_PATH}")
        print("    Run create_models_datamining_v3.py first.")
        return

    logs_dir, kpis_dir = setup_output_dirs()
    print()

    all_results = []

    for model_name, json_filename in MODELS:
        json_path = ORIGINAL_JSON_PATH if model_name == "original" else os.path.join(MODELS_DIR, json_filename)

        print(f"\n── Model: {model_name} ──")
        print(f"   JSON: {json_path}")

        if not os.path.exists(json_path):
            print("   [!] JSON file not found -- skipping")
            continue

        for seed in SEEDS:
            kpis = run_one_simulation(model_name, json_path, seed, logs_dir, kpis_dir)
            if kpis:
                all_results.append({"model": model_name, "seed": seed, **kpis})

    if all_results:
        summary_path = os.path.join(OUTPUT_DIR, "kpi_summary_all.csv")
        pd.DataFrame(all_results).to_csv(summary_path, index=False)
        print(f"\n{'='*60}")
        print("All simulations complete!")
        print(f"Combined KPI summary saved to:\n  {summary_path}")
        print(f"{'='*60}")

        df = pd.DataFrame(all_results)
        print("\nAverage cycle times per model:")
        print(df.groupby("model")["avg_cycle_time_sec"].mean().round(1).to_string())
    else:
        print("\n[!] No results collected -- check the errors above "
              "(if every run FAILED, the empty-weekday padding may need "
              "review, or Prosimos itself is missing/broken in this env).")


if __name__ == "__main__":
    main()
