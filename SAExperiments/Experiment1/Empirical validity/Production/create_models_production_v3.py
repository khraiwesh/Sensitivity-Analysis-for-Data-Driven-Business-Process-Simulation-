"""
create_models_production_v3.py
---------------------------------
QUANTILE-BASED perturbation design for the Production dataset, adapted
from create_models_2012_v3.py. Uses the ratio-based calendar-shrink
approach (like BPIC 2012/2017), NOT the additive-delta approach used for
BPIC 2013, because Production has 19 real, heterogeneous per-resource
calendars (not one degenerate shared calendar).

IMPORTANT DATASET-SPECIFIC ADAPTATION (RC and AC only)
--------------------------------------------------------
Production_train.json has granule_size = 60 minutes: SIMOD discretised
every calendar period into 1-hour granules. As a result, the *per-period*
duration distribution is degenerate for both RC and AC: median = 30th
percentile = 1.0 hour (174 of ~257 RC periods are exactly 1h; 16 of 30 AC
slots are exactly 1h). Applying the standard "shrink each period by its
own p30/p50 ratio" rule to per-period durations would therefore compute a
ratio of 1.0 and perturb NOTHING -- the same kind of degeneracy problem
the thesis already documents for BPIC 2013's Resource Numbers group
(low-cardinality, clustered discrete variable -> percentile-point shift
collapses to zero change).

The fix follows the same principle used there: operationalise the same
statistical rule (median -> p30) on a different, non-degenerate quantity
that reflects the same real-world "less availability" stress, then apply
the resulting single ratio uniformly to every period (exactly as the
original ratio-based method does) -- no change to the direction or
meaning of the perturbation, only to which distribution the p50/p30 ratio
is computed from:

  RC (Resource Calendars): ratio is computed from the distribution of
      TOTAL WEEKLY HOURS PER CALENDAR (19 calendars -> 19 totals), not
      from individual period durations. median=21.0h, p30=12.0h,
      ratio=0.571 (verified against the uploaded Production_train.json).
  AC (Arrival Calendar): there is only ONE arrival calendar, so the
      "per-calendar total" trick has nothing to average over. Instead,
      the ratio is computed from the distribution of TOTAL HOURS PER
      DAY-OF-WEEK (Mon..Sun -> up to 7 totals). median=9.5h, p30=8.0h,
      ratio=0.842 (verified against the uploaded Production_train.json).

AD, TR, RN are UNCHANGED from the 2012/2017 template: AD/TR operate on
individually fitted distributions (no degeneracy found), and RN already
operates per-resource via a discrete step-down (never used a global
period-duration quantile in the first place).

This requires pix_framework to be installed (already a dependency of the
SA tool / thesis_env), since AD/TR reuse pix_framework.statistics.distribution
.DurationDistribution directly -- no distribution formulas are
reimplemented here.

Run:
    conda activate thesis_env
    python3 create_models_production_v3.py

Output files are saved with a "_v3" suffix specific to production, so
they never collide with any other dataset's model files.
"""

import json
import copy
import os
import math
from datetime import datetime
from collections import defaultdict

import numpy as np
from pix_framework.statistics.distribution import DurationDistribution

# ─────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────

# EDIT THIS to wherever you put the file Samira sent you
ORIGINAL_JSON = os.path.expanduser(
    "~/Desktop/thesis_eval/Production_train.json"
)

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

MEDIAN_Q = 0.50
STRESS_LOW_Q = 0.30   # "less capacity" direction (RC, AC, RN, AD)
STRESS_HIGH_Q = 0.70  # "more load" direction (TR)

INCREASE_FACTOR = 1.3  # kept only for perturb_gateways, unrelated to the 5 groups


# ─────────────────────────────────────────────
# 2. HELPER FUNCTIONS — distribution-based (AD, TR)
# ─────────────────────────────────────────────

