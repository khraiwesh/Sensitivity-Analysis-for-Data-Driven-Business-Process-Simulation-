"""Seed-pair rank-stability (Sobol ST) vs sample size N, one line per dataset,
with-gateways and without-gateways panels side by side, for BIMP.

Source: bimp_seed_stability/seed_agreement_ST.csv (seed_a=="MEAN" rows).
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter, NullLocator

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment2\BIMP")
AGREEMENT_CSV = ROOT / "bimp_seed_stability" / "seed_agreement_ST.csv"

DATASET_LABELS = {"2012": "BPIC2012", "2017": "BPIC2017"}
DATASET_ORDER = list(DATASET_LABELS)
DATASET_COLORS = {"2012": "tab:red", "2017": "tab:blue"}
DATASET_MARKERS = {"2012": "o", "2017": "^"}
DATASET_LINESTYLES = {"2012": "-", "2017": "-."}
GW_TITLES = {"with": "With gateways", "without": "Without gateways"}


def main():
    df = pd.read_csv(AGREEMENT_CSV)
    df["dataset"] = df["dataset"].astype(str)
    mean_rows = df[df.seed_a == "MEAN"]
    sizes = sorted(mean_rows["n_samples"].unique())

    plt.rcParams.update({"font.size": 9})
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.6), sharey=True)

    for ax, gw in zip(axes, ["with", "without"]):
        sub = mean_rows[mean_rows.gw == gw]
        for dataset in DATASET_ORDER:
            g = sub[sub.dataset == dataset].sort_values("n_samples")
            ax.plot(g["n_samples"], g["agreement"], marker=DATASET_MARKERS[dataset],
                    markersize=6, linestyle=DATASET_LINESTYLES[dataset], linewidth=1.5,
                    label=DATASET_LABELS[dataset], color=DATASET_COLORS[dataset])
        ax.set_title(GW_TITLES[gw], fontsize=10)
        ax.set_xlabel("Number of samples (N)")
        ax.set_xscale("log")
        ax.xaxis.set_major_locator(FixedLocator(sizes))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)

    axes[0].set_ylabel("Seed-pair rank agreement")
    axes[1].legend(loc="lower left", fontsize=8, frameon=False)
    fig.suptitle("BIMP seed-pair rank stability (Sobol ST): with vs without gateways", fontsize=10)
    fig.tight_layout()

    out_path = ROOT / "bimp_seed_stability" / "with_vs_without_stability_lineplot.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
