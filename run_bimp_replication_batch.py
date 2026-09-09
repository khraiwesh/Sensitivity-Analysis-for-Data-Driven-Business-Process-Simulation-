"""
Batch runner for the BIMP-simulator replication study.

Reads one row per experiment from the settings Excel file
(BIMP_replication_settings_500_1000.xlsx) and replays each one through the
running Flask backend's /simulate endpoint with simulator="bimp". Each call
triggers the full production pipeline (sampling -> BIMP simulation ->
Sobol/Morris sensitivity analysis -> .xlsx export), exactly like the existing
run_batch_*.ps1 scripts already used in this project - just driven from
Excel instead of hard-coded values, and with a resumable Excel run-log.

PREREQUISITES
--------------
1. Start the backend once, in its own terminal, and leave it running:
       cd backend
       python app.py
   (wait for "Running on http://0.0.0.0:5000")

2. In a second terminal (repo root, with the project's venv activated), run
   this script. See "USAGE EXAMPLES" below.

The settings Excel has 169 rows but 2 are exact duplicates (same
bimp_folder_name / same parameters, referenced from two different original
studies) -> 167 unique experiments actually get run. They split naturally
into 3 batches by seed (100 / 200 / 300, ~56 experiments each).

USAGE EXAMPLES
--------------
    # See what would run for batch 1 (seed=100) without calling anything
    python run_bimp_replication_batch.py --seed 100 --dry-run

    # Run batch 1 (seed=100)
    python run_bimp_replication_batch.py --seed 100

    # Run batch 2 / batch 3
    python run_bimp_replication_batch.py --seed 200
    python run_bimp_replication_batch.py --seed 300

    # Run everything (all 3 batches back-to-back in one process)
    python run_bimp_replication_batch.py

    # Smoke test: only the first 2 experiments of batch 1
    python run_bimp_replication_batch.py --seed 100 --limit 2

    # Re-run experiments whose output folder already looks complete
    python run_bimp_replication_batch.py --seed 100 --force

If the script is interrupted (Ctrl+C, crash, machine sleep, etc.) it can
simply be re-run with the same arguments: experiments whose results folder
already contains sensitivity-analysis .xlsx output are skipped automatically
(unless --force is given), so it safely resumes where it left off.
"""
import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent

# Repo-bundled copy by default (works on any OS after cloning); override with
# --settings-xlsx / --base-output if you keep results elsewhere (e.g. the
# original Windows machine's Desktop results folder).
DEFAULT_SETTINGS_XLSX = str(REPO_ROOT / "BIMP_replication_settings_500_1000.xlsx")
DEFAULT_BASE_OUTPUT = r"C:\Users\Samira\Desktop\Sensitivity analysis results"
DEFAULT_LOG_XLSX = str(Path(DEFAULT_BASE_OUTPUT) / "BIMP_replication_batch_log.xlsx")
DEFAULT_BACKEND_URL = "http://localhost:5000"

REQUEST_TIMEOUT_SECONDS = 24 * 60 * 60  # 24h safety net per experiment (large N/cases can be slow)

INPUT_FILES = {
    "BPIC_2012": {
        "bpmn": REPO_ROOT / "example_sensitivity_analysis_inputs" / "BPIC_2012" / "BPIC_2012_train.bpmn",
        "json": REPO_ROOT / "example_sensitivity_analysis_inputs" / "BPIC_2012" / "BPIC_2012_train.json",
    },
    "BPIC_2017": {
        "bpmn": REPO_ROOT / "example_sensitivity_analysis_inputs" / "BPIC_2017" / "BPIC_2017_train.bpmn",
        "json": REPO_ROOT / "example_sensitivity_analysis_inputs" / "BPIC_2017" / "BPIC_2017_train.json",
    },
}

# excel "dimensions" column tokens -> /simulate form flag names
ALL_DIMENSION_TOKENS = [
    "gateway",
    "arrival_distribution",
    "arrival_calendar",
    "tasks_resources",
    "resource_calendars",
    "resource_numbers",
]


def _int_or_none(value):
    if pd.isna(value):
        return None
    return int(value)


