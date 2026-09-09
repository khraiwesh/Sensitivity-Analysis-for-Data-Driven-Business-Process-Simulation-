import json
import csv
from pathlib import Path

# Base directory containing the morris output folders
BASE_DIR = Path(".")

# Output CSV
OUTPUT_CSV = Path("morris_final_summary_waiting.csv")

rows = []

for folder in BASE_DIR.iterdir():
    if not folder.is_dir():
        continue

    # Expected folder name:
    # final_wo_gateways_2012_resource_calendars_morris_100_16
    if not folder.name.startswith("final_wo_gateways_") or "_resource_calendars_morris_" not in folder.name:
        continue

    parts = folder.name.split("_")
    # ["final", "wo", "gateways", "2012", "resource", "calendars", "morris", "100", "16"]

    try:
        dataset = int(parts[3])
        seed = int(parts[7])
        n_samples = int(parts[8])
    except (IndexError, ValueError):
        print(f"Skipping malformed folder name: {folder.name}")
        continue

    cycle_dir = folder / "sensitivity_analysis_outputs" / "waiting"
    if not cycle_dir.exists():
        print(f"Missing sensitivity_analysis_outputs/waiting in {folder.name}")
        continue

    json_path = cycle_dir / "morris_first_order.json"
    if not json_path.exists():
        print(f"Missing morris_first_order.json in {cycle_dir}")
        continue

    # Load JSON
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Take top 10 by mu_star (already sorted in JSON)
    top_10 = data[:10]

    for entry in top_10:
        rows.append([
            dataset,
            seed,
            n_samples,
            entry.get("name"),
            entry.get("mu_star"),
            entry.get("mu_star_conf"),
        ])

# Write CSV
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["dataset", "seed", "n_samples", "name", "mu_star", "mu_star_conf"])
    writer.writerows(rows)

print(f"CSV written to: {OUTPUT_CSV.resolve()}")