def quantile_shift_delta(distribution: DurationDistribution, target_q: float) -> float:
    """Computes the ADDITIVE shift (in the distribution's own units, e.g.
    seconds) that would move this distribution's median to its own
    `target_q` percentile: delta = ppf(target_q) - ppf(0.5).

    An additive shift is used instead of a multiplicative ratio because
    some fitted gamma distributions have a shape parameter far below 1,
    which makes their median numerically collapse towards zero -- dividing
    by a near-zero median would be unstable. A subtraction has no
    equivalent failure mode."""
    import scipy.stats as st

    t = distribution.type.value
    if t == "gamma":
        shape = distribution.mean ** 2 / distribution.var
        scale = distribution.var / distribution.mean
        dist = st.gamma(shape, loc=0, scale=scale)
    elif t == "lognorm":
        pow_mean = distribution.mean ** 2
        phi = math.sqrt(distribution.var + pow_mean)
        mu = math.log(pow_mean / phi)
        sigma = math.sqrt(math.log(phi ** 2 / pow_mean))
        dist = st.lognorm(sigma, loc=0, scale=math.exp(mu))
    elif t == "expon":
        scale = distribution.mean - distribution.min
        dist = st.expon(loc=distribution.min, scale=scale)
    elif t == "norm":
        dist = st.norm(loc=distribution.mean, scale=distribution.std)
    elif t == "uniform":
        dist = st.uniform(loc=distribution.min, scale=distribution.max - distribution.min)
    elif t == "fix":
        return 0.0  # nothing to shift
    else:
        print(f"  [!] Unsupported distribution type for quantile shift: {t} -- leaving unchanged")
        return 0.0

    p50 = dist.ppf(MEDIAN_Q)
    p_target = dist.ppf(target_q)
    return p_target - p50


def shift_distribution_mean(d: DurationDistribution, delta: float) -> DurationDistribution:
    """Returns a new DurationDistribution of the same type, with `delta`
    added to the mean, variance/std left UNCHANGED, and min/max left
    UNCHANGED (clamped so the new mean stays within [min, max] if set)."""
    new_mean = d.mean + delta
    if d.min is not None:
        new_mean = max(new_mean, d.min)
    if d.max is not None:
        new_mean = min(new_mean, d.max)
    return DurationDistribution(
        name=d.type,
        mean=new_mean,
        var=d.var,
        std=d.std,
        minimum=d.min,
        maximum=d.max,
    )


def patch_none_fields(d: DurationDistribution) -> DurationDistribution:
    """Patches any None field (left unset by from_dict() for distribution
    types that don't use it) to a safe default so downstream code does
    not crash."""
    if d.mean is None:
        d.mean = 0.0
    if d.var is None:
        d.var = 0.0
    if d.std is None:
        d.std = math.sqrt(d.var) if d.var else 0.0
    if d.min is None:
        d.min = 0.0
    if d.max is None:
        d.max = 0.0
    return d


def perturb_arrival_distribution(data):
    """AD: shift the fitted distribution from its median to its own 30th
    percentile (faster arrivals -> more congestion)."""
    data = copy.deepcopy(data)
    d = DurationDistribution.from_dict(data["arrival_time_distribution"])
    d = patch_none_fields(d)
    delta = quantile_shift_delta(d, STRESS_LOW_Q)
    new_d = shift_distribution_mean(d, delta)
    data["arrival_time_distribution"] = new_d.to_prosimos_distribution()
    print(f"  [OK] Perturbed: Arrival Distribution "
          f"(median -> p30, mean {d.mean:.1f}s -> {new_d.mean:.1f}s, delta={delta:+.1f}s)")
    return data


def perturb_tasks_resources(data):
    """TR: shift EACH task-resource duration distribution individually
    from its own median to its own 70th percentile (longer durations ->
    more load)."""
    data = copy.deepcopy(data)
    deltas = []
    for task in data["task_resource_distribution"]:
        for resource in task["resources"]:
            if not resource.get("distribution_params"):
                continue
            try:
                d = DurationDistribution.from_dict(resource)
            except Exception as e:
                print(f"  [!] Skipping unparseable distribution for resource {resource.get('resource_id')}: {e}")
                continue
            d = patch_none_fields(d)
            delta = quantile_shift_delta(d, STRESS_HIGH_Q)
            new_d = shift_distribution_mean(d, delta)
            new_dict = new_d.to_prosimos_distribution()
            resource["distribution_name"] = new_dict["distribution_name"]
            resource["distribution_params"] = new_dict["distribution_params"]
            deltas.append(delta)
    mean_delta = sum(deltas) / len(deltas) if deltas else float("nan")
    print(f"  [OK] Perturbed: Tasks & Resources Distributions "
          f"(median -> p70 per distribution, mean delta={mean_delta:+.1f}s over {len(deltas)} distributions)")
    return data


