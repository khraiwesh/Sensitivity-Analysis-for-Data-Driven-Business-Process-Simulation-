"""Pairwise rank-agreement analysis for combined_sa_indices.csv.

Unlike Spearman's rho (which is a correlation coefficient sensitive to the
magnitude of rank displacement), pairwise agreement asks a simpler, more
interpretable question for every unordered pair of parameters (p, q):

    "Does parameter p rank above parameter q in BOTH rankings being compared?"

agreement = (# concordant pairs) / (# pairs where neither ranking has a tie)

This is the same concordant/discordant-pair counting that underlies Kendall's
tau, but reported directly as a 0-1 fraction ("how many of the C(k,2) pairwise
orderings survived a change of seed/sample-size/method") rather than as a
correlation coefficient.
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent


def ranking_from_values(sub: pd.DataFrame, params: list) -> pd.Series:
    s = sub.set_index("parameter")["value"].reindex(params)
    if s.isna().any():
        missing = s[s.isna()].index.tolist()
        raise ValueError(f"Missing values for parameters {missing} in this slice.")
    return s.rank(ascending=False, method="average")


def pairwise_agreement(r1: pd.Series, r2: pd.Series, params: list) -> tuple:
    """Return (agreement_fraction, n_concordant, n_pairs_compared, n_pairs_total)."""
    n_total = 0
    n_compared = 0
    n_concordant = 0
    for p, q in itertools.combinations(params, 2):
        n_total += 1
        d1 = r1[p] - r1[q]
        d2 = r2[p] - r2[q]
        if d1 == 0 or d2 == 0:
            continue  # tie in either ranking -> excluded from comparable pairs
        n_compared += 1
        if (d1 > 0) == (d2 > 0):
            n_concordant += 1
    frac = n_concordant / n_compared if n_compared else np.nan
    return frac, n_concordant, n_compared, n_total


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    need = {"dataset", "method", "seed", "sample_size", "parameter", "value"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"Input file is missing columns: {missing}")
    df["parameter"] = df["parameter"].str.upper().str.strip()
    return df


def main(path: str = "combined_sa_indices.csv", outdir: str = "stability_out_pairwise"):
    df = load_data(path)
    out = Path(outdir)
    out.mkdir(exist_ok=True)

    seed_rows, conv_rows, ref_rows, agree_rows = [], [], [], []

    for (ds, method), g in df.groupby(["dataset", "method"]):
        params = sorted(g["parameter"].unique())
        sizes = sorted(g["sample_size"].unique())
        seeds = sorted(g["seed"].unique())

        for n in sizes:
            rankings = {
                s: ranking_from_values(g[(g.sample_size == n) & (g.seed == s)], params)
                for s in seeds
            }
            pair_fracs = []
            for s1, s2 in itertools.combinations(seeds, 2):
                frac, n_c, n_cmp, n_tot = pairwise_agreement(rankings[s1], rankings[s2], params)
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
                r1 = ranking_from_values(g[(g.sample_size == n1) & (g.seed == s)], params)
                r2 = ranking_from_values(g[(g.sample_size == n2) & (g.seed == s)], params)
                frac, n_c, n_cmp, n_tot = pairwise_agreement(r1, r2, params)
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
            frac, n_c, n_cmp, n_tot = pairwise_agreement(
                common["morris"], common["sobol"], params_common)
            agree_rows.append(dict(
                dataset=ds, n_concordant=n_c, n_pairs_compared=n_cmp,
                n_pairs_total=n_tot, agreement_morris_vs_sobol=frac,
                n_params_compared=len(common),
                params_excluded_from_comparison=",".join(sorted(excluded)) or "none",
            ))

    pd.DataFrame(seed_rows).to_csv(out / "seed_stability_pairwise.csv", index=False)
    pd.DataFrame(conv_rows).to_csv(out / "convergence_pairwise.csv", index=False)
    ref.to_csv(out / "reference_rankings.csv", index=False)
    pd.DataFrame(agree_rows).to_csv(out / "method_agreement_pairwise.csv", index=False)

    print("=== Reference rankings (seed-averaged @ largest size) ===")
    print(ref.pivot_table(index=["dataset", "parameter"], columns="method",
                          values="reference_rank"))
    print("\n=== Mean pairwise rank-agreement per size (fraction of concordant pairs) ===")
    ss = pd.DataFrame(seed_rows)
    print(ss[ss.seed_a == "MEAN"].pivot_table(
        index=["dataset", "method"], columns="sample_size", values="agreement"))
    print("\n=== Method agreement (Sobol vs Morris) ===")
    print(pd.DataFrame(agree_rows).to_string(index=False))
    print(f"\nAll outputs written to {out}/")


if __name__ == "__main__":
    main(*sys.argv[1:])
