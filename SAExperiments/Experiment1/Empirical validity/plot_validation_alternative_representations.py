"""Alternative ways to answer: "Does the SA method's ranking match reality?"

Same underlying data as plot_validation_heatmap_with_datamining.py
(Validation_combined.xlsx -> All_Datasets sheet: kpi_rank = ground-truth
importance ranking from actual KPI/CTD deviation; sa_morris_rank / sa_sobol_rank
= SA-method-derived ranking), but summarized with five different statistics
comparing the two rankings per dataset+method:

  - pairwise_agreement : fraction of concordant parameter pairs (existing metric)
  - top1_agreement     : do both rankings agree on the #1 (most influential) parameter?
  - top2_jaccard        : overlap of the top-2 parameters between the two rankings
  - kendalls_w          : Kendall's coefficient of concordance (2 rankers, n parameters)
  - spearman_rho        : Spearman rank correlation between kpi_rank and sa_rank

Shows the same external-validity question can score very differently depending
on which statistic is used to summarize the same two rankings.
"""
import itertools
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
PARAMS = ["AC", "AD", "RC", "RN", "TR"]
DATASET_ORDER = ["BPIC2012", "BPIC2013", "BPIC2017", "Production", "Datamining"]
METRIC_LABELS = {
    "pairwise_agreement": "Pairwise\nagreement",
    "top1_agreement": "Top-1\nagreement",
    "top2_jaccard": "Top-2\nJaccard",
    "kendalls_w": "Kendall's\nW",
    "spearman_rho": "Spearman's\nrho",
}
METRICS = list(METRIC_LABELS)


def pairwise_agreement(r1: pd.Series, r2: pd.Series, params: list) -> float:
    n_compared = 0
    n_concordant = 0
    for p, q in itertools.combinations(params, 2):
        d1, d2 = r1[p] - r1[q], r2[p] - r2[q]
        if d1 == 0 or d2 == 0:
            continue
        n_compared += 1
        if (d1 > 0) == (d2 > 0):
            n_concordant += 1
    return n_concordant / n_compared if n_compared else np.nan


def kendalls_w(rank_matrix: np.ndarray) -> float:
    """rank_matrix: (m rankers) x (n parameters), raw rank values.

    Re-ranks each row first: some sa_*_rank columns were originally ranked over
    a superset of parameters (e.g. including Gateways) then filtered down to the
    5 KPI-comparable ones, leaving non-contiguous values (e.g. {1,2,3,5,6}). The
    W formula requires each ranker to supply a clean 1..n permutation.
    """
    ranked = np.array([pd.Series(row).rank().to_numpy() for row in rank_matrix])
    m, n = ranked.shape
    R = ranked.sum(axis=0)
    S = np.sum((R - R.mean()) ** 2)
    T = 0.0
    for row in ranked:
        _, counts = np.unique(row, return_counts=True)
        T += np.sum(counts ** 3 - counts)
    denom = (m ** 2) * (n ** 3 - n) - m * T
    return 12 * S / denom if denom > 0 else np.nan


def compute_summary() -> pd.DataFrame:
    df = pd.read_excel(ROOT / "Validation_combined.xlsx", sheet_name="All_Datasets")

    rows = []
    for dataset in DATASET_ORDER:
        g = df[df.Dataset == dataset].set_index("group").reindex(PARAMS)
        kpi_rank = g["kpi_rank"]
        for method, col in [("morris", "sa_morris_rank"), ("sobol", "sa_sobol_rank")]:
            sa_rank = g[col]

            agreement = pairwise_agreement(kpi_rank, sa_rank, PARAMS)

            kpi_top1 = kpi_rank.idxmin()
            sa_top1 = sa_rank.idxmin()
            top1_rate = float(kpi_top1 == sa_top1)

            kpi_top2 = set(kpi_rank.nsmallest(2).index)
            sa_top2 = set(sa_rank.nsmallest(2).index)
            top2_jaccard = len(kpi_top2 & sa_top2) / len(kpi_top2 | sa_top2)

            rank_matrix = np.array([kpi_rank.values, sa_rank.values], dtype=float)
            w = kendalls_w(rank_matrix)

            spearman_rho = kpi_rank.corr(sa_rank, method="spearman")

            rows.append({
                "dataset": dataset, "method": method,
                "pairwise_agreement": agreement, "top1_agreement": top1_rate,
                "top2_jaccard": top2_jaccard, "kendalls_w": w, "spearman_rho": spearman_rho,
            })
    return pd.DataFrame(rows)


def main():
    summary = compute_summary()
    out_csv = ROOT / "validation_alternative_representations_summary.csv"
    summary.to_csv(out_csv, index=False)
    print(summary.to_string(index=False))
    print(f"\nSaved to {out_csv}")

    plt.rcParams.update({"font.size": 8})
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.2))

    for ax, method in zip(axes, ["morris", "sobol"]):
        sub = summary[summary.method == method].set_index("dataset").reindex(DATASET_ORDER)
        mat = sub[METRICS].to_numpy(dtype=float)

        im = ax.imshow(mat, cmap="RdYlGn", vmin=0, vmax=1)
        ax.set_xticks(range(len(METRICS)))
        ax.set_xticklabels([METRIC_LABELS[m] for m in METRICS], fontsize=7)
        ax.set_yticks(range(len(DATASET_ORDER)))
        ax.set_yticklabels(DATASET_ORDER, fontsize=7.5)
        ax.set_title(method.capitalize(), fontsize=9)

        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                val = mat[i, j]
                if np.isnan(val):
                    continue
                color = "white" if val < 0.45 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color=color)

    cbar = fig.colorbar(im, ax=axes, fraction=0.03, pad=0.02)
    cbar.set_label("Score", fontsize=8)
    fig.suptitle("Validation against KPI/CTD ground truth\n(same rankings, different statistics)", fontsize=10)

    out_path = ROOT / "validation_alternative_representations_heatmap.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
