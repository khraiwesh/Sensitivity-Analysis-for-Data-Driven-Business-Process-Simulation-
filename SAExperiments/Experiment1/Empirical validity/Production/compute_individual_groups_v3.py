"""
compute_individual_groups_production_v3.py
----------------------------------------------
Same logic as compute_individual_groups_v3.py, extended with a
"production" / "production_v3" entry so it works on the Production
dataset's individual-perturbation simulation outputs, without touching
the BPIC 2012/2013/2017 SA_RANKINGS or logic.

  1. --dataset accepts "production" / "production_v3" in addition to the
     existing BPIC options.
  2. SA_RANKINGS["production"] is looked up using the base dataset name
     ("_v3" suffix stripped), exactly as for the BPIC datasets -- the SA
     reference ranking itself does not change, only the perturbation
     magnitudes used to generate the comparison logs do.
  3. Requires simulation_outputs/production_v3/logs/ to already exist
     (i.e. run_simulations_production_v3.py must be run first).

Usage:
    python3 compute_individual_groups_production_v3.py --dataset production_v3
"""

import os
import argparse
import itertools
import numpy as np
import pandas as pd
import time
import statistics
from datetime import timedelta
from scipy.stats import spearmanr


def exact_perm_pvalue(rho: float, k: int) -> float:
    """Exact two-sided permutation p-value for Spearman's rho with k items.
    Identical to the function in spearman_stability_v2.py -- scipy's
    asymptotic p-value is unreliable for a ranking of only 5 (or 6) items,
    e.g. it can print p=0.000 when the true minimum possible exact
    p-value for k=5 is 1/120 (approx 0.0083). All p-values reported by
    this script use this exact permutation test instead of scipy's."""
    base = np.arange(k)
    rhos = []
    for perm in itertools.permutations(range(k)):
        r, _ = spearmanr(base, np.array(perm))
        rhos.append(r)
    rhos = np.array(rhos)
    return float(np.mean(np.abs(rhos) >= abs(rho) - 1e-12))

from log_distance_measures.config import EventLogIDs, DistanceMetric
from log_distance_measures import n_gram_distribution as ngd_mod
from log_distance_measures import control_flow_log_distance as cfld_mod
from log_distance_measures import absolute_event_distribution as aed_mod
from log_distance_measures import circadian_event_distribution as ced_mod
from log_distance_measures import relative_event_distribution as red_mod
from log_distance_measures import case_arrival_distribution as car_mod
from log_distance_measures import cycle_time_distribution as ctd_mod
from log_distance_measures import circadian_workforce_distribution as cwd_mod

LOG_IDS = EventLogIDs(
    case="case_id", activity="activity", resource="resource",
    start_time="start_time", end_time="end_time"
)

SEEDS = [1, 2, 3, 4, 5]
GROUPS = ["RC", "AD", "RN", "TR", "AC"]
METRICS = ["NGD", "CFLD", "AED", "CED", "RED", "CAR", "CTD", "CWD"]
DIM = {
    "NGD": "Control-flow", "CFLD": "Control-flow", "AED": "Temporal",
    "CED": "Temporal", "RED": "Temporal", "CAR": "Congestion",
    "CTD": "Congestion", "CWD": "Resource"
}

SA_RANKINGS = {
    "2012": {
        "sobol":  {"RC": 1, "AD": 2, "RN": 3, "TR": 4, "AC": 5},
        "morris": {"RN": 1, "RC": 2, "TR": 3, "AD": 4, "AC": 5},
    },
    "2017": {
        "sobol":  {"RC": 1, "AD": 2, "AC": 3, "GW": 4, "RN": 5, "TR": 6},
        "morris": {"RC": 1, "AD": 2, "RN": 3, "AC": 4, "TR": 5},
    },
    "2013": {
        "sobol":  {"RC": 1, "TR": 2, "RN": 3, "AD": 4, "AC": 5},
        "morris": {"TR": 1, "RC": 2, "RN": 3, "AD": 4, "AC": 5},
    },
    # Production reference rankings, from the stability analysis run on
    # Samira's Sobol (n=2048, GW included, 6 groups) and Morris (t=512,
    # GW excluded, 5 groups) results. GW is kept in the Sobol dict for
    # completeness (matches the 2017 precedent) but is never a member of
    # GROUPS, so it is never individually perturbed here.
    "production": {
        "sobol":  {"GW": 1, "RC": 2, "RN": 3, "TR": 4, "AC": 5, "AD": 6},
        "morris": {"RN": 1, "RC": 2, "TR": 3, "AD": 4, "AC": 5},
    },
}


