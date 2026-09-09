"""Does including Gateways in the SA change the ranking of the remaining
parameters? Compares the "with gateway" vs "without gateway" Sobol-ST
ranking for each dataset, at matching seed/n_samples configs, using the
same pairwise_agreement metric as the rest of the analysis.

Source: prosimos_seed_stability/seed_rankings_ST.csv (per-seed rankings,
already built from Prosimos_sobol_cycletime_extract.xlsx). Only the 5
parameters common to both conditions are compared (Gateways is dropped from
the "with" ranking since it doesn't exist "without"); pairwise_agreement only
depends on relative order, so no re-ranking of the 5-subset is needed.
"""
import itertools
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment2\Prosimos")
RANKINGS_CSV = ROOT / "prosimos_seed_stability" / "seed_rankings_ST.csv"

COMMON_PARAMS = ["Arrival Calendar", "Arrival Distribution", "Resource Calendars",
                  "Resource Numbers", "Tasks and Resources Distributions"]
DATASET_LABELS = {"2012": "BPIC2012", "2013": "BPIC2013", "2017": "BPIC2017",
                   "production": "Production", "datamining": "Datamining"}
DATASET_ORDER = list(DATASET_LABELS)


def pairwise_agreement(r1: pd.Series, r2: pd.Series, params: list) -> float:
    n_compared = n_concordant = 0
    for p, q in itertools.combinations(params, 2):
        d1, d2 = r1[p] - r1[q], r2[p] - r2[q]
        if d1 == 0 or d2 == 0:
            continue
        n_compared += 1
        if (d1 > 0) == (d2 > 0):
            n_concordant += 1
    return n_concordant / n_compared if n_compared else np.nan


def main():
    df = pd.read_csv(RANKINGS_CSV)

    rows = []
    for dataset in DATASET_ORDER:
        g = df[df.dataset == dataset]
        sizes = sorted(g["n_samples"].unique())
        for n in sizes:
            gn = g[g.n_samples == n]
            seeds = sorted(gn["seed"].unique())
            agreements = []
            for seed in seeds:
                with_r = (gn[(gn.gw == "with") & (gn.seed == seed)]
                          .set_index("group")["rank"].reindex(COMMON_PARAMS))
                without_r = (gn[(gn.gw == "without") & (gn.seed == seed)]
                             .set_index("group")["rank"].reindex(COMMON_PARAMS))
                if with_r.isna().any() or without_r.isna().any():
                    continue
                agreements.append(pairwise_agreement(with_r, without_r, COMMON_PARAMS))
            mean_agreement = float(np.nanmean(agreements)) if agreements else np.nan
            rows.append({"dataset": dataset, "n_samples": n,
                         "n_seeds": len(agreements), "agreement": mean_agreement})

    summary = pd.DataFrame(rows)
    out_csv = ROOT / "prosimos_seed_stability" / "with_vs_without_gateway_agreement.csv"
    summary.to_csv(out_csv, index=False)
    print(summary.to_string(index=False))
    print(f"\nSaved to {out_csv}")

    piv = summary.pivot(index="dataset", columns="n_samples", values="agreement").reindex(DATASET_ORDER)

    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter, NullLocator

    DATASET_COLORS = {"2012": "tab:red", "2013": "tab:green", "2017": "tab:blue",
                       "production": "tab:orange", "datamining": "tab:purple"}
    sizes = sorted(summary["n_samples"].unique())

    plt.rcParams.update({"font.size": 9})
    fig, ax = plt.subplots(figsize=(5.0, 3.5))
    for dataset in DATASET_ORDER:
        row = piv.loc[dataset]
        ax.plot(row.index, row.values, marker="o", markersize=5, linewidth=1.5,
                label=DATASET_LABELS[dataset], color=DATASET_COLORS[dataset])

    ax.set_xlabel("Number of samples (N)")
    ax.set_ylabel("Pairwise rank agreement")
    ax.set_title("With- vs without-gateway ranking agreement (Sobol ST)")
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator(sizes))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    fig.tight_layout()

    out_path = ROOT / "prosimos_seed_stability" / "with_vs_without_gateway_agreement.png"
    fig.savefig(out_path, dpi=300)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
