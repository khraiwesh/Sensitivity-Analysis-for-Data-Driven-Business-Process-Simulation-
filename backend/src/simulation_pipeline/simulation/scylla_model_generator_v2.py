"""Create schema-conformant Scylla global and simulation configuration files."""

import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple


SCYLLA_NAMESPACE = "http://bsim.hpi.uni-potsdam.de/scylla/simModel"
ET.register_namespace("bsim", SCYLLA_NAMESPACE)


def _tag(name: str) -> str:
    return f"{{{SCYLLA_NAMESPACE}}}{name}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _write_xml(root: ET.Element, output_path: str) -> str:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path


def _number(value: Any, default: float) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _distribution_values(distribution: Dict[str, Any]) -> List[float]:
    values = distribution.get("distribution_params", [])
    if not isinstance(values, list):
        return []
    return [_number(item.get("value"), 0.0) for item in values if isinstance(item, dict)]


def _add_distribution(
    parent: ET.Element,
    distribution: Dict[str, Any],
    default_minutes: float = 5.0,
    multiplier: float = 1.0,
) -> None:
    """Add a time distribution accepted by Scylla's SimulationConfigurationParser."""
    name = str(distribution.get("distribution_name", "fix")).lower()
    # Prosimos stores fitted arrival and task-duration parameters in seconds.
    values = [value / 60.0 * multiplier for value in _distribution_values(distribution)]
    fallback = default_minutes * multiplier

    if name in {"expon", "exponential"}:
        element = ET.SubElement(parent, _tag("exponentialDistribution"))
        ET.SubElement(element, _tag("mean")).text = str(max(values[0] if values else fallback, 0.001))
    elif name in {"norm", "normal"} and len(values) >= 2:
        element = ET.SubElement(parent, _tag("normalDistribution"))
        ET.SubElement(element, _tag("mean")).text = str(max(values[0], 0.001))
        ET.SubElement(element, _tag("standardDeviation")).text = str(max(values[1], 0.001))
    elif name in {"uniform", "uni"} and len(values) >= 2:
        lower, upper = sorted(values[:2])
        element = ET.SubElement(parent, _tag("uniformDistribution"))
        ET.SubElement(element, _tag("lower")).text = str(max(lower, 0.001))
        ET.SubElement(element, _tag("upper")).text = str(max(upper, lower + 0.001))
    else:
        # Scylla's parser does not support Prosimos gamma/log-normal distributions.
        element = ET.SubElement(parent, _tag("constantDistribution"))
        ET.SubElement(element, _tag("constantValue")).text = str(max(values[0] if values else fallback, 0.001))


_DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def _calendar_periods(calendar: Dict[str, Any]) -> List[Dict[str, str]]:
    periods = calendar.get("time_periods", [])
    if not isinstance(periods, list):
        return []
    return [period for period in periods if isinstance(period, dict)]


def _calendar_id(calendar: Dict[str, Any]) -> str:
    return str(calendar.get("id") or calendar.get("name") or "")


def _valid_period(period: Dict[str, str]) -> bool:
    try:
        _DAYS.index(str(period["from"]).upper())
        _DAYS.index(str(period.get("to", period["from"])).upper())
        time.fromisoformat(str(period["beginTime"]))
        time.fromisoformat(str(period["endTime"]))
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _days_in_range(start_day: int, end_day: int) -> List[int]:
    """Days (0=MONDAY..6=SUNDAY) from start_day to end_day inclusive.

    Wraps across the end of the week when start_day > end_day
    (e.g. SATURDAY -> MONDAY covers SATURDAY, SUNDAY, MONDAY).
    """
    if start_day <= end_day:
        return list(range(start_day, end_day + 1))
    return list(range(start_day, 7)) + list(range(0, end_day + 1))