# ─────────────────────────────────────────────
# 3. HELPER FUNCTIONS — empirical-quantile-based (RC, AC, RN)
# ─────────────────────────────────────────────

def parse_time(s):
    """Production_train.json has a few timestamps with fractional seconds
    (e.g. '07:59:59.999000'), unlike BPIC's clean 'HH:MM:SS' -- try both."""
    for fmt in ("%H:%M:%S", "%H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised time format: {s}")


def period_duration_hours(begin_str, end_str):
    return (parse_time(end_str) - parse_time(begin_str)).total_seconds() / 3600.0


def shrink_period(begin_str, end_str, factor):
    """Shrinks [begin, end] by keeping begin fixed and moving end back so
    the new duration = old duration * factor (factor < 1). Output is
    always written back in plain HH:MM:SS (no fractional seconds), which
    Prosimos/SIMOD both read without issue."""
    b = parse_time(begin_str)
    e = parse_time(end_str)
    duration = e - b
    new_end = b + duration * factor
    return new_end.strftime("%H:%M:%S")


def perturb_resource_calendars(data):
    """RC (Production-specific): compute the empirical distribution of
    TOTAL WEEKLY HOURS PER CALENDAR (one total per calendar, 19 calendars
    here) rather than per-period durations, because per-period durations
    are degenerate at this dataset's 60-minute granule size (median =
    p30 = 1.0h -> ratio 1.0 -> no perturbation). The resulting single
    ratio (p30/p50 of the per-calendar totals) is then applied uniformly
    to every period, exactly as in the standard ratio-based design."""
    data = copy.deepcopy(data)
    calendar_totals = [
        sum(period_duration_hours(p["beginTime"], p["endTime"]) for p in cal["time_periods"])
        for cal in data["resource_calendars"]
    ]
    p50 = float(np.percentile(calendar_totals, 50))
    p30 = float(np.percentile(calendar_totals, 30))
    factor = p30 / p50 if p50 > 0 else 1.0
    for cal in data["resource_calendars"]:
        for period in cal["time_periods"]:
            period["endTime"] = shrink_period(period["beginTime"], period["endTime"], factor)
    print(f"  [OK] Perturbed: Resource Calendars "
          f"(per-calendar TOTAL weekly hours median={p50:.2f}h -> p30={p30:.2f}h, "
          f"factor={factor:.4f}, applied uniformly to every period)")
    return data


def perturb_arrival_calendar(data):
    """AC (Production-specific): compute the empirical distribution of
    TOTAL HOURS PER DAY-OF-WEEK (there is only one arrival calendar here,
    so a per-calendar aggregate isn't available -- per-day aggregation is
    the natural analogue). Per-slot durations are degenerate for the same
    granule-size reason as RC. The resulting ratio is applied uniformly
    to every slot."""
    data = copy.deepcopy(data)
    day_totals = defaultdict(float)
    for slot in data["arrival_time_calendar"]:
        day_totals[slot["from"]] += period_duration_hours(slot["beginTime"], slot["endTime"])
    totals = list(day_totals.values())
    p50 = float(np.percentile(totals, 50))
    p30 = float(np.percentile(totals, 30))
    factor = p30 / p50 if p50 > 0 else 1.0
    for slot in data["arrival_time_calendar"]:
        slot["endTime"] = shrink_period(slot["beginTime"], slot["endTime"], factor)
    print(f"  [OK] Perturbed: Arrival Calendar "
          f"(per-day-of-week TOTAL hours median={p50:.2f}h -> p30={p30:.2f}h, "
          f"factor={factor:.4f}, applied uniformly to every slot)")
    return data


