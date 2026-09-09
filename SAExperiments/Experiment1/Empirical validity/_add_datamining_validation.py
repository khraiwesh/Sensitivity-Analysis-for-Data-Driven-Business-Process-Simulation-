"""One-off script: add the Datamining dataset into Validation_combined.xlsx,
mirroring the schema of the existing BPIC2012/2013/2017/Production sheets.

Source: datamining_v3/individual_group_analysis_final.csv (already has the
exact 16-column schema used by the other per-dataset sheets).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
SRC = ROOT / "datamining_v3" / "individual_group_analysis_final.csv"
XLSX = ROOT / "Validation_combined.xlsx"

DATASET_LABEL = "Datamining"


def main():
    dm = pd.read_csv(SRC)
    dm.insert(0, "Dataset", DATASET_LABEL)

    xl = pd.ExcelFile(XLSX)
    all_datasets = xl.parse("All_Datasets")
    if DATASET_LABEL in set(all_datasets["Dataset"]):
        print(f"'{DATASET_LABEL}' already present in All_Datasets, aborting.")
        return
    all_datasets_new = pd.concat([all_datasets, dm], ignore_index=True)

    with pd.ExcelWriter(XLSX, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        dm.to_excel(writer, sheet_name=DATASET_LABEL, index=False)
        all_datasets_new.to_excel(writer, sheet_name="All_Datasets", index=False)

    print(f"Added sheet '{DATASET_LABEL}' ({len(dm)} rows).")
    print(f"All_Datasets: {len(all_datasets)} -> {len(all_datasets_new)} rows.")


if __name__ == "__main__":
    main()
