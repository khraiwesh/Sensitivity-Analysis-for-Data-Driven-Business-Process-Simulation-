"""Consolidate Experiment3\\BIMP raw Sobol results (read-only w.r.t. sources).

Folder layout actually found on disk (differs from the Prosimos layout):
  BIMP/{2012,2017}/<seed folder>/sensitivity_analysis_{cycle_time,processing_time,waiting_time}_avg/sobol_first_and_total_order.xlsx

Each seed folder's user_config.json gives the authoritative `seed` and
`n_samples` for that run. Two seed folders (2012 seed100, 2017 seed100) have
no Sobol output at all (only user_config.json under each KPI subfolder) --
these are skipped and reported, matching known failed BIMP runs.

Never touches source files; only writes new summary .xlsx files.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment3\BIMP")
KPI_FOLDER_NAMES = {
    "Cycle Time": "sensitivity_analysis_cycle_time_avg",
    "Processing Time": "sensitivity_analysis_processing_time_avg",
    "Waiting Time": "sensitivity_analysis_waiting_time_avg",
}
RESULT_FILE = "sobol_first_and_total_order.xlsx"
# summary files created by this script itself -> never treat as a source on re-run
GENERATED_FILE_PREFIXES = ("BIMP_All_Results", "_All_Seeds", "_All_KPIs")

report = {"included": [], "skipped": [], "row_counts": {}, "seed_counts": {}}


def read_kpi_result(seed_dir: Path, kpi: str, seed: int, n_samples: int):
    kpi_dir = seed_dir / KPI_FOLDER_NAMES[kpi]
    result_file = kpi_dir / RESULT_FILE
    if not result_file.exists():
        report["skipped"].append(f"{seed_dir.name} / {kpi}: no {RESULT_FILE} found (failed/missing run)")
        return None
    df = pd.read_excel(result_file)
    df.insert(0, "seed", seed)
    df.insert(1, "n_samples", n_samples)
    df.insert(2, "KPI", kpi)
    report["included"].append(str(result_file.relative_to(ROOT)))
    return df


def main():
    import json

    dataset_kpi_frames = {}  # (dataset, kpi) -> [df, ...]
    dataset_all_frames = {}  # dataset -> [df, ...] (all KPIs combined)

    for ds_dir in sorted(ROOT.iterdir()):
        if not ds_dir.is_dir():
            continue
        dataset = ds_dir.name
        seed_dirs = sorted(d for d in ds_dir.iterdir() if d.is_dir())
        report["seed_counts"][dataset] = len(seed_dirs)

        for seed_dir in seed_dirs:
            cfg = json.loads((seed_dir / "user_config.json").read_text())
            seed, n_samples = cfg["seed"], cfg["n_samples"]

            for kpi in KPI_FOLDER_NAMES:
                df = read_kpi_result(seed_dir, kpi, seed, n_samples)
                if df is None:
                    continue
                df.insert(0, "dataset", dataset)
                dataset_kpi_frames.setdefault((dataset, kpi), []).append(df)
                dataset_all_frames.setdefault(dataset, []).append(df)
                report["row_counts"][f"{dataset} / {kpi} / seed{seed}"] = len(df)

    # Level 1: per dataset x KPI, all seeds
    for (dataset, kpi), frames in dataset_kpi_frames.items():
        combined = pd.concat(frames, ignore_index=True, sort=False)
        expected = sum(len(f) for f in frames)
        assert len(combined) == expected, f"row count mismatch for {dataset}/{kpi}"
        out_name = f"{dataset}_{kpi.replace(' ', '_')}_All_Seeds.xlsx"
        out_path = ROOT / dataset / out_name
        combined.to_excel(out_path, index=False, sheet_name="results")
        print(f"Wrote {out_path} ({len(combined)} rows)")

    # Level 2: per dataset, all KPIs + all seeds
    for dataset, frames in dataset_all_frames.items():
        combined = pd.concat(frames, ignore_index=True, sort=False)
        expected = sum(len(f) for f in frames)
        assert len(combined) == expected, f"row count mismatch for {dataset}"
        out_path = ROOT / dataset / f"BPIC{dataset}_All_KPIs.xlsx"
        combined.to_excel(out_path, index=False, sheet_name="results")
        print(f"Wrote {out_path} ({len(combined)} rows)")

    # Level 3: everything
    all_frames = [f for frames in dataset_all_frames.values() for f in frames]
    overall = pd.concat(all_frames, ignore_index=True, sort=False)
    expected = sum(len(f) for f in all_frames)
    assert len(overall) == expected, "row count mismatch for overall BIMP summary"
    overall_path = ROOT / "BIMP_All_Results.xlsx"
    overall.to_excel(overall_path, index=False, sheet_name="results")
    print(f"Wrote {overall_path} ({len(overall)} rows)")

    print("\n--- SEED COUNTS PER DATASET ---")
    for ds, n in report["seed_counts"].items():
        print(f"  {ds}: {n} seed folders found")

    print("\n--- SKIPPED ---")
    for s in report["skipped"]:
        print(" ", s)

    print("\n--- ROW COUNTS PER Dataset/KPI/Seed ---")
    for k, v in report["row_counts"].items():
        print(f"  {k}: {v} rows")

    print("\n--- INCLUDED SOURCE FILES ---")
    for f in report["included"]:
        print(" ", f)


if __name__ == "__main__":
    main()
