"""Consolidate Experiment5\\BIMP "within-group" Morris SA results (individual
gateway nodes / individual resource calendars) into 3 Excel files: Gateways-only,
Resource-Calendars-only, and everything combined. Mirrors the Experiment5\\Prosimos
consolidation, adapted to BIMP's per-seed folder layout (see
_consolidate_bimp_results.py in Experiment4\\BIMP for the established pattern:
`sensitivity_analysis_{kpi}_avg/morris_first_order.json`, cases 500+1000 rows,
keep cases==1000).

Parameter type is determined from `user_config.json`'s authoritative
`is_gateway`/`is_resource_calendars` flags, NOT the folder name -- folder names
in this dataset are not 100% reliable (see repo memory
bimp-sample-failure-bug.md for a prior mislabeled-folder gotcha). Folders with
`is_groups: true` (the full 5-group without-gateways analysis, e.g. the 3
`final_wo_gateways_2017_morris_300_{64,128,256}_BIMP` folders) are a DIFFERENT
analysis type (whole-group, not individual-parameter) and are explicitly
excluded from all 3 files here, reported as skipped rather than silently
dropped.

KNOWN DATA GAPS (real, not bugs -- reported explicitly):
  2012 Resource Calendars: only seeds 100 and 300 (seed200 never run)
  2017 Gateways:           seed300 missing n_trajectories=64 (only 16, 32)
  2017 Resource Calendars: only seed300 (seeds 100, 200 never run)

Never modifies source files.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment5\BIMP")
KPIS = ["cycle_time", "waiting_time"]
KPI_LABEL = {"cycle_time": "Cycle Time", "waiting_time": "Waiting Time"}
BIMP_CASES = 1000

report = {"included": [], "skipped": [], "row_counts": {}}


def classify(cfg):
    if cfg.get("is_groups"):
        return None  # full 5-group analysis, not within-group -- excluded
    if cfg.get("is_gateway"):
        return "Gateway"
    if cfg.get("is_resource_calendars"):
        return "Resource Calendar"
    return None


def load_seed_folder(ds, seed_dir):
    cfg_path = seed_dir / "user_config.json"
    if not cfg_path.exists():
        report["skipped"].append(f"{ds} / {seed_dir.name}: no user_config.json (folder incomplete/failed run)")
        return []
    cfg = json.loads(cfg_path.read_text())
    ptype = classify(cfg)
    if ptype is None:
        report["skipped"].append(f"{ds} / {seed_dir.name}: is_groups=true (full 5-group analysis, not within-group, excluded)")
        return []
    seed = cfg["seed"]
    n_samples = cfg.get("n_trajectories")

    parts = []
    for kpi in KPIS:
        f = seed_dir / f"sensitivity_analysis_{kpi}_avg" / "morris_first_order.json"
        if not f.exists():
            report["skipped"].append(f"{ds} / {seed_dir.name} / {ptype} / {KPI_LABEL[kpi]}: morris_first_order.json not found (failed run)")
            continue
        records = json.loads(f.read_text())
        df = pd.DataFrame(records)
        df = df[df["cases"] == BIMP_CASES].copy()
        if df.empty:
            report["skipped"].append(f"{ds} / {seed_dir.name} / {ptype} / {KPI_LABEL[kpi]}: no cases=={BIMP_CASES} rows")
            continue
        df = df[["name", "mu_star", "mu_star_conf"]].copy()
        df["dataset"] = ds
        df["parameter_type"] = ptype
        df["KPI"] = KPI_LABEL[kpi]
        df["seed"] = seed
        df["n_samples"] = n_samples
        report["included"].append(str(f.relative_to(ROOT)))
        report["row_counts"][f"{ds} / {ptype} / {KPI_LABEL[kpi]} / seed{seed}_n{n_samples}"] = len(df)
        parts.append(df)
    return parts


def main():
    parts = []
    for ds in ["2012", "2017"]:
        for seed_dir in sorted((ROOT / ds).iterdir()):
            if seed_dir.is_dir():
                parts.extend(load_seed_folder(ds, seed_dir))

    combined = pd.concat(parts, ignore_index=True, sort=False)
    cols = ["dataset", "parameter_type", "KPI", "seed", "n_samples", "name", "mu_star", "mu_star_conf"]
    combined = combined[cols]

    gateways = combined[combined["parameter_type"] == "Gateway"].reset_index(drop=True)
    rescal = combined[combined["parameter_type"] == "Resource Calendar"].reset_index(drop=True)

    gw_path = ROOT / "Gateways_All_Data.xlsx"
    gateways.to_excel(gw_path, index=False, sheet_name="Gateways")
    print(f"Wrote {gw_path} ({len(gateways)} rows)")

    rc_path = ROOT / "Resource_Calendars_All_Data.xlsx"
    rescal.to_excel(rc_path, index=False, sheet_name="Resource_Calendars")
    print(f"Wrote {rc_path} ({len(rescal)} rows)")

    all_path = ROOT / "All_Parameters_Combined.xlsx"
    combined.to_excel(all_path, index=False, sheet_name="All_Data")
    print(f"Wrote {all_path} ({len(combined)} rows)")

    print("\n--- INCLUDED SOURCE FILES ---")
    for f in report["included"]:
        print(" ", f)
    print("\n--- SKIPPED ---")
    for s in report["skipped"]:
        print(" ", s)
    print("\n--- ROW COUNTS ---")
    for k, v in report["row_counts"].items():
        print(f"  {k}: {v} rows")

    print("\n--- SEED/N COVERAGE ---")
    print(combined.groupby(["dataset", "parameter_type"])["seed"].unique())
    print(combined.groupby(["dataset", "parameter_type"])["n_samples"].unique())


if __name__ == "__main__":
    main()
