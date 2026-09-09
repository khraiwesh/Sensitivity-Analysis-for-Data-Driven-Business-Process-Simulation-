"""Consolidate Experiment4\\Prosimos Cycle Time + Waiting Time results (Sobol
N=2048 AND Morris), combined in one sheet per KPI with a `method` column so the
two approaches can be compared directly, per user's request.

Sobol source (CORRECTED 2026-09-02): the earlier version of this script used
the Experiment4\\Prosimos Sobol N=64 exploratory runs, which the user flagged
as not the right data for this experiment. Sobol data is now sourced instead
from `DetailedRunsPerDatasets`, Step 1-2 / without-gateways configuration,
filtered to n_samples == 2048 (SOBOL_N below):
  2012\\Step 1-2\\Withoutgateway\\2012\\sobol_final_summary_{cycle,wait}.csv (ST) +
      sobol_final_summary_{cycle,wait}_S1_2012.csv (S1)          (split ST/S1)
  2017\\Step1-2\\Withoutgateway\\2017\\sobol_final_summary_{cycle,wait}.csv (ST) +
      sobol_final_summary_{cycle,wait}_S1_2017.csv (S1)          (split ST/S1)
  BPIC2013\\Final_2013\\Step 1-2\\without gateways\\2013\\sobol_final_summary_{cycle,waiting}.csv (combined S1+ST)
  Production.zip!Final_production/Step 1-2/without gateways/production/sobol_final_summary_{cycle,waiting}.csv
      (combined S1+ST, read directly from the zip, never extracted/modified)
  "Final_datamining (2).zip"!Final_datamining/Step 1-2/without gateways/datamining/sobol_final_summary_{cycle,waiting}.csv
      (combined S1+ST, read directly from the zip, never extracted/modified; added 2026-09-03)

Morris source is UNCHANGED: still Experiment4\\Prosimos\\<dataset>\\<dataset>_morris\\
morris_final_summary_{cycle,waiting}.csv (mu_star/mu_star_conf).

Morris uses column "name" + mu_star/mu_star_conf (no S1/ST); Sobol uses
"group" + S1/S1_conf/ST/ST_conf (no mu_star). Both are renamed to a common
"parameter_group" column and stacked with the union of columns, method-
specific metrics blank where not applicable. Never modifies source files.
"""
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment4\Prosimos")
DETAILED_ROOT = Path(r"C:\Users\Samira\SAExperiments\DetailedRunsPerDatasets")
KPIS = ["cycle", "waiting"]
KPI_LABEL = {"cycle": "Cycle Time", "waiting": "Waiting Time"}
SOBOL_N = 2048

# Sobol source: "combined" -> single CSV with S1+ST; "split" -> separate ST/S1 CSVs.
SOBOL_SOURCES = {
    "2012": {
        "kind": "split",
        "dir": DETAILED_ROOT / "2012" / "Step 1-2" / "Withoutgateway" / "2012",
        "st_name": lambda kpi: f"sobol_final_summary_{'wait' if kpi == 'waiting' else kpi}.csv",
        "s1_name": lambda kpi: f"sobol_final_summary_{'wait' if kpi == 'waiting' else kpi}_S1_2012.csv",
    },
    "2017": {
        "kind": "split",
        "dir": DETAILED_ROOT / "2017" / "Step1-2" / "Withoutgateway" / "2017",
        "st_name": lambda kpi: f"sobol_final_summary_{'wait' if kpi == 'waiting' else kpi}.csv",
        "s1_name": lambda kpi: f"sobol_final_summary_{'wait' if kpi == 'waiting' else kpi}_S1_2017.csv",
    },
    "2013": {
        "kind": "combined",
        "dir": DETAILED_ROOT / "BPIC2013" / "Final_2013" / "Step 1-2" / "without gateways" / "2013",
        "combined_name": lambda kpi: f"sobol_final_summary_{kpi}.csv",
    },
    "Production": {
        "kind": "zip_combined",
        "zip": DETAILED_ROOT / "Production.zip",
        "entry_name": lambda kpi: f"Final_production/Step 1-2/without gateways/production/sobol_final_summary_{kpi}.csv",
    },
    "Datamining": {
        "kind": "zip_combined",
        "zip": DETAILED_ROOT / "Final_datamining (2).zip",
        "entry_name": lambda kpi: f"Final_datamining/Step 1-2/without gateways/datamining/sobol_final_summary_{kpi}.csv",
    },
}

