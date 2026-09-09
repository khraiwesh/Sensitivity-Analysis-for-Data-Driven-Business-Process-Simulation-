"""
create_models_datamining_v3.py
----------------------------------
QUANTILE-BASED perturbation design for the DataMining (ACR /
ConsultaDataMining201618) dataset, adapted from
create_models_production_v3.py. Uses the ratio-based calendar-shrink
approach (like BPIC 2012/2017/Production), since this dataset has 17
real, heterogeneous per-resource calendar templates (not one degenerate
shared calendar like BPIC 2013).

TWO DATASET-SPECIFIC ADAPTATIONS
-----------------------------------
1) Resource Calendars (RC) -- granule-size degeneracy, same fix as Production.
   ConsultaDataMining201618_train.json has granule_size = 60 minutes, so
   most individual calendar periods are exactly 1 hour (98 of ~134
   periods). The standard "shrink each period by its own p30/p50 ratio"
   rule is therefore degenerate at the per-period level (median = p30 =
   1.0h -> ratio 1.0 -> no perturbation). As with Production, the ratio is
   instead computed from the distribution of TOTAL WEEKLY HOURS PER
   CALENDAR (17 calendars -> 17 totals): median=9.0h, p30=6.0h,
   ratio=0.667 (verified against the uploaded JSON). This ratio is then
   applied uniformly to every period, exactly as the standard method does.

   Arrival Calendar (AC) does NOT need this adaptation here: its per-slot
   durations are not degenerate for this dataset (median=2.0h, p30=1.5h,
   ratio=0.75), unlike Production where AC also needed the aggregate fix.
   AC therefore uses the standard per-period ratio directly.

2) Prosimos empty-weekday crash (documented in Samira's README).
   14 of this dataset's 17 resource-calendar templates are missing one or
   more weekdays entirely (SIMOD discovers them that way when a resource
   was never observed working that day). Samira's own cluster pipeline
   patches this by padding empty weekdays with a zero-length working
   interval (beginTime == endTime) before simulation, in her own fork of
   Prosimos's simulate_samples.py. Our local, plain pip-installed Prosimos
   does NOT have that patch, so without a workaround the ORIGINAL
   (unperturbed) model would already be liable to crash Prosimos on
   reaching one of these empty days -- independent of anything this script
   perturbs.

   pad_empty_weekdays() below applies the exact same fix Samira describes:
   for every resource-calendar template, any weekday with zero time_periods
   gets one zero-length period added (beginTime == endTime). Prosimos then
   finds *something* at that day's index 0; the resource still has no real
   working time that day, so behaviour is unchanged. This is applied to
   the ORIGINAL model AND all five perturbed models, so every simulation
   run in run_simulations_datamining_v3.py, including the "original"
   baseline, uses a padded copy.

AD, TR, RN are UNCHANGED from the standard template: AD/TR operate on
individually fitted distributions, and RN operates per-resource via a
discrete step-down; neither is affected by either adaptation above.

Run:
    conda activate thesis_env
    python3 create_models_datamining_v3.py

Output files are saved with a "_v3" suffix specific to datamining, so
they never collide with any other dataset's model files.
"""

import json
import copy
import os
import math
from datetime import datetime

import numpy as np
from pix_framework.statistics.distribution import DurationDistribution

# ─────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────

# EDIT THIS to wherever you put the file Samira sent you
ORIGINAL_JSON = os.path.expanduser(
    "~/Desktop/datamining_eval/ConsultaDataMining201618_train.json"
)

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

MEDIAN_Q = 0.50
STRESS_LOW_Q = 0.30   # "less capacity" direction (RC, AC, RN, AD)
STRESS_HIGH_Q = 0.70  # "more load" direction (TR)

ALL_WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                "FRIDAY", "SATURDAY", "SUNDAY"]

INCREASE_FACTOR = 1.3  # kept only for perturb_gateways, unrelated to the 5 groups


# ─────────────────────────────────────────────
# 2. HELPER FUNCTIONS — distribution-based (AD, TR)
# ─────────────────────────────────────────────