def load_experiments(settings_xlsx: str) -> list[dict]:
    """Parse the settings Excel into a list of ready-to-send experiment dicts."""
    df = pd.read_excel(settings_xlsx)

    before = len(df)
    df = df.drop_duplicates(subset="bimp_folder_name", keep="first").reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"[INFO] Dropped {dropped} duplicate row(s) sharing a bimp_folder_name (already-covered experiments).")

    experiments = []
    for i, row in df.iterrows():
        dataset = str(row["dataset"]).strip()
        if dataset not in INPUT_FILES:
            raise ValueError(f"Row {i}: unknown dataset '{dataset}' (expected one of {list(INPUT_FILES)})")

        method = str(row["method"]).strip().lower()
        is_sobol = method == "sobol"

        dims_active = {d.strip() for d in str(row["dimensions"]).split("+")}
        unknown = dims_active - set(ALL_DIMENSION_TOKENS)
        if unknown:
            raise ValueError(f"Row {i}: unknown dimension token(s) {unknown} in '{row['dimensions']}'")
        dim_flags = {f"is_{d}": (d in dims_active) for d in ALL_DIMENSION_TOKENS}

        cases_list = [int(c) for c in str(row["cases_list"]).split(";") if c.strip()]

        folder_name = str(row["bimp_folder_name"]).strip()
        if folder_name.upper().endswith("_BIMP"):
            folder_name = folder_name[: -len("_BIMP")]

        experiments.append({
            "exp_id": i + 1,
            "dataset": dataset,
            "bpmn_path": INPUT_FILES[dataset]["bpmn"],
            "json_path": INPUT_FILES[dataset]["json"],
            "is_sobol": is_sobol,
            "is_groups": bool(row["is_groups"]),
            **dim_flags,
            "n_samples": _int_or_none(row.get("n_samples")),
            "n_trajectories": _int_or_none(row.get("n_trajectories")),
            "num_levels": _int_or_none(row.get("num_levels")),
            "calc_second_order": bool(row["calc_second_order"]),
            "replication_runs": int(row["replication_runs"]),
            "cases_list": cases_list,
            "seed": int(row["seed"]),
            "results_folder_name": folder_name,
            "original_folder": str(row.get("original_folder", "")),
        })

    return experiments


def already_done(base_output: str, folder_name: str) -> bool:
    """Heuristic: an experiment is 'done' if its results folder has at least
    one sensitivity_analysis_* subfolder containing an .xlsx file."""
    exp_folder = Path(base_output) / f"{folder_name}_BIMP"
    if not exp_folder.exists():
        return False
    for sa_dir in exp_folder.glob("sensitivity_analysis_*"):
        if sa_dir.is_dir() and any(sa_dir.glob("*.xlsx")):
            return True
    return False


