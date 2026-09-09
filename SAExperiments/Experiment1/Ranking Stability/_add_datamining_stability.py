"""One-off script: add the Datamining dataset into stability_out_pairwise/*.csv
and Ranking_Stability_combined.xlsx, following the exact same pipeline
(pairwise_agreement.py) used for 2012/2013/2017/production.

Source files (already prepared, unchanged):
  Datamining/datamining_results/02_stability_analysis/datamining/sobol_final_summary_cycle.csv
  Datamining/datamining_results/02_stability_analysis/datamining/morris_final_summary_cycle.csv
  Datamining/datamining_results/02_stability_analysis/datamining/sa_indices.csv
    (already in the dataset,method,seed,sample_size,parameter,value format
    required by pairwise_agreement.py, produced by convert_to_sa_indices.py)
"""
from pathlib import Path

import pandas as pd

import pairwise_agreement as pa

ROOT = Path(__file__).parent
DM_DIR = ROOT / "Datamining" / "datamining_results" / "02_stability_analysis" / "datamining"
OUT = ROOT / "stability_out_pairwise"
XLSX = ROOT / "Ranking_Stability_combined.xlsx"

DATASET_LABEL = "datamining"


def build_new_pairwise_rows():
    df = pa.load_data(str(DM_DIR / "sa_indices.csv"))
    df = df[df["dataset"] == DATASET_LABEL]

    seed_rows, conv_rows, ref_rows, agree_rows = [], [], [], []

    for (ds, method), g in df.groupby(["dataset", "method"]):
        params = sorted(g["parameter"].unique())
        sizes = sorted(g["sample_size"].unique())
        seeds = sorted(g["seed"].unique())

        for n in sizes:
            rankings = {
                s: pa.ranking_from_values(g[(g.sample_size == n) & (g.seed == s)], params)
                for s in seeds
            }
            import itertools
            import numpy as np
            pair_fracs = []
            for s1, s2 in itertools.combinations(seeds, 2):
                frac, n_c, n_cmp, n_tot = pa.pairwise_agreement(rankings[s1], rankings[s2], params)
                pair_fracs.append(frac)
                seed_rows.append(dict(dataset=ds, method=method, sample_size=n,
                                      seed_a=s1, seed_b=s2, n_params=len(params),
                                      n_concordant=n_c, n_pairs_compared=n_cmp,
                                      n_pairs_total=n_tot, agreement=frac))
            seed_rows.append(dict(dataset=ds, method=method, sample_size=n,
                                  seed_a="MEAN", seed_b="", n_params=len(params),
                                  n_concordant=np.nan, n_pairs_compared=np.nan,
                                  n_pairs_total=np.nan, agreement=float(np.nanmean(pair_fracs))))

        for s in seeds:
            for n1, n2 in zip(sizes, sizes[1:]):
                r1 = pa.ranking_from_values(g[(g.sample_size == n1) & (g.seed == s)], params)
                r2 = pa.ranking_from_values(g[(g.sample_size == n2) & (g.seed == s)], params)
                frac, n_c, n_cmp, n_tot = pa.pairwise_agreement(r1, r2, params)
                conv_rows.append(dict(dataset=ds, method=method, seed=s,
                                      size_from=n1, size_to=n2, n_params=len(params),
                                      n_concordant=n_c, n_pairs_compared=n_cmp,
                                      n_pairs_total=n_tot, agreement=frac))

        nmax = sizes[-1]
        avg = (g[g.sample_size == nmax]
               .groupby("parameter")["value"].mean().reindex(params))
        rank = avg.rank(ascending=False).astype(int)
        for p_ in params:
            ref_rows.append(dict(dataset=ds, method=method, sample_size=nmax,
                                 parameter=p_, mean_value=avg[p_],
                                 reference_rank=rank[p_]))

    ref = pd.DataFrame(ref_rows)
    for ds, g in ref.groupby("dataset"):
        piv = g.pivot(index="parameter", columns="method", values="reference_rank")
        if {"morris", "sobol"} <= set(piv.columns):
            common = piv.dropna(subset=["morris", "sobol"])
            excluded = set(piv.index) - set(common.index)
            params_common = sorted(common.index)
            frac, n_c, n_cmp, n_tot = pa.pairwise_agreement(
                common["morris"], common["sobol"], params_common)
            agree_rows.append(dict(
                dataset=ds, n_concordant=n_c, n_pairs_compared=n_cmp,
                n_pairs_total=n_tot, agreement_morris_vs_sobol=frac,
                n_params_compared=len(common),
                params_excluded_from_comparison=",".join(sorted(excluded)) or "none",
            ))

    return (pd.DataFrame(seed_rows), pd.DataFrame(conv_rows), ref, pd.DataFrame(agree_rows))


def append_csv(filename, new_df):
    path = OUT / filename
    old_df = pd.read_csv(path)
    combined = pd.concat([old_df, new_df], ignore_index=True)
    combined.to_csv(path, index=False)
    print(f"{filename}: {len(old_df)} -> {len(combined)} rows (+{len(new_df)})")


def update_excel_sheets():
    sobol = pd.read_csv(DM_DIR / "sobol_final_summary_cycle.csv")
    morris = pd.read_csv(DM_DIR / "morris_final_summary_cycle.csv")
    sobol.insert(0, "Dataset", "Datamining")
    morris.insert(0, "Dataset", "Datamining")

    with pd.ExcelWriter(XLSX, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        sobol.to_excel(writer, sheet_name="sobol_summary_datamining", index=False)
        morris.to_excel(writer, sheet_name="morris_summary_datamining", index=False)
    print(f"Added sheets 'sobol_summary_datamining' ({len(sobol)} rows) and "
          f"'morris_summary_datamining' ({len(morris)} rows) to {XLSX.name}")


def main():
    seed_df, conv_df, ref_df, agree_df = build_new_pairwise_rows()
    append_csv("seed_stability_pairwise.csv", seed_df)
    append_csv("convergence_pairwise.csv", conv_df)
    append_csv("reference_rankings.csv", ref_df)
    append_csv("method_agreement_pairwise.csv", agree_df)
    update_excel_sheets()


if __name__ == "__main__":
    main()