def quantile_shift_delta(distribution: DurationDistribution, target_q: float) -> float:
    """Computes the ADDITIVE shift (in the distribution's own units, e.g.
    seconds) that would move this distribution's median to its own
    `target_q` percentile: delta = ppf(target_q) - ppf(0.5)."""
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
        return 0.0
    else:
        print(f"  [!] Unsupported distribution type for quantile shift: {t} -- leaving unchanged")
        return 0.0

    p50 = dist.ppf(MEDIAN_Q)
    p_target = dist.ppf(target_q)
    return p_target - p50


def shift_distribution_mean(d: DurationDistribution, delta: float) -> DurationDistribution:
    new_mean = d.mean + delta
    if d.min is not None:
        new_mean = max(new_mean, d.min)
    if d.max is not None:
        new_mean = min(new_mean, d.max)
    return DurationDistribution(
        name=d.type, mean=new_mean, var=d.var, std=d.std,
        minimum=d.min, maximum=d.max,
    )


def patch_none_fields(d: DurationDistribution) -> DurationDistribution:
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
    from its own median to its own 70th percentile.

    BUGFIX (found while validating the DataMining results): "fix"
    (constant-value) distributions must be skipped ENTIRELY, not just
    given delta=0. The previous version still round-tripped every
    resource with non-empty distribution_params through
    shift_distribution_mean()/to_prosimos_distribution(), including
    "fix" ones. For some "fix" entries, pix_framework's from_dict()
    leaves .mean as None (fix distributions don't naturally populate a
    mean/var/std/min/max schema the way continuous distributions do),
    which patch_none_fields() then set to 0.0 -- and that 0.0 got written
    straight back out as the new "fix" value, silently replacing real
    task durations (some over an hour long) with 0. This was confirmed
    empirically on DataMining: 180 of 1422 distributions collapsed to
    0.0, which is what caused the counter-intuitive ~20% DROP in average
    cycle time for the TR perturbation (instant tasks speeding up the
    process, despite every genuinely-shifted distribution getting
    LONGER as intended). Skipping "fix" outright removes this failure
    mode regardless of how pix_framework happens to populate its fields.
    """
    data = copy.deepcopy(data)
    deltas = []
    skipped_fix = 0
    for task in data["task_resource_distribution"]:
        for resource in task["resources"]:
            if resource.get("distribution_name") == "fix":
                skipped_fix += 1
                continue  # leave constant-duration entries completely untouched
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
          f"(median -> p70 per distribution, mean delta={mean_delta:+.1f}s over {len(deltas)} distributions; "
          f"{skipped_fix} fix-type distributions left untouched)")
    return data


# ─────────────────────────────────────────────
# 3. HELPER FUNCTIONS — empirical-quantile-based (RC, AC, RN)
# ─────────────────────────────────────────────

def parse_time(s):
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
    the new duration = old duration * factor (factor < 1)."""
    b = parse_time(begin_str)
    e = parse_time(end_str)
    duration = e - b
    new_end = b + duration * factor
    return new_end.strftime("%H:%M:%S")


def perturb_resource_calendars(data):
    """RC (DataMining-specific, same fix as Production): compute the
    empirical distribution of TOTAL WEEKLY HOURS PER CALENDAR (one total
    per calendar template, 17 templates here) rather than per-period
    durations, because per-period durations are degenerate at this
    dataset's 60-minute granule size (median = p30 = 1.0h). The resulting
    single ratio is applied uniformly to every period."""
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
    """AC: standard per-period ratio (NOT degenerate for this dataset --
    median=2.0h, p30=1.5h -- unlike Production, so no aggregate-quantity
    adaptation is needed here)."""
    data = copy.deepcopy(data)
    durations = [period_duration_hours(s["beginTime"], s["endTime"])
                 for s in data["arrival_time_calendar"]]
    p50 = float(np.percentile(durations, 50))
    p30 = float(np.percentile(durations, 30))
    factor = p30 / p50 if p50 > 0 else 1.0
    for slot in data["arrival_time_calendar"]:
        slot["endTime"] = shrink_period(slot["beginTime"], slot["endTime"], factor)
    print(f"  [OK] Perturbed: Arrival Calendar "
          f"(per-slot duration median={p50:.2f}h -> p30={p30:.2f}h, "
          f"factor={factor:.4f}, applied uniformly to every slot)")
    return data


