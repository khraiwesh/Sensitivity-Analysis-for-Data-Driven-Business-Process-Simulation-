"""Pairwise agreement between KPI/CTD rankings and Sobol/Morris SA rankings,
for each of the 4 validation datasets.

Reads individual_group_analysis_final_*.csv from the Validation folder (each
has columns: group, kpi_rank, sa_sobol_rank, sa_morris_rank, cc_CTD, ...).
File names are used as-is (not swapped), per user confirmation.

For each dataset, computes pairwise agreement for:
  - kpi_rank  vs sa_sobol_rank
  - kpi_rank  vs sa_morris_rank
  - ctd_rank  vs sa_sobol_rank   (ctd_rank = cc_CTD ranked descending)
  - ctd_rank  vs sa_morris_rank
"""
import itertools
from pathlib import Path

import pandas as pd

VALIDATION_DIR = Path(r"C:\Users\Samira\OneDrive - GJU\Desktop\PhD Progress -Submissions\Sensitivity Analysis\Vaildation")
OUT_DIR = Path(__file__).parent

FILES = {
    "2012": "individual_group_analysis_final _2012.csv",
    "2013": "individual_group_analysis_final _2013.csv",
    "2017": "individual_group_analysis_final_2017.csv",
    "Production": "individual_group_analysis_final_Production.csv",
}

PARAMS = ["AC", "AD", "RC", "RN", "TR"]


def pairwise_agreement(r1: pd.Series, r2: pd.Series) -> float:
    n_compared = 0
    n_concordant = 0
    for p, q in itertools.combinations(PARAMS, 2):
        d1, d2 = r1[p] - r1[q], r2[p] - r2[q]
        if d1 == 0 or d2 == 0:
            continue
        n_compared += 1
        if (d1 > 0) == (d2 > 0):
            n_concordant += 1
    return n_concordant / n_compared if n_compared else float("nan")


def main():
    rows = []
    for dataset, fname in FILES.items():
        df = pd.read_csv(VALIDATION_DIR / fname)
        df["group"] = df["group"].str.upper().str.strip()
        df = df.set_index("group").reindex(PARAMS)

        kpi_rank = df["kpi_rank"]
        sobol_rank = df["sa_sobol_rank"]
        morris_rank = df["sa_morris_rank"]
        ctd_rank = df["cc_CTD"].rank(ascending=False, method="average")

        rows.append(dict(dataset=dataset, comparison="KPI vs Sobol",
                          agreement=pairwise_agreement(kpi_rank, sobol_rank)))
        rows.append(dict(dataset=dataset, comparison="KPI vs Morris",
                          agreement=pairwise_agreement(kpi_rank, morris_rank)))
        rows.append(dict(dataset=dataset, comparison="CTD vs Sobol",
                          agreement=pairwise_agreement(ctd_rank, sobol_rank)))
        rows.append(dict(dataset=dataset, comparison="CTD vs Morris",
                          agreement=pairwise_agreement(ctd_rank, morris_rank)))

    out = pd.DataFrame(rows)
    pivot = out.pivot(index="dataset", columns="comparison", values="agreement")
    pivot = pivot[["KPI vs Sobol", "KPI vs Morris", "CTD vs Sobol", "CTD vs Morris"]]
    pivot = pivot.reindex(["2012", "2013", "2017", "Production"])

    out.to_csv(OUT_DIR / "kpi_ctd_vs_sa_agreement_4datasets.csv", index=False)
    print(pivot.to_string())


if __name__ == "__main__":
    main()
