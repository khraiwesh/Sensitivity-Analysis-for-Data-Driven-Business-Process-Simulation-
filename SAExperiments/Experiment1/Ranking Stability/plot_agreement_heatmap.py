"""Compact heatmap version (MAIN stability result): rows = dataset, columns =
sample size, cell = mean pairwise rank agreement between seed replicates AT
THE SAME sample size N (see pairwise_agreement.py). One heatmap for Morris,
one for Sobol, side by side. Much shorter vertically than the line-plot
version -- good for tight paper space.

For the broader "vs every other run regardless of seed/N" robustness check,
see plot_agreement_heatmap_allvsall.py instead.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent

DATASET_LABELS = {
    "2012": "BPIC2012",
    "2013_cycle_time": "BPIC2013",
    "2017": "BPIC2017",
    "production": "Production",
}
DATASET_ORDER = list(DATASET_LABELS)
METHOD_XLABEL = {"morris": "Number of trajectories", "sobol": "Number of samples"}


def main():
    df = pd.read_csv(ROOT / "stability_out_pairwise" / "seed_stability_pairwise.csv")
    mean_df = df[df.seed_a == "MEAN"].copy()

    plt.rcParams.update({"font.size": 8})
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 1.3))

    for ax, method in zip(axes, ["morris", "sobol"]):
        sub = mean_df[mean_df.method == method]
        sizes = sorted(sub["sample_size"].unique())
        piv = (sub.pivot(index="dataset", columns="sample_size", values="agreement")
               .reindex(index=DATASET_ORDER, columns=sizes))

        im = ax.imshow(piv.values, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(len(sizes)))
        ax.set_xticklabels(sizes)
        ax.set_yticks(range(len(DATASET_ORDER)))
        y_labels = [DATASET_LABELS[d] for d in DATASET_ORDER]
        ax.set_yticklabels(y_labels if method == "morris" else [], fontsize=7)
        ax.set_xlabel(METHOD_XLABEL[method])
        ax.set_title(method.capitalize(), fontsize=9)

        for i in range(piv.shape[0]):
            for j in range(piv.shape[1]):
                val = piv.values[i, j]
                if np.isnan(val):
                    continue
                color = "white" if val < 0.45 or val > 0.9 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=7, color=color)

    cbar = fig.colorbar(im, ax=axes, fraction=0.05, pad=0.02)
    cbar.set_label("Agreement", fontsize=7)
    cbar.ax.tick_params(labelsize=6)

    out_path = ROOT / "agreement_heatmap_paper.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
