"""Per-dataset seed-pair rank-stability comparison: with gateways vs without
gateways (Sobol ST), for BIMP. Same methodology as
Prosimos/_with_without_stability_table.py: for each condition separately,
averages the seed-pair mean agreement across all sample sizes N (from
bimp_seed_stability/seed_agreement_ST.csv), then reports whether removing
gateways improves or worsens that stability.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\Samira\SAExperiments\Experiment2\BIMP")
AGREEMENT_CSV = ROOT / "bimp_seed_stability" / "seed_agreement_ST.csv"

DATASET_LABELS = {"2012": "BPIC2012", "2017": "BPIC2017"}
DATASET_ORDER = list(DATASET_LABELS)


def effect_label(diff: float) -> str:
    if diff >= 0.10:
        return "\u2191 improves"
    if diff >= 0.02:
        return "\u2191 slight improvement"
    if diff <= -0.10:
        return "\u2193 worse"
    if diff <= -0.02:
        return "\u2193 slightly worse"
    return "\u2192 no change"


def main():
    df = pd.read_csv(AGREEMENT_CSV)
    df["dataset"] = df["dataset"].astype(str)
    mean_rows = df[df.seed_a == "MEAN"]
    # average the per-N mean seed-pair agreement across sample sizes (skips
    # N values where fewer than 2 seeds were available, i.e. agreement is NaN)
    per_dataset_gw = mean_rows.groupby(["dataset", "gw"])["agreement"].mean()

    rows = []
    for dataset in DATASET_ORDER:
        with_val = per_dataset_gw[(dataset, "with")]
        without_val = per_dataset_gw[(dataset, "without")]
        diff = without_val - with_val
        rows.append({
            "Dataset": DATASET_LABELS[dataset],
            "With gateways": round(with_val, 3),
            "Without gateways": round(without_val, 3),
            "Effect of removing GW": effect_label(diff),
        })

    table = pd.DataFrame(rows)
    out_csv = ROOT / "bimp_seed_stability" / "with_vs_without_stability_table.csv"
    table.to_csv(out_csv, index=False)
    print(table.to_string(index=False))
    print(f"\nSaved to {out_csv}")

    fig, ax = plt.subplots(figsize=(7.5, 0.55 * (len(table) + 1)))
    ax.axis("off")
    cell_text = [[row["Dataset"], f'{row["With gateways"]:.3f}',
                  f'{row["Without gateways"]:.3f}', row["Effect of removing GW"]]
                 for _, row in table.iterrows()]
    tbl = ax.table(cellText=cell_text,
                   colLabels=["Dataset", "With gateways", "Without gateways", "Effect of removing GW"],
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.8)
    for (row, col), cell in tbl.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#dddddd")
    fig.tight_layout()

    out_path = ROOT / "bimp_seed_stability" / "with_vs_without_stability_table.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
