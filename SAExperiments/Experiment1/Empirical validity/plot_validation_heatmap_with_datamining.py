"""Validation-against-KPI-and-CTD heatmap (Morris/Sobol-SA rank vs KPI rank),
now including Datamining, computed directly from Validation_combined.xlsx's
All_Datasets sheet (kpi_rank, sa_sobol_rank, sa_morris_rank columns).
"""
import itertools
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
PARAMS = ["AC", "AD", "RC", "RN", "TR"]
DATASET_ORDER = ["BPIC2012", "BPIC2013", "BPIC2017", "Production", "Datamining"]


def pairwise_agreement(r1, r2):
    n_compared = n_concordant = 0
    for p, q in itertools.combinations(PARAMS, 2):
        d1, d2 = r1[p] - r1[q], r2[p] - r2[q]
        if d1 == 0 or d2 == 0:
            continue
        n_compared += 1
        if (d1 > 0) == (d2 > 0):
            n_concordant += 1
    return n_concordant / n_compared if n_compared else float("nan")


def compute_validation_table():
    df = pd.read_excel(ROOT / "Validation_combined.xlsx", sheet_name="All_Datasets")
    df["group"] = df["group"].str.upper().str.strip()
    df["Dataset"] = df["Dataset"].replace({"2012": "BPIC2012", "2013": "BPIC2013", "2017": "BPIC2017"})

    rows = []
    for ds in DATASET_ORDER:
        sub = df[df.Dataset == ds].set_index("group").reindex(PARAMS)
        rows.append(dict(dataset=ds,
                          Morris=pairwise_agreement(sub["kpi_rank"], sub["sa_morris_rank"]),
                          Sobol=pairwise_agreement(sub["kpi_rank"], sub["sa_sobol_rank"])))
    return pd.DataFrame(rows).set_index("dataset").reindex(DATASET_ORDER)[["Morris", "Sobol"]]


def main():
    val_df = compute_validation_table()

    plt.rcParams.update({"font.size": 8})
    fig, ax = plt.subplots(figsize=(2.4, 2.0))
    im = ax.imshow(val_df.values, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(val_df.columns)))
    ax.set_xticklabels(val_df.columns)
    ax.set_yticks(range(len(val_df.index)))
    ax.set_yticklabels(val_df.index, fontsize=7)
    ax.set_title("Validation against\nKPI and CTD", fontsize=9, fontweight="bold")

    for i in range(val_df.shape[0]):
        for j in range(val_df.shape[1]):
            val = val_df.values[i, j]
            if np.isnan(val):
                continue
            color = "white" if val < 0.45 or val > 0.9 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.08, pad=0.05)
    cbar.set_label("Agreement", fontsize=7)
    cbar.ax.tick_params(labelsize=6)

    out_path = ROOT / "validation_heatmap_with_datamining.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(val_df.to_string())
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