def perturb_resource_numbers(data):
    """RN: unchanged from the standard template -- each resource's
    assignedTasks count is reduced by one step to the next distinct value
    below it in the empirical distribution (floored at 1). This already
    operates per-resource, so it is unaffected by the granule-size
    degeneracy that required adapting RC/AC above."""
    data = copy.deepcopy(data)

    lengths = [
        len(res["assignedTasks"])
        for profile in data["resource_profiles"] for res in profile["resource_list"]
    ]
    p50 = float(np.percentile(lengths, 50))

    pre_edit_resources = {
        task["task_id"]: list(task["resources"])
        for task in data["task_resource_distribution"]
    }

    removed_assignments = {}
    for profile in data["resource_profiles"]:
        for res in profile["resource_list"]:
            tasks = res["assignedTasks"]
            keep = max(1, len(tasks) - 1)
            removed = tasks[keep:]
            res["assignedTasks"] = tasks[:keep]
            removed_assignments[res["id"]] = set(removed)

    for task in data["task_resource_distribution"]:
        task_id = task["task_id"]
        task["resources"] = [
            r for r in task["resources"]
            if task_id not in removed_assignments.get(r["resource_id"], set())
        ]
        if not task["resources"]:
            task["resources"] = pre_edit_resources[task_id]

    print(f"  [OK] Perturbed: Resource Numbers "
          f"(assignedTasks length median={p50:.1f}; each resource stepped down by "
          f"one distinct value, floored at 1)")
    return data


def perturb_gateways(data):
    """Gateways: unchanged (not one of the five core parameter groups
    perturbed individually; kept only for completeness / consistency
    with the other create_models_*_v3.py scripts)."""
    data = copy.deepcopy(data)
    for gateway in data["gateway_branching_probabilities"]:
        probs = gateway["probabilities"]
        if len(probs) >= 2:
            new_first = min(probs[0]["value"] * INCREASE_FACTOR, 0.99)
            remaining = 1.0 - new_first
            total_others = sum(p["value"] for p in probs[1:])
            probs[0]["value"] = new_first
            for p in probs[1:]:
                if total_others > 0:
                    p["value"] = (p["value"] / total_others) * remaining
                else:
                    p["value"] = remaining / (len(probs) - 1)
    return data


# ─────────────────────────────────────────────
# 4. MODEL CREATION
# ─────────────────────────────────────────────

def create_model(original_data, groups_to_perturb):
    data = copy.deepcopy(original_data)
    for group in groups_to_perturb:
        if group == "arrival_distribution":
            data = perturb_arrival_distribution(data)
        elif group == "arrival_calendar":
            data = perturb_arrival_calendar(data)
        elif group == "resource_calendars":
            data = perturb_resource_calendars(data)
        elif group == "resource_numbers":
            data = perturb_resource_numbers(data)
        elif group == "tasks_resources":
            data = perturb_tasks_resources(data)
        elif group == "gateways":
            data = perturb_gateways(data)
        else:
            print(f"  [!] Unknown group: {group} -- skipped")
    return data


def save_model(data, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)
    print(f"  -> Saved: {filepath}")


# ─────────────────────────────────────────────
# 5. MAIN
# ─────────────────────────────────────────────

def main():
    print(f"\nLoading original JSON from:\n  {ORIGINAL_JSON}\n")
    with open(ORIGINAL_JSON, "r") as f:
        original = json.load(f)
    print("Original JSON loaded successfully.\n")

    print("── Individual Group Models (v3, quantile-based: median -> p30/p70) ──")
    print("── (RC/AC use Production-specific aggregate quantities -- see docstring) ──\n")

    print("── Model_RC_v3: Resource Calendars only ──")
    save_model(create_model(original, ["resource_calendars"]), "model_RC_production_v3.json")

    print("\n── Model_AD_v3: Arrival Distribution only ──")
    save_model(create_model(original, ["arrival_distribution"]), "model_AD_production_v3.json")

    print("\n── Model_RN_v3: Resource Numbers only ──")
    save_model(create_model(original, ["resource_numbers"]), "model_RN_production_v3.json")

    print("\n── Model_TR_v3: Tasks & Resources only ──")
    save_model(create_model(original, ["tasks_resources"]), "model_TR_production_v3.json")

    print("\n── Model_AC_v3: Arrival Calendar only ──")
    save_model(create_model(original, ["arrival_calendar"]), "model_AC_production_v3.json")

    print("\n" + "=" * 60)
    print("All Production 'v3' (quantile-based) models created successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