# reads one simulated event log CSV, with a few retries because sometimes
# the file isn't fully written to disk yet when we try to read it
def load_log(logs_dir, model_name, seed):
    path = os.path.join(logs_dir, f"log_{model_name}_seed{seed}.csv")
    if not os.path.exists(path):
        print(f"  [WARNING] File not found: {path}")
        return None
    df = None
    last_error = None
    for attempt in range(5):
        try:
            df = pd.read_csv(path)
            if df.empty or len(df.columns) == 0:
                # transient macOS I/O stall can yield a 0-byte/partial read
                # even though the file exists and os.path.exists() is True
                raise pd.errors.EmptyDataError("read returned an empty frame")
            break
        except (TimeoutError, OSError, pd.errors.EmptyDataError) as e:
            last_error = e
            df = None
            time.sleep(1.5)
    if df is None:
        try:
            df = pd.read_csv(path, engine="python")
            if df.empty or len(df.columns) == 0:
                raise pd.errors.EmptyDataError("read returned an empty frame")
        except Exception:
            print(f"  [ERROR] Could not read {path} after retries: {last_error}")
            return None
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["end_time"] = pd.to_datetime(df["end_time"], utc=True)
    df["resource"] = df["resource"].astype(str)
    df["case_id"] = df["case_id"].astype(str)
    return df


# cycle time for one case = last activity end time minus first activity start
# time; this averages that across every case in the log
def compute_avg_cycle_time(log):
    ct = log.groupby("case_id").agg(s=("start_time", "min"), e=("end_time", "max"))
    ct["dur"] = (ct["e"] - ct["s"]).dt.total_seconds()
    return ct["dur"].mean()


# runs all 8 Chapela-Campa distance metrics comparing the original log
# against one perturbed log. Each metric is wrapped in its own try/except
# so if one metric fails (e.g. bad data), the others still get computed
def compute_all_metrics(log_orig, log_other):
    res = {}
    try:
        res["NGD"] = ngd_mod.n_gram_distribution_distance(log_orig, LOG_IDS, log_other, LOG_IDS, n=3, normalize=True)
    except Exception as e:
        print(f"    [NGD error] {e}"); res["NGD"] = None
    try:
        res["CFLD"] = cfld_mod.control_flow_log_distance(log_orig, LOG_IDS, log_other, LOG_IDS, parallel=False)
    except Exception as e:
        print(f"    [CFLD error] {e}"); res["CFLD"] = None
    try:
        res["AED"] = aed_mod.absolute_event_distribution_distance(log_orig, LOG_IDS, log_other, LOG_IDS, metric=DistanceMetric.WASSERSTEIN)
    except Exception as e:
        print(f"    [AED error] {e}"); res["AED"] = None
    try:
        res["CED"] = ced_mod.circadian_event_distribution_distance(log_orig, LOG_IDS, log_other, LOG_IDS, metric=DistanceMetric.WASSERSTEIN)
    except Exception as e:
        print(f"    [CED error] {e}"); res["CED"] = None
    try:
        res["RED"] = red_mod.relative_event_distribution_distance(log_orig, LOG_IDS, log_other, LOG_IDS, metric=DistanceMetric.WASSERSTEIN)
    except Exception as e:
        print(f"    [RED error] {e}"); res["RED"] = None
    try:
        res["CAR"] = car_mod.case_arrival_distribution_distance(log_orig, LOG_IDS, log_other, LOG_IDS, metric=DistanceMetric.WASSERSTEIN)
    except Exception as e:
        print(f"    [CAR error] {e}"); res["CAR"] = None
    try:
        res["CTD"] = ctd_mod.cycle_time_distribution_distance(log_orig, LOG_IDS, log_other, LOG_IDS, bin_size=timedelta(hours=1), metric=DistanceMetric.WASSERSTEIN)
    except Exception as e:
        print(f"    [CTD error] {e}"); res["CTD"] = None
    try:
        res["CWD"] = cwd_mod.circadian_workforce_distribution_distance(log_orig, LOG_IDS, log_other, LOG_IDS, metric=DistanceMetric.WASSERSTEIN)
    except Exception as e:
        print(f"    [CWD error] {e}"); res["CWD"] = None
    return res


