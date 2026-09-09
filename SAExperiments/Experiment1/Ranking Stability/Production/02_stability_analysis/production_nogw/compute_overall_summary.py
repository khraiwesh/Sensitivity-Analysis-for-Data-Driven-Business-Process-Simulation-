"""
compute_overall_summary_generic.py
------------------------------------
Same logic as compute_overall_summary.py, but takes the stability_out
folder as a CLI argument instead of hardcoding "stability_out/", so it
works for any dataset run (e.g. stability_out_production/).

Usage:
    python3 compute_overall_summary_generic.py stability_out_production
"""
import sys
import pandas as pd

def main(outdir="stability_out"):
    ss = pd.read_csv(f"{outdir}/seed_stability.csv")
    pairwise = ss[ss.seed_a != "MEAN"]

    summary = (pairwise.groupby(["dataset", "method"])
               .agg(n_configs=("rho", "size"), avg_rho=("rho", "mean"))
               .reset_index())

    def qualitative(rho):
        if rho >= 0.9: return "Very Stable"
        if rho >= 0.7: return "Stable"
        if rho >= 0.5: return "Moderate"
        return "Unstable"

    summary["qualitative_stability"] = summary["avg_rho"].apply(qualitative)
    summary = summary.sort_values(["dataset", "method"])
    summary.to_csv(f"{outdir}/overall_grid_summary.csv", index=False)
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main(*sys.argv[1:])
