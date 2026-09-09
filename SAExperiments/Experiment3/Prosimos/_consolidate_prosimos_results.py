"""Consolidate Experiment3\\Prosimos raw Sobol results into summary Excel files.

Read-only w.r.t. source data: never modifies/renames/deletes existing files,
only creates new .xlsx files. For datasets where the S1 and ST indices are
split across two CSVs (2012/2017 in CycleTime and WaitingTime), the two are
outer-merged on (seed, n_samples, group) so each row carries both indices,
matching the schema already used by the single-file datasets (2013, Production).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment3\Prosimos")
KPI_DIRS = {
    "Cycle Time": ROOT / "CycleTime",
    "Processing Time": ROOT / "ProcessingTime",
    "Waiting Time": ROOT / "WaitingTime",
}
KEY_COLS = ["seed", "n_samples", "group"]
DATASET_LABEL = {"2012": "2012", "2013": "2013", "2017": "2017",
                  "Production": "Production", "Datamining": "Datamining"}

report = {"included": [], "skipped": [], "row_counts": {}}


def load_dataset_folder(ds_dir: Path):
    """Load and merge all CSVs in a dataset folder into one dataframe."""
    csvs = sorted(ds_dir.glob("*.csv"))
    if not csvs:
        report["skipped"].append(f"{ds_dir.relative_to(ROOT)}: no CSV files found")
        return None

    frames = [pd.read_csv(f) for f in csvs]
    for f in csvs:
        report["included"].append(str(f.relative_to(ROOT)))

    df = frames[0]
    for extra in frames[1:]:
        common = [c for c in KEY_COLS if c in df.columns and c in extra.columns]
        df = df.merge(extra, on=common, how="outer", suffixes=("", "_dup"))
        # both files carry their own "dataset" col with possibly different dtype -> drop the duplicate
        dup_cols = [c for c in df.columns if c.endswith("_dup")]
        df = df.drop(columns=dup_cols)

    df["dataset"] = DATASET_LABEL[ds_dir.name]
    df["source_files"] = ";".join(f.name for f in csvs)
    return df


def build_kpi_summary(kpi_name, kpi_dir):
    parts = []
    for ds_dir in sorted(kpi_dir.iterdir()):
        if not ds_dir.is_dir():
            continue
        df = load_dataset_folder(ds_dir)
        if df is not None:
            parts.append(df)
            report["row_counts"].setdefault(kpi_name, {})[ds_dir.name] = len(df)
    combined = pd.concat(parts, ignore_index=True, sort=False)

    # put dataset first, source_files last, keep original column order otherwise
    cols = [c for c in combined.columns if c not in ("dataset", "source_files")]
    combined = combined[["dataset"] + cols + ["source_files"]]
    return combined


def main():
    kpi_frames = {}
    for kpi_name, kpi_dir in KPI_DIRS.items():
        combined = build_kpi_summary(kpi_name, kpi_dir)
        kpi_frames[kpi_name] = combined

        out_name = kpi_name.replace(" ", "_") + "_All_Datasets.xlsx"
        out_path = kpi_dir / out_name
        combined.to_excel(out_path, index=False, sheet_name=kpi_name.replace(" ", "_")[:31])
        print(f"Wrote {out_path} ({len(combined)} rows)")

    overall_parts = []
    for kpi_name, df in kpi_frames.items():
        d = df.copy()
        d.insert(0, "KPI", kpi_name)
        overall_parts.append(d)
    overall = pd.concat(overall_parts, ignore_index=True, sort=False)
    overall_path = ROOT / "Prosimos_All_Results.xlsx"
    overall.to_excel(overall_path, index=False, sheet_name="All_Results")
    print(f"Wrote {overall_path} ({len(overall)} rows)")

    print("\n--- INCLUDED SOURCE FILES ---")
    for f in report["included"]:
        print(" ", f)
    print("\n--- SKIPPED ---")
    for s in report["skipped"]:
        print(" ", s)
    print("\n--- ROW COUNTS PER KPI/DATASET ---")
    for kpi_name, counts in report["row_counts"].items():
        print(f" {kpi_name}:")
        for ds, n in counts.items():
            print(f"   {ds}: {n} rows")


if __name__ == "__main__":
    main()
