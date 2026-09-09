# small script: takes the per-seed-pair stability results and boils them
# down into one average number per (dataset, method) combo, with a plain-
# English label so it's easy to read at a glance
import pandas as pd

ss = pd.read_csv("stability_out/seed_stability.csv")
# the "MEAN" rows are already an average of the pairwise rows below them,
# so we drop them here to avoid counting the same info twice
pairwise = ss[ss.seed_a != "MEAN"]

# group by dataset+method, then average the rho values across all seed pairs
summary = (pairwise.groupby(["dataset", "method"])
           .agg(n_configs=("rho", "size"), avg_rho=("rho", "mean"))
           .reset_index())

# turns a rho number into a simple word so it's readable without knowing stats
def qualitative(rho):
    if rho >= 0.9: return "Very Stable"
    if rho >= 0.7: return "Stable"
    if rho >= 0.5: return "Moderate"
    return "Unstable"

summary["qualitative_stability"] = summary["avg_rho"].apply(qualitative)
summary = summary.sort_values(["dataset", "method"])
summary.to_csv("stability_out/overall_grid_summary.csv", index=False)
print(summary.to_string(index=False))