MORRIS_DIRS = {
    "2012": ROOT / "2012" / "2012_morris",
    "2013": ROOT / "2013" / "2013_morris",
    "2017": ROOT / "2017" / "2017_morris",
    "Production": ROOT / "Production" / "production_morris",
    "Datamining": ROOT / "Datamining" / "datamining_morris",
}

report = {"included": [], "skipped": [], "row_counts": {}}


def load_morris(ds, kpi):
    f = MORRIS_DIRS[ds] / f"morris_final_summary_{kpi}.csv"
    if not f.exists():
        report["skipped"].append(f"{ds} / Morris / {kpi}: {f.name} not found")
        return None
    df = pd.read_csv(f)
    df = df.rename(columns={"name": "parameter_group"})
    df["dataset"] = ds
    df["method"] = "Morris"
    report["included"].append(str(f.relative_to(ROOT.parent)))
    return df


def load_sobol(ds, kpi):
    src = SOBOL_SOURCES[ds]
    if src["kind"] == "split":
        st_path = src["dir"] / src["st_name"](kpi)
        s1_path = src["dir"] / src["s1_name"](kpi)
        st_df = pd.read_csv(st_path)
        s1_df = pd.read_csv(s1_path)
        report["included"].append(str(st_path.relative_to(DETAILED_ROOT.parent)))
        report["included"].append(str(s1_path.relative_to(DETAILED_ROOT.parent)))
        df = st_df.merge(s1_df, on=["dataset", "seed", "n_samples", "group"], how="outer")
    elif src["kind"] == "combined":
        f = src["dir"] / src["combined_name"](kpi)
        df = pd.read_csv(f)
        report["included"].append(str(f.relative_to(DETAILED_ROOT.parent)))
    else:  # zip_combined
        entry = src["entry_name"](kpi)
        with zipfile.ZipFile(src["zip"]) as z, z.open(entry) as fh:
            df = pd.read_csv(fh)
        report["included"].append(f"{src['zip'].name}!{entry}")

    df = df[df["n_samples"] == SOBOL_N].copy()
    if df.empty:
        report["skipped"].append(f"{ds} / Sobol / {kpi}: no rows at n_samples={SOBOL_N}")
        return None

    df = df.rename(columns={"group": "parameter_group"})
    df["dataset"] = ds
    df["method"] = "Sobol"
    return df


def main():
    kpi_frames = {}
    for kpi in KPIS:
        parts = []
        for ds in MORRIS_DIRS:
            morris_df = load_morris(ds, kpi)
            sobol_df = load_sobol(ds, kpi)
            for df in (morris_df, sobol_df):
                if df is not None:
                    parts.append(df)
                    method = df["method"].iloc[0]
                    report["row_counts"][f"{ds} / {KPI_LABEL[kpi]} / {method}"] = len(df)
        combined = pd.concat(parts, ignore_index=True, sort=False)
        expected = sum(len(p) for p in parts)
        assert len(combined) == expected, f"row mismatch for {kpi}"

        cols = ["dataset", "method", "seed", "n_samples", "parameter_group",
                "S1", "S1_conf", "ST", "ST_conf", "mu_star", "mu_star_conf"]
        cols = [c for c in cols if c in combined.columns] + [c for c in combined.columns if c not in cols]
        combined = combined[cols]
        kpi_frames[kpi] = combined

        out_path = ROOT / f"{KPI_LABEL[kpi].replace(' ', '_')}_All_Datasets.xlsx"
        combined.to_excel(out_path, index=False, sheet_name=KPI_LABEL[kpi].replace(" ", "_")[:31])
        print(f"Wrote {out_path} ({len(combined)} rows)")

    overall_parts = []
    for kpi, df in kpi_frames.items():
        d = df.copy()
        d.insert(0, "KPI", KPI_LABEL[kpi])
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
    print("\n--- ROW COUNTS ---")
    for k, v in report["row_counts"].items():
        print(f"  {k}: {v} rows")


if __name__ == "__main__":
    main()