def _seconds_to_time_str(seconds: int) -> str:
    """Format a seconds-since-midnight offset as HH:MM:SS, clamped to a single day."""
    seconds = max(0, min(int(seconds), 24 * 60 * 60))
    if seconds >= 24 * 60 * 60:
        return "23:59:59"
    hh, rem = divmod(seconds, 3600)
    mm, ss = divmod(rem, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def _expand_period_to_day_intervals(period: Dict[str, str]) -> List[Tuple[int, int, int]]:
    """Expand a period into (day, begin_seconds, end_seconds) tuples.

    Handles two cases that a single from/to/beginTime/endTime entry cannot
    represent directly:
      - a day range that wraps past the end of the week (from > to, e.g.
        SATURDAY -> MONDAY), and
      - an overnight time window that crosses midnight (beginTime >= endTime,
        e.g. 22:00:00 -> 06:00:00), which spills into the next calendar day.
    """
    start_day = _DAYS.index(str(period["from"]).upper())
    end_day = _DAYS.index(str(period.get("to", period["from"])).upper())
    begin = time.fromisoformat(str(period["beginTime"]))
    end = time.fromisoformat(str(period["endTime"]))
    begin_seconds = begin.hour * 3600 + begin.minute * 60 + begin.second
    end_seconds = end.hour * 3600 + end.minute * 60 + end.second
    day_seconds = 24 * 60 * 60

    intervals: List[Tuple[int, int, int]] = []
    for day in _days_in_range(start_day, end_day):
        if begin_seconds < end_seconds:
            intervals.append((day, begin_seconds, end_seconds))
        else:
            # Overnight window: spills past midnight into the next calendar day.
            intervals.append((day, begin_seconds, day_seconds))
            intervals.append(((day + 1) % 7, 0, end_seconds))
    return intervals


def _availability_multiplier(periods: List[Dict[str, str]]) -> float:
    """Return an elapsed-time multiplier for a calendar's weekly availability."""
    weekly_seconds = 7 * 24 * 60 * 60
    intervals_by_day: Dict[int, List[Tuple[int, int]]] = {}
    for period in periods:
        if not _valid_period(period):
            continue
        for day, begin_seconds, end_seconds in _expand_period_to_day_intervals(period):
            intervals_by_day.setdefault(day, []).append((begin_seconds, end_seconds))

    open_seconds = 0
    for intervals in intervals_by_day.values():
        merged: List[Tuple[int, int]] = []
        for begin_seconds, end_seconds in sorted(intervals):
            if merged and begin_seconds <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end_seconds))
            else:
                merged.append((begin_seconds, end_seconds))
        open_seconds += sum(end_seconds - begin_seconds for begin_seconds, end_seconds in merged)

    fraction = min(open_seconds / weekly_seconds, 1.0)
    return 1.0 / fraction if fraction > 0 else 1.0


def _arrival_calendar_multiplier(config: Dict[str, Any]) -> float:
    """Approximate closed arrival hours by reducing the mean arrival rate."""
    periods = [
        period for period in config.get("arrival_time_calendar", [])
        if isinstance(period, dict)
    ]
    return _availability_multiplier(periods)


def _resource_calendar_multipliers(config: Dict[str, Any]) -> Dict[str, float]:
    calendars = config.get("resource_calendars", [])
    if not isinstance(calendars, list):
        return {}
    return {
        _calendar_id(calendar): _availability_multiplier(_calendar_periods(calendar))
        for calendar in calendars
        if isinstance(calendar, dict) and _calendar_id(calendar)
    }


def _add_resource_timetables(root: ET.Element, config: Dict[str, Any]) -> set[str]:
    calendars = config.get("resource_calendars", [])
    if not isinstance(calendars, list):
        return set()

    valid_calendars = [
        calendar for calendar in calendars
        if isinstance(calendar, dict) and _calendar_id(calendar)
    ]
    if not valid_calendars:
        return set()

    timetables = ET.SubElement(root, _tag("timetables"))
    timetable_ids = set()
    for calendar in valid_calendars:
        timetable_id = _calendar_id(calendar)
        if timetable_id in timetable_ids:
            continue
        timetable_ids.add(timetable_id)
        timetable = ET.SubElement(timetables, _tag("timetable"), {"id": timetable_id})
        for period in _calendar_periods(calendar):
            if not _valid_period(period):
                continue
            # Expand wraparound day ranges and overnight windows into simple
            # same-day, begin<end items so Scylla never has to interpret an
            # ambiguous from>to or beginTime>=endTime entry itself.
            for day, begin_seconds, end_seconds in _expand_period_to_day_intervals(period):
                if end_seconds <= begin_seconds:
                    continue
                ET.SubElement(timetable, _tag("timetableItem"), {
                    "from": _DAYS[day],
                    "to": _DAYS[day],
                    "beginTime": _seconds_to_time_str(begin_seconds),
                    "endTime": _seconds_to_time_str(end_seconds),
                })
    return timetable_ids


