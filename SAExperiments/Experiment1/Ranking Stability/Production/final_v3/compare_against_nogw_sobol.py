"""
compare_against_nogw_sobol.py
--------------------------------
Compares the ALREADY-COMPUTED individual-perturbation results for
Production (KPI deviation + 8 Chapela-Campa metrics, from
individual_group_analysis_final.csv) against a NEW Sobol reference
ranking -- specifically the gateway-EXCLUDED Sobol run Samira sent as a
follow-up, instead of the gateway-included one used in the original
analysis.

No re-simulation and no re-computation of Chapela-Campa distances is
needed: those numbers don't depend on which SA reference ranking they're
being checked against. Only the correlation/tier-matching step is
redone, against the new 5-group (no-GW) Sobol ranking.

Usage:
    python3 compare_against_nogw_sobol.py \
        <individual_group_analysis_final.csv> \
        <nogw_reference_rankings.csv>

Where <nogw_reference_rankings.csv> is the reference_rankings.csv
produced by spearman_stability_v2.py on the gateway-excluded Sobol run
(stability_out/reference_rankings.csv inside the production_nogw folder).
"""
import sys
import itertools
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

GROUPS = ["RC", "AD", "RN", "TR", "AC"]
METRICS = ["NGD", "CFLD", "AED", "CED", "RED", "CAR", "CTD", "CWD"]


def exact_perm_pvalue(rho: float, k: int) -> float:
    base = np.arange(k)
    rhos = []
    for perm in itertools.permutations(range(k)):
        r, _ = spearmanr(base, np.array(perm))
        rhos.append(r)
    rhos = np.array(rhos)
    return float(np.mean(np.abs(rhos) >= abs(rho) - 1e-12))


def main():
    results_path, refranks_path = sys.argv[1], sys.argv[2]

    results = pd.read_csv(results_path).set_index("group")
    refranks = pd.read_csv(refranks_path)

    sobol_nogw = (refranks[refranks.method == "sobol"]
                  .set_index("parameter")["reference_rank"].to_dict())
    missing = set(GROUPS) - set(sobol_nogw)
    if missing:
        sys.exit(f"reference_rankings.csv is missing parameters: {missing} "
                  f"-- did you point this at the gateway-EXCLUDED Sobol run?")

    print("=" * 70)
    print("Comparison against gateway-EXCLUDED Sobol reference ranking")
    print("=" * 70)
    ranking_str = " > ".join(sorted(GROUPS, key=lambda g: sobol_nogw[g]))
    print(f"\nSobol (no-GW) reference ranking: {ranking_str}\n")

    sobol_vec = [sobol_nogw[g] for g in GROUPS]

    # -- KPI deviation --
    kpi_rank = results.loc[GROUPS, "kpi_rank"].to_dict()
    kpi_vec = [kpi_rank[g] for g in GROUPS]
    rho_kpi, _ = spearmanr(sobol_vec, kpi_vec)
    p_kpi = exact_perm_pvalue(rho_kpi, len(GROUPS))
    print(f"Spearman rho (Sobol no-GW vs KPI deviation rank): {rho_kpi:.3f}  (p={p_kpi:.3f})")

    # -- overall CC deviation --
    cc_rank = results.loc[GROUPS, "cc_overall_rank"].to_dict()
    cc_vec = [cc_rank[g] for g in GROUPS]
    rho_cc, _ = spearmanr(sobol_vec, cc_vec)
    p_cc = exact_perm_pvalue(rho_cc, len(GROUPS))
    print(f"Spearman rho (Sobol no-GW vs overall CC deviation rank): {rho_cc:.3f}  (p={p_cc:.3f})")

    # -- tier-based matching (top-3 / bottom-2) across KPI + 8 metrics --
    sa_top3 = set(sorted(GROUPS, key=lambda g: sobol_nogw[g])[:3])
    sa_bot2 = set(sorted(GROUPS, key=lambda g: sobol_nogw[g])[3:])
    print(f"\nSA tier A (top-3): {sorted(sa_top3, key=lambda g: sobol_nogw[g])}")
    print(f"SA tier B (bot-2): {sorted(sa_bot2, key=lambda g: sobol_nogw[g])}")

    print(f"\n{'Metric':<6} {'Dev Ranking':<50} {'Match':>6} {'rho':>8}")
    print("-" * 78)

    total_matches, total_possible, per_metric_rho = 0, 0, {}
    all_metrics_inc = ["KPI"] + METRICS
    for m in all_metrics_inc:
        if m == "KPI":
            vals = kpi_rank
            dev_rank_m = vals  # already a rank (1=largest deviation)
        else:
            col = f"cc_{m}"
            raw = results.loc[GROUPS, col].to_dict()
            sorted_g = sorted(raw, key=lambda g: raw[g], reverse=True)
            dev_rank_m = {g: i + 1 for i, g in enumerate(sorted_g)}

        matches = 0
        for g in GROUPS:
            dr = dev_rank_m.get(g, 99)
            in_top3, in_bot2 = dr <= 3, dr >= 4
            if (g in sa_top3 and in_top3) or (g in sa_bot2 and in_bot2):
                matches += 1
        total_matches += matches
        total_possible += 5

        dev_vec = [dev_rank_m[g] for g in GROUPS]
        rho_m, _ = spearmanr(sobol_vec, dev_vec)
        per_metric_rho[m] = rho_m

        dev_str = " > ".join(sorted(GROUPS, key=lambda g: dev_rank_m[g]))
        print(f"{m:<6} {dev_str:<50} {matches}/5  {rho_m:>8.3f}")

    pct = 100 * total_matches / total_possible
    print("-" * 78)
    print(f"\nTotal tier matches (Sobol no-GW): {total_matches}/{total_possible} ({pct:.1f}%)")
    print(f"Average Spearman rho across all metrics (Sobol no-GW): "
          f"{np.mean(list(per_metric_rho.values())):.3f}")

    print("\n" + "=" * 70)
    print("For comparison, the gateway-INCLUDED Sobol results were:")
    print("  KPI deviation rho = 0.800 (p=0.133)")
    print("  Overall CC deviation rho = 0.100 (p=0.950)")
    print("  Tier matches = 30/45 (66.7%)")
    print("=" * 70)


if __name__ == "__main__":
    main()