def run_analysis(dataset):
    # dataset may be "2012_v3" -- folder path uses it AS-IS,
    # but SA_RANKINGS lookup uses the base name (suffix stripped).
    sa_key = dataset.replace("_v3", "")

    # Script lives inside final_v3/, and each dataset's simulation outputs
    # (logs/, kpis/, etc.) live in a sibling folder final_v3/{dataset}/ --
    # e.g. final_v3/production_v3/logs/, final_v3/2012_v3/logs/, etc.
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(_script_dir, dataset, "logs")
    output_dir = os.path.join(_script_dir, dataset)

    print("=" * 70)
    print(f"BPIC {dataset} -- Individual Group Perturbation Analysis")
    print(f"(SA reference rankings taken from '{sa_key}')")
    print(f"Seeds: {SEEDS} | Metrics: KPI + 8 Chapela-Campa")
    print("=" * 70)

    sa_sobol = SA_RANKINGS[sa_key]["sobol"]
    sa_morris = SA_RANKINGS[sa_key]["morris"]

    print("\n-- Step 1: Cycle Time KPI --------------------------------------------")
    # compute the average cycle time of the ORIGINAL (unperturbed) model,
    # averaged across all seeds -- this is the baseline everything else compares to
    orig_cts = []
    for s in SEEDS:
        log = load_log(logs_dir, "original", s)
        if log is not None:
            orig_cts.append(compute_avg_cycle_time(log))
    orig_avg = statistics.mean(orig_cts)
    print(f"\nOriginal average cycle time: {orig_avg:.1f}s  (n={len(orig_cts)} seeds)")

    # now do the same for each perturbed group, and record how far its
    # cycle time deviates from the original (bigger deviation = perturbing
    # that group changed the process more)
    kpi_results = {}
    for g in GROUPS:
        cts = []
        for s in SEEDS:
            log = load_log(logs_dir, g, s)
            if log is not None:
                cts.append(compute_avg_cycle_time(log))
        if cts:
            avg = statistics.mean(cts)
            kpi_results[g] = {
                "avg_ct": round(avg, 1),
                "deviation": round(abs(orig_avg - avg), 1),
                "direction": "up" if avg > orig_avg else "down"
            }

    print(f"\n{'Group':<6} {'Avg CT (s)':>12} {'|O-X| (s)':>12} {'Dir':>5} {'SA Sobol#':>10} {'SA Morris#':>11}")
    print("-" * 60)
    for g in GROUPS:
        r = kpi_results[g]
        print(f"{g:<6} {r['avg_ct']:>12.1f} {r['deviation']:>12.1f} {r['direction']:>5} {sa_sobol[g]:>10} {sa_morris[g]:>11}")

    # rank groups by how much they deviated (#1 = biggest deviation = most influential)
    kpi_ranked = sorted(kpi_results.items(), key=lambda x: x[1]["deviation"], reverse=True)
    kpi_rank = {g: i + 1 for i, (g, _) in enumerate(kpi_ranked)}

    print("\nKPI deviation ranking (1 = largest deviation from original):")
    for i, (g, r) in enumerate(kpi_ranked, 1):
        print(f"  #{i}: {g}  |O-X|={r['deviation']:.1f}s  (Sobol SA#{sa_sobol[g]}, Morris SA#{sa_morris[g]})")

    # check if the group ranking based on simulation deviation agrees with
    # the ranking the sensitivity analysis (SA) already predicted
    kpi_vec = [kpi_rank[g] for g in GROUPS]
    rho_kpi_sobol, _ = spearmanr([sa_sobol[g] for g in GROUPS], kpi_vec)
    rho_kpi_morris, _ = spearmanr([sa_morris[g] for g in GROUPS], kpi_vec)
    p_kpi_sobol = exact_perm_pvalue(rho_kpi_sobol, len(GROUPS))
    p_kpi_morris = exact_perm_pvalue(rho_kpi_morris, len(GROUPS))
    print(f"\n  Spearman rho (Sobol  SA vs KPI rank): {rho_kpi_sobol:.3f}  (p={p_kpi_sobol:.3f})")
    print(f"  Spearman rho (Morris SA vs KPI rank): {rho_kpi_morris:.3f}  (p={p_kpi_morris:.3f})")

    print("\n-- Step 2: Chapela-Campa Metrics --------------------------------------")
    print("  Computing distances for all groups and seeds (this may take a few minutes)...")

    # for every seed, compare the original log against each perturbed-group
    # log, and collect all 8 metric values per group
    raw = {g: {m: [] for m in METRICS} for g in GROUPS}
    for seed in SEEDS:
        log_o = load_log(logs_dir, "original", seed)
        if log_o is None:
            print(f"  [WARNING] Original log missing for seed {seed}, skipping.")
            continue
        for g in GROUPS:
            log_g = load_log(logs_dir, g, seed)
            if log_g is None:
                continue
            print(f"  Computing {g} vs original (seed={seed})...")
            mvals = compute_all_metrics(log_o, log_g)
            for m in METRICS:
                if mvals.get(m) is not None:
                    raw[g][m].append(mvals[m])

    # average each metric across all seeds, so we get one stable number per (group, metric)
    cc_avg = {g: {m: (statistics.mean(raw[g][m]) if raw[g][m] else None) for m in METRICS} for g in GROUPS}

    print(f"\nAveraged Chapela-Campa distances (Distance(original, perturbed_X)):\n")
    print(f"{'Group':<6}", end="")
    for m in METRICS:
        print(f" {m:>8}", end="")
    print()
    print("-" * (6 + 9 * len(METRICS)))
    for g in GROUPS:
        print(f"{g:<6}", end="")
        for m in METRICS:
            v = cc_avg[g][m]
            print(f" {v:>8.4f}" if v is not None else f" {'N/A':>8}", end="")
        print()

    print("\n-- Step 3: Full Ranking per Metric ------------------------------------")
    print("\nRanking by deviation magnitude (#1 = largest deviation):")
    print("SA Sobol rank shown in parentheses.\n")
    col_w = 12
    header = f"{'Metric':<6} {'Dimension':<14}"
    for i in range(1, 6):
        header += f" {'#' + str(i):<{col_w}}"
    print(header)
    print("-" * (6 + 14 + 5 * (col_w + 1)))

    per_metric_rank = {}
    for m in METRICS:
        vals = {g: cc_avg[g][m] for g in GROUPS if cc_avg[g][m] is not None}
        ranked_groups = sorted(vals.items(), key=lambda x: x[1], reverse=True)
        per_metric_rank[m] = {g: i + 1 for i, (g, _) in enumerate(ranked_groups)}
        row = f"{m:<6} {DIM.get(m, ''):<14}"
        for g, _ in ranked_groups:
            cell = f"{g}(S#{sa_sobol[g]})"
            row += f" {cell:<{col_w}}"
        print(row)

    print("\n-- Step 4: Tier-Based Matching -----------------------------------------")
    # instead of comparing exact ranks, this checks a looser question: does a
    # group that SA said is "important" (top-3) also show a big deviation in
    # simulation, and does a group SA said is "unimportant" (bottom-2) also
    # show a small deviation? This is checked for both SA methods separately.
    for sa_method, sa_r in [("Sobol", sa_sobol), ("Morris", sa_morris)]:
        sa_top3 = set(sorted(sa_r, key=sa_r.get)[:3])
        sa_bot2 = set(sorted(sa_r, key=sa_r.get)[3:])
        print(f"\n  [{sa_method}]")
        print(f"  SA tier A (top-3): {sorted(sa_top3, key=sa_r.get)}")
        print(f"  SA tier B (bot-2): {sorted(sa_bot2, key=sa_r.get)}")

        total_matches = 0
        total_possible = 0
        spearman_vals = []
        all_metrics_inc = ["KPI"] + METRICS

        print(f"  {'Metric':<6} {'Dim':<14} {'Dev Ranking':<50} {'Match':>6} {'rho':>8}")
        print("  " + "-" * 88)

        for m in all_metrics_inc:
            if m == "KPI":
                vals = {g: kpi_results[g]["deviation"] for g in GROUPS if g in kpi_results}
                dim = "KPI"
            else:
                vals = {g: cc_avg[g][m] for g in GROUPS if cc_avg[g][m] is not None}
                dim = DIM.get(m, "")

            sorted_g = sorted(vals, key=lambda g: vals[g], reverse=True)
            dev_rank_m = {g: i + 1 for i, g in enumerate(sorted_g)}

            # count how many groups landed in the tier (top-3 / bottom-2)
            # that SA predicted for them -- a "match" means SA's prediction
            # for that group was confirmed by this metric
            matches = 0
            details = []
            for g in GROUPS:
                dr = dev_rank_m.get(g, 99)
                in_dev_top3 = dr <= 3
                in_dev_bot2 = dr >= 4
                if g in sa_top3 and in_dev_top3:
                    matches += 1; details.append(f"{g}OK")
                elif g in sa_bot2 and in_dev_bot2:
                    matches += 1; details.append(f"{g}OK")
                else:
                    details.append(f"{g}X")

            total_matches += matches
            total_possible += 5

            sa_vec = [sa_r[g] for g in GROUPS]
            dev_vec = [dev_rank_m.get(g, 99) for g in GROUPS]
            rho, _ = spearmanr(sa_vec, dev_vec)
            spearman_vals.append(rho)

            dev_str = " > ".join([f"{g}({'A' if g in sa_top3 else 'B'})#{dev_rank_m[g]}" for g in sorted_g])
            print(f"  {m:<6} {dim:<14} {dev_str:<50} {matches}/5  {rho:>8.3f}  {' '.join(details)}")

        print("  " + "-" * 88)
        pct = 100 * total_matches / total_possible
        avg_rho = statistics.mean(spearman_vals)
        print(f"\n  Total tier matches ({sa_method}): {total_matches}/{total_possible} ({pct:.1f}%)")
        print(f"  Average Spearman rho across all metrics ({sa_method}): {avg_rho:.3f}")

    print("\n-- Step 5: Overall Spearman rho Summary --------------------------------")
    overall_avg = {g: statistics.mean([cc_avg[g][m] for m in METRICS if cc_avg[g][m] is not None]) for g in GROUPS}
    overall_ranked = sorted(overall_avg.items(), key=lambda x: x[1], reverse=True)
    cc_rank = {g: i + 1 for i, (g, _) in enumerate(overall_ranked)}

    print(f"\n  Overall CC deviation ranking (averaged across 8 metrics):")
    for g, _ in overall_ranked:
        print(f"    #{cc_rank[g]}: {g}  (avg CC distance = {overall_avg[g]:.4f})")

    for sa_method, sa_r in [("Sobol", sa_sobol), ("Morris", sa_morris)]:
        sa_vec = [sa_r[g] for g in GROUPS]
        kpi_vec = [kpi_rank[g] for g in GROUPS]
        cc_vec = [cc_rank[g] for g in GROUPS]
        rho_kpi, _ = spearmanr(sa_vec, kpi_vec)
        rho_cc, _ = spearmanr(sa_vec, cc_vec)
        p_kpi = exact_perm_pvalue(rho_kpi, len(GROUPS))
        p_cc = exact_perm_pvalue(rho_cc, len(GROUPS))
        print(f"\n  {sa_method}:")
        print(f"    Spearman rho (SA vs KPI deviation rank):         {rho_kpi:.3f}  (p={p_kpi:.3f})")
        print(f"    Spearman rho (SA vs overall CC deviation rank):  {rho_cc:.3f}  (p={p_cc:.3f})")

    # collect everything computed above into one row per group, so it can be saved as a CSV
    rows = []
    for g in GROUPS:
        row = {
            "group": g,
            "kpi_avg_ct": kpi_results.get(g, {}).get("avg_ct"),
            "kpi_deviation": kpi_results.get(g, {}).get("deviation"),
            "kpi_direction": kpi_results.get(g, {}).get("direction"),
            "kpi_rank": kpi_rank.get(g),
            "cc_overall_rank": cc_rank.get(g),
            "sa_sobol_rank": sa_sobol.get(g),
            "sa_morris_rank": sa_morris.get(g),
        }
        for m in METRICS:
            row[f"cc_{m}"] = cc_avg[g].get(m)
        rows.append(row)

    out_path = os.path.join(output_dir, "individual_group_analysis_final.csv")
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"\nResults saved to: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Individual group perturbation analysis (try variant).")
    parser.add_argument(
        "--dataset",
        choices=["2012", "2017", "2013", "2012_v3", "2017_v3", "2013_v3",
                 "production", "production_v3"],
        required=True,
    )
    args = parser.parse_args()
    run_analysis(args.dataset)