def _load_bpmn(bpmn_path: str) -> Tuple[str, List[Tuple[str, str]], List[str]]:
    root = ET.parse(bpmn_path).getroot()
    process = next((element for element in root.iter() if _local_name(element.tag) == "process"), None)
    if process is None or not process.get("id"):
        raise ValueError("BPMN model does not contain a process id.")

    tasks = [
        (element.get("id"), element.get("name") or element.get("id"))
        for element in process.iter()
        if _local_name(element.tag) in {"task", "userTask", "serviceTask", "manualTask"} and element.get("id")
    ]
    start_events = [
        element.get("id")
        for element in process.iter()
        if _local_name(element.tag) == "startEvent" and element.get("id")
    ]
    return process.get("id"), tasks, start_events


def _resource_definitions(config: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    """Map resource id -> resource dict, and task id -> ALL eligible resource ids.

    Mirrors bimp_model_generator.py's equivalent (Dict[str, List[str]] +
    .append()) so the full SIMOD-discovered resource pool per task is
    preserved, instead of collapsing to a single first-encountered resource.
    """
    resources: Dict[str, Dict[str, Any]] = {}
    task_resources: Dict[str, List[str]] = {}
    for profile in config.get("resource_profiles", []):
        if not isinstance(profile, dict):
            continue
        for resource in profile.get("resource_list", []):
            if not isinstance(resource, dict):
                continue
            resource_id = str(resource.get("id", ""))
            if not resource_id or resource_id == "NOT_SET":
                continue
            resources.setdefault(resource_id, resource)
            for task_id in resource.get("assignedTasks", []):
                task_resources.setdefault(str(task_id), []).append(resource_id)
    return resources, task_resources


def compute_end_date_time(starting_at: str, horizon_days: float = 365.0) -> str:
    """Compute a simulation end date `horizon_days` after `starting_at`.

    Kept as an explicit, callable helper (rather than a value baked silently
    into json_to_scylla_xml) so callers can make the simulation horizon
    configurable instead of hard-coded.
    """
    start = datetime.fromisoformat(str(starting_at))
    return (start + timedelta(days=horizon_days)).isoformat()


class ScyllaModelGeneratorV2:
    """Generate the two namespaced XML documents expected by Scylla."""

    @staticmethod
    def json_to_global_xml(json_path: str, output_xml_path: str, seed: int = 100) -> str:
        with open(json_path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)

        root = ET.Element(_tag("globalConfiguration"), {
            "id": "generatedGlobalConfiguration",
            "targetNamespace": "http://www.hpi.de",
        })
        ET.SubElement(root, _tag("randomSeed")).text = str(seed)
        ET.SubElement(root, _tag("zoneOffset")).text = "+00:00"

        resources, _ = _resource_definitions(config)
        timetable_ids = _add_resource_timetables(root, config)
        if resources:
            resource_data = ET.SubElement(root, _tag("resourceData"))
            for resource_id, resource in resources.items():
                quantity = max(int(_number(resource.get("amount"), 1)), 1)
                attributes = {
                    "id": resource_id,
                    "name": str(resource.get("name", resource_id)),
                    "defaultQuantity": str(quantity),
                    "defaultCost": str(_number(resource.get("cost_per_hour"), 0.0)),
                    "defaultTimeUnit": "HOURS",
                }
                calendar_id = str(resource.get("calendar", ""))
                if calendar_id in timetable_ids:
                    attributes["defaultTimetableId"] = calendar_id
                dynamic = ET.SubElement(resource_data, _tag("dynamicResource"), attributes)
                for index in range(quantity):
                    ET.SubElement(dynamic, _tag("instance"), {"name": f"{resource_id}_{index + 1}"})

        return _write_xml(root, output_xml_path)

    @staticmethod
    def json_to_scylla_xml(
        json_path: str,
        output_xml_path: str,
        bpmn_path: str,
        process_instances: int,
        starting_at: str,
        seed: int = 100,
        end_date_time: Optional[str] = None,
    ) -> str:
        with open(json_path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)

        process_id, tasks, start_events = _load_bpmn(bpmn_path)
        if not start_events:
            raise ValueError("BPMN model does not contain a start event.")

        root = ET.Element(_tag("definitions"), {"targetNamespace": "http://www.hpi.de"})
        simulation_attributes = {
            "id": "generatedSimulationConfiguration",
            "processRef": process_id,
            "processInstances": str(max(int(process_instances), 1)),
            "startDateTime": str(starting_at),
        }
        if end_date_time:
            simulation_attributes["endDateTime"] = str(end_date_time)
        simulation_attributes["randomSeed"] = str(seed)
        simulation = ET.SubElement(root, _tag("simulationConfiguration"), simulation_attributes)

        arrival = config.get("arrival_time_distribution", {})
        arrival_multiplier = _arrival_calendar_multiplier(config)
        for start_event_id in start_events:
            start_event = ET.SubElement(simulation, _tag("startEvent"), {"id": start_event_id})
            arrival_rate = ET.SubElement(start_event, _tag("arrivalRate"), {"timeUnit": "MINUTES"})
            _add_distribution(
                arrival_rate,
                arrival if isinstance(arrival, dict) else {},
                multiplier=arrival_multiplier,
            )

        resources, task_resources = _resource_definitions(config)
        resource_calendar_multipliers = _resource_calendar_multipliers(config)
        task_distributions = {
            str(entry.get("task_id")): entry.get("resources", [])
            for entry in config.get("task_resource_distribution", [])
            if isinstance(entry, dict) and entry.get("task_id")
        }
        for task_id, task_name in tasks:
            task = ET.SubElement(simulation, _tag("task"), {"id": task_id, "name": task_name})
            duration = ET.SubElement(task, _tag("duration"), {"timeUnit": "MINUTES"})
            eligible_resource_ids = task_resources.get(task_id, [])
            distributions = task_distributions.get(task_id, [])
            # Scylla's engine keys durations only per-task (durations:
            # Map<Integer, TimeDistributionWrapper> in the decompiled
            # SimulationConfiguration), not per-resource, so one
            # "representative" resource (the first eligible one) is used to
            # pick the duration distribution and resource-calendar
            # availability multiplier below. This is an inherent Scylla
            # format limitation, not a resource-pool bug: the full eligible
            # pool is still written to <bsim:resources> further down.
            representative_resource_id = eligible_resource_ids[0] if eligible_resource_ids else None
            selected = next(
                (item for item in distributions if isinstance(item, dict) and item.get("resource_id") == representative_resource_id),
                distributions[0] if distributions and isinstance(distributions[0], dict) else {},
            )
            calendar_id = str(resources.get(representative_resource_id, {}).get("calendar", ""))
            # The installed Scylla runtime accepts timetable XML but does not delay
            # this model's tasks for closed hours; preserve calendar availability in elapsed time.
            _add_distribution(
                duration,
                selected,
                multiplier=resource_calendar_multipliers.get(calendar_id, 1.0),
            )
            if eligible_resource_ids:
                task_resources_element = ET.SubElement(task, _tag("resources"))
                for resource_id in eligible_resource_ids:
                    ET.SubElement(task_resources_element, _tag("resource"), {"id": resource_id, "amount": "1"})

        for gateway in config.get("gateway_branching_probabilities", []):
            if not isinstance(gateway, dict) or not gateway.get("gateway_id"):
                continue
            probabilities = [
                entry for entry in gateway.get("probabilities", [])
                if isinstance(entry, dict) and entry.get("path_id")
            ]
            if not probabilities:
                continue
            gateway_element = ET.SubElement(
                simulation,
                _tag("exclusiveGateway"),
                {"id": str(gateway["gateway_id"])},
            )
            values = [max(_number(probability.get("value"), 0.0), 0.0) for probability in probabilities]
            total = sum(values)
            # Scylla rejects totals slightly above 1 due to floating-point parsing.
            # Keep the sampled branch ratios while retaining a small numeric margin.
            scale = 0.999999 / total if total > 0 else 1.0 / len(values)
            for probability, value in zip(probabilities, values):
                flow = ET.SubElement(
                    gateway_element,
                    _tag("outgoingSequenceFlow"),
                    {"id": str(probability["path_id"])},
                )
                ET.SubElement(flow, _tag("branchingProbability")).text = str(
                    min(value * scale, 1.0)
                )

        return _write_xml(root, output_xml_path)