def run_one_experiment(exp: dict, backend_url: str) -> dict:
    """POST a single experiment to /simulate and return a result-log row."""
    data = {
        "simulator": "bimp",
        "is_sobol": str(exp["is_sobol"]).lower(),
        "is_groups": str(exp["is_groups"]).lower(),
        "is_gateway": str(exp["is_gateway"]).lower(),
        "is_arrival_distribution": str(exp["is_arrival_distribution"]).lower(),
        "is_arrival_calendar": str(exp["is_arrival_calendar"]).lower(),
        "is_tasks_resources": str(exp["is_tasks_resources"]).lower(),
        "is_resource_calendars": str(exp["is_resource_calendars"]).lower(),
        "is_resource_numbers": str(exp["is_resource_numbers"]).lower(),
        "calc_second_order": str(exp["calc_second_order"]).lower(),
        "replication_runs": str(exp["replication_runs"]),
        "cases_list": json.dumps(exp["cases_list"]),
        "seed": str(exp["seed"]),
        "simulation_results_folder": exp["results_folder_name"],
    }
    if exp["is_sobol"]:
        data["n_samples"] = str(exp["n_samples"])
    else:
        data["n_trajectories"] = str(exp["n_trajectories"])
        data["num_levels"] = str(exp["num_levels"])

    log_row = {
        "exp_id": exp["exp_id"],
        "bimp_folder_name": f"{exp['results_folder_name']}_BIMP",
        "dataset": exp["dataset"],
        "method": "sobol" if exp["is_sobol"] else "morris",
        "seed": exp["seed"],
        "cases_list": ";".join(str(c) for c in exp["cases_list"]),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    start = time.time()
    try:
        with open(exp["bpmn_path"], "rb") as bpmn_f, open(exp["json_path"], "rb") as json_f:
            files = {
                "bpmn": (Path(exp["bpmn_path"]).name, bpmn_f, "application/xml"),
                "json": (Path(exp["json_path"]).name, json_f, "application/json"),
            }
            resp = requests.post(
                f"{backend_url}/simulate",
                data=data,
                files=files,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        elapsed = time.time() - start
        log_row["elapsed_minutes"] = round(elapsed / 60, 1)
        log_row["http_status"] = resp.status_code

        try:
            body = resp.json()
        except ValueError:
            body = {"raw_text": resp.text[:2000]}

        if resp.status_code == 200:
            log_row["status"] = "SUCCESS"
            sa_errors = body.get("sensitivity_analysis_errors")
            log_row["status"] = "SUCCESS_WITH_SA_WARNINGS" if sa_errors else "SUCCESS"
            log_row["detail"] = json.dumps(body)[:4000]
        else:
            log_row["status"] = "FAILED"
            log_row["detail"] = json.dumps(body)[:4000]
    except requests.exceptions.ConnectionError as e:
        elapsed = time.time() - start
        log_row["elapsed_minutes"] = round(elapsed / 60, 1)
        log_row["http_status"] = None
        log_row["status"] = "CONNECTION_ERROR"
        log_row["detail"] = str(e)[:2000]
    except requests.exceptions.Timeout as e:
        elapsed = time.time() - start
        log_row["elapsed_minutes"] = round(elapsed / 60, 1)
        log_row["http_status"] = None
        log_row["status"] = "TIMEOUT"
        log_row["detail"] = str(e)[:2000]
    except Exception as e:
        elapsed = time.time() - start
        log_row["elapsed_minutes"] = round(elapsed / 60, 1)
        log_row["http_status"] = None
        log_row["status"] = "ERROR"
        log_row["detail"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}"

    log_row["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return log_row


def save_log(rows: list[dict], log_xlsx: str):
    Path(log_xlsx).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(log_xlsx, index=False)


def main():
    parser = argparse.ArgumentParser(description="Batch-run BIMP replication experiments from an Excel settings file.")
    parser.add_argument("--settings-xlsx", default=DEFAULT_SETTINGS_XLSX)
    parser.add_argument("--base-output", default=DEFAULT_BASE_OUTPUT)
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--log-xlsx", default=DEFAULT_LOG_XLSX)
    parser.add_argument("--seed", type=int, default=None, choices=[100, 200, 300],
                         help="Only run experiments with this seed (batch 1=100, batch 2=200, batch 3=300). Omit to run all.")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N (filtered) experiments.")
    parser.add_argument("--start", type=int, default=1, help="1-based position to start from within the filtered list.")
    parser.add_argument("--force", action="store_true", help="Re-run experiments even if their output folder already looks complete.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run, without calling the backend.")
    args = parser.parse_args()

    experiments = load_experiments(args.settings_xlsx)

    if args.seed is not None:
        experiments = [e for e in experiments if e["seed"] == args.seed]
    experiments = experiments[args.start - 1:]
    if args.limit is not None:
        experiments = experiments[: args.limit]

    total = len(experiments)
    print(f"[INFO] {total} experiment(s) selected (seed={args.seed or 'ALL'}, start={args.start}, limit={args.limit}).")

    if total == 0:
        print("[INFO] Nothing to do.")
        return

    if not args.dry_run:
        try:
            health = requests.get(f"{args.backend_url}/health", timeout=10)
            health.raise_for_status()
        except Exception as e:
            print(f"[FATAL] Backend not reachable at {args.backend_url} ({e}).")
            print("        Start it first: cd backend && python app.py")
            sys.exit(1)

    rows = []
    skipped = 0
    ok = 0
    failed = 0
    batch_start = time.time()

    try:
        for pos, exp in enumerate(experiments, start=1):
            label = f"[{pos}/{total}] exp_id={exp['exp_id']} {exp['results_folder_name']}_BIMP (dataset={exp['dataset']}, seed={exp['seed']}, cases={exp['cases_list']})"

            if not args.force and already_done(args.base_output, exp["results_folder_name"]):
                print(f"{label} -> SKIP (already has sensitivity-analysis .xlsx output)")
                skipped += 1
                continue

            if args.dry_run:
                print(f"{label} -> WOULD RUN")
                continue

            print(f"{label} -> RUNNING...")
            row = run_one_experiment(exp, args.backend_url)
            rows.append(row)
            save_log(rows, args.log_xlsx)

            if row["status"].startswith("SUCCESS"):
                ok += 1
                print(f"  -> {row['status']} ({row['elapsed_minutes']} min)")
            else:
                failed += 1
                print(f"  -> {row['status']} ({row['elapsed_minutes']} min): {row['detail'][:300]}")

            if row["status"] == "CONNECTION_ERROR":
                print("[FATAL] Backend connection lost. Stopping batch (re-run this same command to resume).")
                break
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user. Progress saved to log; re-run the same command to resume.")
    finally:
        if rows:
            save_log(rows, args.log_xlsx)

    elapsed_h = (time.time() - batch_start) / 3600
    print(f"\n[SUMMARY] ok={ok} failed={failed} skipped={skipped} total_selected={total} elapsed={elapsed_h:.1f}h")
    if rows:
        print(f"[SUMMARY] Run log written to: {args.log_xlsx}")


if __name__ == "__main__":
    main()
