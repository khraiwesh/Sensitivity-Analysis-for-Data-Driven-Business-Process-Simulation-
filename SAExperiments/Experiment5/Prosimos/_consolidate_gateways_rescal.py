"""Consolidate Experiment5\\Prosimos "within-group" Morris SA results (individual
gateway nodes / individual resource calendars, NOT the 5-group analysis used
elsewhere) into 3 Excel files: Gateways-only, Resource-Calendars-only, and
everything combined.

Layout found on disk:
  2012/gateways/2012/morris_final_summary_{cycle,waiting}.csv            (combined, per-gateway-node mu_star)
  2012/resources calenders/2012/morris_final_summary_{cycle,waiting}.csv (combined, per-resource-calendar mu_star)
  2017/gateways/2017/morris_final_summary_{cycle,waiting}.csv
  2017/Resources calenders/2017/morris_final_summary_{cycle,waiting}.csv
  Production/gateways/morris_final_summary_{cycle,waiting}.csv
  Production/resource calendars/morris_final_summary_{cycle,waiting}.csv
  Datamining/gateways/morris_final_summary_{cycle,waiting}.csv                (added 2026-09-03)
  Datamining/resource calendars/morris_final_summary_{cycle,waiting}.csv      (added 2026-09-03)
  2013/gateways/bpic2013_within_gateways_morris_t{16,32,64}_seed{100,200,300}/
      sensitivity_analysis_outputs/sa_{cycle_time,waiting_time}/morris_first_order.json
      (NO combined CSV here -- built directly from the 18 per-seed/per-trajectory JSON files)

NOTE: 2013 has NO "resource calendars" subfolder at all -- this dataset only
has within-group Morris data for Gateways, not Resource Calendars. This is
reported explicitly, not silently omitted.

Columns: dataset, parameter_type (Gateway/Resource Calendar), KPI, seed,
n_samples (Morris trajectory count), name (individual gateway node id or
resource calendar id), mu_star, mu_star_conf. Never modifies source files.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment5\Prosimos")
KPIS = ["cycle", "waiting"]
KPI_LABEL = {"cycle": "Cycle Time", "waiting": "Waiting Time"}

CSV_SOURCES = [
    # (dataset, parameter_type, dir)
    ("2012", "Gateway", ROOT / "2012" / "gateways" / "2012"),
    ("2012", "Resource Calendar", ROOT / "2012" / "resources calenders" / "2012"),
    ("2017", "Gateway", ROOT / "2017" / "gateways" / "2017"),
    ("2017", "Resource Calendar", ROOT / "2017" / "Resources calenders" / "2017"),
    ("Production", "Gateway", ROOT / "Production" / "gateways"),
    ("Production", "Resource Calendar", ROOT / "Production" / "resource calendars"),
    ("Datamining", "Gateway", ROOT / "Datamining" / "gateways"),
    ("Datamining", "Resource Calendar", ROOT / "Datamining" / "resource calendars"),
]

BPIC2013_GATEWAYS_DIR = ROOT / "2013" / "gateways"
KPI_SUBFOLDER = {"cycle": "sa_cycle_time", "waiting": "sa_waiting_time"}

report = {"included": [], "skipped": [], "row_counts": {}}


def load_csv_sources():
    parts = []
    for dataset, ptype, d in CSV_SOURCES:
        for kpi in KPIS:
            f = d / f"morris_final_summary_{kpi}.csv"
            if not f.exists():
                report["skipped"].append(f"{dataset} / {ptype} / {KPI_LABEL[kpi]}: {f} not found")
                continue
            df = pd.read_csv(f)
            df["dataset"] = dataset
            df["parameter_type"] = ptype
            df["KPI"] = KPI_LABEL[kpi]
            report["included"].append(str(f.relative_to(ROOT)))
            report["row_counts"][f"{dataset} / {ptype} / {KPI_LABEL[kpi]}"] = len(df)
            parts.append(df)
    return parts


def load_bpic2013_gateways():
    parts = []
    for seed_dir in sorted(BPIC2013_GATEWAYS_DIR.iterdir()):
        if not seed_dir.is_dir():
            continue
        cfg_path = seed_dir / "user_config.json"
        if not cfg_path.exists():
            report["skipped"].append(f"2013 / Gateway / {seed_dir.name}: no user_config.json")
            continue
        cfg = json.loads(cfg_path.read_text())
        seed = cfg["seed"]
        n_samples = cfg.get("n_trajectories")
        for kpi in KPIS:
            f = seed_dir / "sensitivity_analysis_outputs" / KPI_SUBFOLDER[kpi] / "morris_first_order.json"
            if not f.exists():
                report["skipped"].append(f"2013 / Gateway / {seed_dir.name} / {KPI_LABEL[kpi]}: morris_first_order.json not found")
                continue
            records = json.loads(f.read_text())
            df = pd.DataFrame(records)
            df = df[["name", "mu_star", "mu_star_conf"]].copy()
            df["dataset"] = "2013"
            df["parameter_type"] = "Gateway"
            df["KPI"] = KPI_LABEL[kpi]
            df["seed"] = seed
            df["n_samples"] = n_samples
            report["included"].append(str(f.relative_to(ROOT)))
            parts.append(df)
    for kpi in KPIS:
        n = sum(len(p) for p in parts if p["KPI"].iloc[0] == KPI_LABEL[kpi])
        report["row_counts"][f"2013 / Gateway / {KPI_LABEL[kpi]}"] = n
    return parts


def main():
    parts = load_csv_sources() + load_bpic2013_gateways()
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


if __name__ == "__main__":
    main()