def perturb_resource_numbers(data):
    """RN: unchanged from the standard template -- each resource's
    assignedTasks count is reduced by one step to the next distinct value
    below it in the empirical distribution (floored at 1)."""
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
    """Gateways: unchanged (not one of the five core groups perturbed
    individually; kept only for consistency with the other scripts)."""
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
# 4. PROSIMOS EMPTY-WEEKDAY WORKAROUND (Samira's README fix)
# ─────────────────────────────────────────────

def pad_empty_weekdays(data):
    """Applies the exact workaround described in Samira's README: any
    resource-calendar template missing one or more weekdays entirely gets
    a zero-length period (beginTime == endTime) added for each missing
    day, so Prosimos finds *something* at that day's index and does not
    crash. The resource still has no real working time that day -- this
    changes nothing about the model's behaviour, only prevents the crash
    our plain (unpatched) local Prosimos would otherwise hit.

    Applied to every model this script produces -- the original baseline
    copy AND all five perturbed models -- since 14 of the 17 calendar
    templates in this dataset are missing at least one weekday already,
    independent of anything perturbed here.
    """
    data = copy.deepcopy(data)
    total_padded = 0
    for cal in data["resource_calendars"]:
        present_days = {p["from"] for p in cal["time_periods"]}
        missing_days = [d for d in ALL_WEEKDAYS if d not in present_days]
        for day in missing_days:
            cal["time_periods"].append({
                "from": day, "to": day,
                "beginTime": "00:00:00", "endTime": "00:00:00",
            })
            total_padded += 1
    if total_padded:
        print(f"  [OK] Padded {total_padded} empty weekday(s) across "
              f"{len(data['resource_calendars'])} calendar templates "
              f"(Prosimos crash workaround, per Samira's README)")
    return data


# ─────────────────────────────────────────────
# 5. MODEL CREATION
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
    # Always pad empty weekdays LAST, on every model (baseline and
    # perturbed alike), so the crash workaround is never accidentally
    # skipped and never interferes with the perturbation logic above.
    data = pad_empty_weekdays(data)
    return data


def save_model(data, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)
    print(f"  -> Saved: {filepath}")


# ─────────────────────────────────────────────
# 6. MAIN
# ─────────────────────────────────────────────

def main():
    print(f"\nLoading original JSON from:\n  {ORIGINAL_JSON}\n")
    with open(ORIGINAL_JSON, "r") as f:
        original = json.load(f)
    print("Original JSON loaded successfully.\n")

    print("── Individual Group Models (v3, quantile-based: median -> p30/p70) ──")
    print("── (RC uses DataMining-specific aggregate quantity -- see docstring) ──")
    print("── (every model, incl. baseline, gets the empty-weekday padding fix) ──\n")

    print("── Baseline (padded, unperturbed) ──")
    save_model(create_model(original, []), "model_original_datamining_v3_padded.json")

    print("\n── Model_RC_v3: Resource Calendars only ──")
    save_model(create_model(original, ["resource_calendars"]), "model_RC_datamining_v3.json")

    print("\n── Model_AD_v3: Arrival Distribution only ──")
    save_model(create_model(original, ["arrival_distribution"]), "model_AD_datamining_v3.json")

    print("\n── Model_RN_v3: Resource Numbers only ──")
    save_model(create_model(original, ["resource_numbers"]), "model_RN_datamining_v3.json")

    print("\n── Model_TR_v3: Tasks & Resources only ──")
    save_model(create_model(original, ["tasks_resources"]), "model_TR_datamining_v3.json")

    print("\n── Model_AC_v3: Arrival Calendar only ──")
    save_model(create_model(original, ["arrival_calendar"]), "model_AC_datamining_v3.json")

    print("\n" + "=" * 60)
    print("All DataMining 'v3' (quantile-based) models created successfully!")
    print("NOTE: use model_original_datamining_v3_padded.json as the")
    print("'original' baseline in run_simulations_datamining_v3.py, NOT")
    print("the raw ConsultaDataMining201618_train.json -- the raw file")
    print("still has the empty-weekday issue and will likely crash Prosimos.")
    print("=" * 60)


if __name__ == "__main__":
    main()
