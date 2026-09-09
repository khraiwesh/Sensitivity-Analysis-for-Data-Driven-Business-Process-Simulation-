import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def exact_perm_pvalue(rho: float, k: int) -> float:
    base = np.arange(k)
    rhos = []
    for perm in itertools.permutations(range(k)):
        r, _ = spearmanr(base, np.array(perm))
        rhos.append(r)
    rhos = np.array(rhos)
    return float(np.mean(np.abs(rhos) >= abs(rho) - 1e-12))


def ranking_from_values(sub: pd.DataFrame, params: list) -> pd.Series:
    s = sub.set_index("parameter")["value"].reindex(params)
    if s.isna().any():
        missing = s[s.isna()].index.tolist()
        raise ValueError(f"Missing values for parameters {missing} in this slice.")
    return s.rank(ascending=False, method="average")


def rho_between(r1: pd.Series, r2: pd.Series):
    k = len(r1)
    rho, _ = spearmanr(r1.values, r2.values)
    return float(rho), exact_perm_pvalue(rho, k)


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    need = {"dataset", "method", "seed", "sample_size", "parameter", "value"}
    missing = need - set(df.columns)
    if missing:
        sys.exit(f"Input file is missing columns: {missing}")
    df["parameter"] = df["parameter"].str.upper().str.strip()
    return df


def main(path: str = "sa_indices.csv", outdir: str = "stability_out"):
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
            pair_rhos = []
            for s1, s2 in itertools.combinations(seeds, 2):
                rho, p = rho_between(rankings[s1], rankings[s2])
                pair_rhos.append(rho)
                seed_rows.append(dict(dataset=ds, method=method, sample_size=n,
                                      seed_a=s1, seed_b=s2, n_params=len(params),
                                      rho=rho, p_exact=p))
            seed_rows.append(dict(dataset=ds, method=method, sample_size=n,
                                  seed_a="MEAN", seed_b="", n_params=len(params),
                                  rho=float(np.mean(pair_rhos)), p_exact=np.nan))

        for s in seeds:
            for n1, n2 in zip(sizes, sizes[1:]):
                r1 = ranking_from_values(g[(g.sample_size == n1) & (g.seed == s)], params)
                r2 = ranking_from_values(g[(g.sample_size == n2) & (g.seed == s)], params)
                rho, p = rho_between(r1, r2)
                conv_rows.append(dict(dataset=ds, method=method, seed=s,
                                      size_from=n1, size_to=n2, n_params=len(params),
                                      rho=rho, p_exact=p))

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
            rho, p = rho_between(common["morris"], common["sobol"])
            agree_rows.append(dict(
                dataset=ds, rho_morris_vs_sobol=rho, p_exact=p,
                n_params_compared=len(common),
                params_excluded_from_comparison=",".join(sorted(excluded)) or "none",
            ))

    pd.DataFrame(seed_rows).to_csv(out / "seed_stability.csv", index=False)
    pd.DataFrame(conv_rows).to_csv(out / "convergence.csv", index=False)
    ref.to_csv(out / "reference_rankings.csv", index=False)
    pd.DataFrame(agree_rows).to_csv(out / "method_agreement.csv", index=False)

    print("=== Reference rankings (seed-averaged @ largest size) ===")
    print(ref.pivot_table(index=["dataset", "parameter"], columns="method",
                          values="reference_rank"))
    print("\n=== Mean seed-stability rho per size ===")
    ss = pd.DataFrame(seed_rows)
    print(ss[ss.seed_a == "MEAN"].pivot_table(
        index=["dataset", "method"], columns="sample_size", values="rho"))
    print("\n=== Method agreement (Sobol vs Morris) ===")
    print(pd.DataFrame(agree_rows).to_string(index=False))
    print(f"\nAll outputs written to {out}/")


if __name__ == "__main__":
    main(*sys.argv[1:])
