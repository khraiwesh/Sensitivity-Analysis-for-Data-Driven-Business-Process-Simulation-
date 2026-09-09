"""Consolidate Experiment4\\BIMP Cycle Time + Waiting Time results (Sobol N=2048
AND Morris, without-gateways config), combined in one sheet per KPI with a
`method` column, mirroring Experiment4\\Prosimos's consolidation.

Layout found on disk: one folder per (method, seed[, n]) under 2012/ and 2017/,
named e.g. `final_wo_gateways_2012_sobol_100_2048_no2nd_BIMP` or
`final_wo_gateways_2012_morris_100_512_BIMP` (some Sobol seed300 folders drop
the "wo_gateways" infix, e.g. `final_2012_sobol_300_2048_no2nd_BIMP` -- content
layout is identical). Each seed folder contains
`sensitivity_analysis_{cycle_time,waiting_time}_avg/` with either
`sobol_first_and_total_order.json` (cases 500 AND 1000 rows; keep cases==1000,
matching the BIMP_CASES convention used throughout this project) or
`morris_first_order.json` (same cases split). `user_config.json` at the seed
folder root gives the authoritative seed/n_samples(Sobol)/n_trajectories(Morris)
and is_sobol flag.

KNOWN FAILED/MISSING RUNS (BIMP has a documented failure mode for extreme
sampled scenarios, see repo memory bimp-sample-failure-bug.md): seed100 is
MISSING RESULTS for Sobol in both 2012 and 2017 (folder exists, only
user_config.json, no result file), Morris seed100 is missing results for 2017,
and Morris seed300 for 2012 has no folder contents at all (not even
user_config.json) -- only "samples/". These are skipped and reported, not
treated as errors. This leaves only 2 seeds available for several
method/dataset combos (not 3) -- explicitly flagged in the report.
Also note: 2017 Morris seed200 ran at n_trajectories=512 while seed300 ran at
n_trajectories=256 (inconsistent trajectory count between available seeds).

Never modifies source files.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment4\BIMP")
KPIS = ["cycle_time", "waiting_time"]
KPI_LABEL = {"cycle_time": "Cycle Time", "waiting_time": "Waiting Time"}
BIMP_CASES = 1000

report = {"included": [], "skipped": [], "row_counts": {}}


def load_seed_folder(ds, seed_dir):
    cfg_path = seed_dir / "user_config.json"
    if not cfg_path.exists():
        report["skipped"].append(f"{ds} / {seed_dir.name}: no user_config.json (folder incomplete/failed run)")
        return None
    cfg = json.loads(cfg_path.read_text())
    if cfg.get("is_gateway"):
        # Some seed folders (e.g. seed300, missing the "wo_gateways" name infix)
        # are actually WITH-gateways runs despite living alongside without-
        # gateways folders -- verified via this authoritative config flag, not
        # the folder name. Must be excluded per explicit requirement.
        report["skipped"].append(f"{ds} / {seed_dir.name}: is_gateway=true (with-gateways run, excluded)")
        return None
    method = "Sobol" if cfg.get("is_sobol") else "Morris"
    seed = cfg["seed"]
    ref_n = cfg.get("n_samples") if method == "Sobol" else cfg.get("n_trajectories")

    parts = []
    for kpi in KPIS:
        kdir = seed_dir / f"sensitivity_analysis_{kpi}_avg"
        result_name = "sobol_first_and_total_order.json" if method == "Sobol" else "morris_first_order.json"
        f = kdir / result_name
        if not f.exists():
            report["skipped"].append(f"{ds} / {seed_dir.name} / {method} / {KPI_LABEL[kpi]}: {result_name} not found (failed run)")
            continue
        records = json.loads(f.read_text())
        df = pd.DataFrame(records)
        df = df[df["cases"] == BIMP_CASES].copy()
        if df.empty:
            report["skipped"].append(f"{ds} / {seed_dir.name} / {method} / {KPI_LABEL[kpi]}: no cases=={BIMP_CASES} rows")
            continue
        df = df.rename(columns={"name": "parameter_group", "group": "parameter_group"})
        df["dataset"] = ds
        df["method"] = method
        df["seed"] = seed
        df["n_samples"] = ref_n
        df["KPI"] = KPI_LABEL[kpi]
        report["included"].append(str(f.relative_to(ROOT)))
        parts.append(df)
    return parts


def main():
    all_parts = []
    for ds in ["2012", "2017"]:
        for seed_dir in sorted((ROOT / ds).iterdir()):
            if not seed_dir.is_dir():
                continue
            parts = load_seed_folder(ds, seed_dir)
            if parts:
                all_parts.extend(parts)

    combined = pd.concat(all_parts, ignore_index=True, sort=False)
    cols = ["dataset", "method", "seed", "n_samples", "KPI", "parameter_group",
            "S1", "S1_conf", "ST", "ST_conf", "mu", "mu_star", "mu_star_conf", "sigma"]
    cols = [c for c in cols if c in combined.columns] + [c for c in combined.columns if c not in cols]
    combined = combined[cols]

    for ds in combined["dataset"].unique():
        for method in combined["method"].unique():
            for kpi_label in combined["KPI"].unique():
                n = len(combined[(combined["dataset"] == ds) & (combined["method"] == method) & (combined["KPI"] == kpi_label)])
                if n:
                    report["row_counts"][f"{ds} / {kpi_label} / {method}"] = n

    for kpi in KPIS:
        kpi_label = KPI_LABEL[kpi]
        kpi_df = combined[combined["KPI"] == kpi_label].drop(columns=["KPI"])
        out_path = ROOT / f"{kpi_label.replace(' ', '_')}_All_Datasets.xlsx"
        kpi_df.to_excel(out_path, index=False, sheet_name=kpi_label.replace(" ", "_")[:31])
        print(f"Wrote {out_path} ({len(kpi_df)} rows)")

    overall_path = ROOT / "BIMP_All_Results.xlsx"
    combined.to_excel(overall_path, index=False, sheet_name="All_Results")
    print(f"Wrote {overall_path} ({len(combined)} rows)")

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
