"""Seed-pair rank-stability analysis for Prosimos only, per dataset x gateway
config, sourced directly from Prosimos_sobol_cycletime_extract.xlsx.

Same methodology as gateway_stability_analysis.py: per (dataset, gw), builds
seed-level rankings at each sample size N, computes seed-pair rank agreement
(fraction of concordant parameter pairs), and finds the smallest N at which
the ranking is stable across all seed pairs and stays stable for all larger N.
Seed/N runs whose JSON contained null S1/ST values (genuinely failed runs)
are skipped rather than treated as a valid ranking. (Note: datamining's rows
were previously mostly null due to a bug in an earlier extraction pass -- this
was fixed 2026-09-03 via _fix_datamining_extract.py; all 18 datamining
seed/N/gateway runs now have valid data.)
"""
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

XLSX = Path(r"C:\Users\Samira\SAExperiments\Experiment2\Prosimos\Prosimos_sobol_cycletime_extract.xlsx")
OUT_DIR = XLSX.parent / "prosimos_seed_stability"

GW_LABEL = {"With gateway": "with", "Without gateway": "without"}


def ranking(sub, groups, value_col="ST"):
    s = sub.set_index("group")[value_col].reindex(groups)
    return s.rank(ascending=False, method="average")


def pairwise_agreement(r1, r2, groups):
    n_compared = n_concordant = 0
    for p, q in itertools.combinations(groups, 2):
        d1, d2 = r1[p] - r1[q], r2[p] - r2[q]
        if d1 == 0 or d2 == 0:
            continue
        n_compared += 1
        if (d1 > 0) == (d2 > 0):
            n_concordant += 1
    return n_concordant / n_compared if n_compared else np.nan


def analyze(df, value_col="ST"):
    rank_rows, agree_rows, stability_rows = [], [], []

    for (ds, gw), g in df.groupby(["dataset", "gw"]):
        groups = sorted(g["group"].unique())
        sizes = sorted(g["n_samples"].unique())
        seeds = sorted(g["seed"].unique())

        n_stable_from = None
        for n in sizes:
            sub_n = g[g.n_samples == n]
            rankings = {}
            for s in seeds:
                sub_s = sub_n[sub_n.seed == s]
                if sub_s.empty or sub_s[value_col].isna().any():
                    continue  # missing/failed run for this seed x N
                r = ranking(sub_s, groups, value_col)
                rankings[s] = r
                for grp in groups:
                    rank_rows.append(dict(dataset=ds, gw=gw, n_samples=n, seed=s,
                                           group=grp, rank=r[grp]))
            avail_seeds = sorted(rankings.keys())
            fracs = []
            for s1, s2 in itertools.combinations(avail_seeds, 2):
                frac = pairwise_agreement(rankings[s1], rankings[s2], groups)
                fracs.append(frac)
                agree_rows.append(dict(dataset=ds, gw=gw, n_samples=n,
                                        seed_a=s1, seed_b=s2, agreement=frac))
            mean_frac = float(np.nanmean(fracs)) if fracs else np.nan
            agree_rows.append(dict(dataset=ds, gw=gw, n_samples=n,
                                    seed_a="MEAN", seed_b="",
                                    n_seeds_available=len(avail_seeds), agreement=mean_frac))

            if mean_frac == 1.0 and n_stable_from is None:
                n_stable_from = n
            elif not np.isnan(mean_frac) and mean_frac != 1.0:
                n_stable_from = None
            elif np.isnan(mean_frac):
                n_stable_from = None  # can't confirm stability with <2 seeds available

        stability_rows.append(dict(dataset=ds, gw=gw, n_groups=len(groups),
                                    n_seeds=len(seeds), sizes=sizes,
                                    smallest_stable_N=n_stable_from if n_stable_from else "not reached"))

    return pd.DataFrame(rank_rows), pd.DataFrame(agree_rows), pd.DataFrame(stability_rows)


def run_for(df, value_col):
    rank_df, agree_df, stability_df = analyze(df, value_col)

    OUT_DIR.mkdir(exist_ok=True)
    rank_df.to_csv(OUT_DIR / f"seed_rankings_{value_col}.csv", index=False)
    agree_df.to_csv(OUT_DIR / f"seed_agreement_{value_col}.csv", index=False)
    stability_df.to_csv(OUT_DIR / f"stability_summary_{value_col}.csv", index=False)

    print("=" * 100)
    print(f"[{value_col}] SMALLEST N STABLE ACROSS ALL SEED PAIRS (with vs without gateway)")
    print("=" * 100)
    piv = stability_df.pivot(index="dataset", columns="gw", values="smallest_stable_N")
    print(piv.to_string())

    print()
    print("=" * 100)
    print(f"[{value_col}] SEED-PAIR MEAN AGREEMENT per dataset/gw/N (n_seeds_available shown in brackets)")
    print("=" * 100)
    mean_rows = agree_df[agree_df.seed_a == "MEAN"].copy()
    mean_rows["cell"] = mean_rows.apply(lambda r: f"{r.agreement:.3f} ({int(r.n_seeds_available)})" if pd.notna(r.agreement) else f"n/a ({int(r.n_seeds_available)})", axis=1)
    piv2 = mean_rows.pivot(index=["dataset", "gw"], columns="n_samples", values="cell")
    print(piv2.to_string())
    print()


def main():
    df = pd.read_excel(XLSX, sheet_name="Prosimos_sobol_cycletime")
    # the sheet has manually merged cells for repeated gateway/seed values (visual
    # grouping) -> openpyxl/pandas reads those as NaN for every row but the first
    # in each merged block, so forward-fill to restore the true per-row values.
    df["gateway"] = df["gateway"].ffill()
    df["seed"] = df["seed"].ffill()
    df["gw"] = df["gateway"].map(GW_LABEL)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)

    run_for(df, "ST")
    run_for(df, "S1")

    print(f"Saved outputs to {OUT_DIR}/")


if __name__ == "__main__":
    main()
