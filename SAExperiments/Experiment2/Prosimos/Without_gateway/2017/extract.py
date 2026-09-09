import json
import csv
from pathlib import Path

# Base directory containing the Sobol output folders
BASE_DIR = Path(".")

# Output CSV
OUTPUT_CSV = Path("sobol_final_summary_wait_S1_2017.csv")

rows = []

for folder in BASE_DIR.iterdir():
    if not folder.is_dir():
        continue

    # Expected folder name:
    # final_wo_gateways_2012_sobol_100_512_no2nd
    if not folder.name.startswith("final_wo_gateways_") or "_sobol_" not in folder.name:
        continue

    parts = folder.name.split("_")
    # ["final", "wo", "gateways", "2012", "sobol", "100", "512", "no2nd"]

    try:
        dataset = int(parts[3])
        seed = int(parts[5])
        n_samples = int(parts[6])
    except (IndexError, ValueError):
        print(f"Skipping malformed folder name: {folder.name}")
        continue

    cycle_dir = folder / "sensitivity_analysis_outputs" / "wait"
    if not cycle_dir.exists():
        print(f"Missing sensitivity_analysis_outputs/wait in {folder.name}")
        continue

    json_path = cycle_dir / "sobol_first_and_total_order.json"
    if not json_path.exists():
        print(f"Missing sobol_first_and_total_order.json in {cycle_dir}")
        continue

    # Load JSON
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Stable ordering
    data_sorted = sorted(data, key=lambda x: x.get("group", ""))

    for entry in data_sorted:
        rows.append([
            dataset,
            seed,
            n_samples,
            entry.get("group"),
            entry.get("S1"),
            entry.get("S1_conf"),
        ])

# Write CSV
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["dataset", "seed", "n_samples", "group", "S1", "S1_conf"])
    writer.writerows(rows)

print(f"CSV written to: {OUTPUT_CSV.resolve()}")
