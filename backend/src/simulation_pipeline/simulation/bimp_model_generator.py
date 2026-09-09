"""Create a QBP (BIMP) simulation-parameter-annotated BPMN file from sampled JSON config.

BIMP (https://bimp.cs.ut.ee/) is driven by the open-source `qbp-simulator-engine.jar`
(QBP = "Qualified Business Process"). Unlike Scylla, which reads a separate
simulation-model XML file, BIMP/QBP expects the simulation parameters to be
embedded directly inside the BPMN file as a <qbp:processSimulationInfo>
extension element (namespace http://www.qbp-simulator.com/Schema201212).

This module converts this project's Prosimos-style sampled JSON configuration
(the same format used by ProsimosSimulator / ScyllaModelGeneratorV2) into that
QBP XML block and writes out a new, annotated BPMN file that can be fed
directly to qbp-simulator-engine.jar.
"""

import json
import math
import xml.etree.ElementTree as ET
from datetime import time
from typing import Any, Dict, List, Tuple

QBP_NAMESPACE = "http://www.qbp-simulator.com/Schema201212"
ET.register_namespace("qbp", QBP_NAMESPACE)


def _tag(name: str) -> str:
    return f"{{{QBP_NAMESPACE}}}{name}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


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


_DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def _calendar_periods(calendar: Any) -> List[Dict[str, str]]:
    periods = calendar.get("time_periods", []) if isinstance(calendar, dict) else calendar
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


def _to_qbp_distribution(distribution: Dict[str, Any]) -> Tuple[str, Dict[str, float]]:
    """Map a sampled distribution dict to a QBP distribution (type, mean/arg1/arg2).

    This project's `distribution_params` convention (as produced by the
    sampling/conversion pipeline) already stores values in the QBP-native
    mean/variance/min/max representation (all in seconds), not scipy's
    loc/scale convention:
      - fix:     [value]
      - expon:   [mean, min, max]
      - uniform: [min, max]
      - norm:    [mean, std_dev, min, max]
      - gamma:   [mean, variance, min, max]
      - lognorm: [mean, variance, min, max]
      - triang:  [mode, min, max]
    QBP does not support the min/max truncation bounds directly on
    NORMAL/GAMMA/LOGNORMAL distributions, so they are dropped here.
    """
    name = str(distribution.get("distribution_name", "")).lower()
    params = _distribution_values(distribution)

    def p(i: int, default: float = 0.0) -> float:
        return params[i] if i < len(params) else default

    if name in ("fix", "fixed", "constant"):
        return "FIXED", {"mean": p(0), "arg1": 0.0, "arg2": 0.0}
    if name in ("expon", "exponential"):
        mean = p(0)
        return "EXPONENTIAL", {"mean": mean, "arg1": mean, "arg2": 0.0}
    if name in ("uniform", "uni"):
        lo, hi = p(0), p(1)
        return "UNIFORM", {"mean": 0.0, "arg1": min(lo, hi), "arg2": max(lo, hi)}
    if name in ("norm", "normal"):
        mean, std_dev = p(0), p(1)
        return "NORMAL", {"mean": mean, "arg1": max(std_dev, 0.0), "arg2": 0.0}
    if name == "gamma":
        mean, variance = p(0), p(1)
        return "GAMMA", {"mean": mean, "arg1": max(variance, 0.0), "arg2": 0.0}
    if name == "lognorm":
        mean, variance = p(0), p(1)
        return "LOGNORMAL", {"mean": mean, "arg1": max(variance, 0.0), "arg2": 0.0}
    if name == "triang":
        mode, lo, hi = p(0), p(1), p(2)
        return "TRIANGULAR", {"mean": mode, "arg1": min(lo, hi), "arg2": max(lo, hi)}

    # Unknown distribution: fall back to a constant using the first param
    # (or a 60s default) rather than failing the whole simulation.
    return "FIXED", {"mean": p(0, 60.0), "arg1": 0.0, "arg2": 0.0}


def _add_distribution_element(parent: ET.Element, tag_name: str, distribution: Dict[str, Any]) -> ET.Element:
    dist_type, values = _to_qbp_distribution(distribution if isinstance(distribution, dict) else {})
    element = ET.SubElement(parent, _tag(tag_name), {
        "type": dist_type,
        "mean": str(max(values["mean"], 0.0)),
        "arg1": str(max(values["arg1"], 0.0)),
        "arg2": str(max(values["arg2"], 0.0)),
    })
    ET.SubElement(element, _tag("timeUnit")).text = "seconds"
    return element


def _local_name_matches(element: ET.Element, *names: str) -> bool:
    return _local_name(element.tag) in names


def _load_bpmn(bpmn_path: str) -> Tuple[ET.ElementTree, ET.Element, str, List[Tuple[str, str]], List[str], List[str]]:
    tree = ET.parse(bpmn_path)
    root = tree.getroot()
    process = next((el for el in root.iter() if _local_name(el.tag) == "process"), None)
    if process is None or not process.get("id"):
        raise ValueError("BPMN model does not contain a process id.")

    tasks = [
        (el.get("id"), el.get("name") or el.get("id"))
        for el in process.iter()
        if _local_name_matches(el, "task", "userTask", "serviceTask", "manualTask") and el.get("id")
    ]
    start_events = [
        el.get("id") for el in process.iter()
        if _local_name(el.tag) == "startEvent" and el.get("id")
    ]
    sequence_flow_ids = [
        el.get("id") for el in process.iter()
        if _local_name(el.tag) == "sequenceFlow" and el.get("id")
    ]
    return tree, root, process.get("id"), tasks, start_events, sequence_flow_ids


def _resource_definitions(config: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    """Return (resource_id -> resource dict, task_id -> [resource_id, ...])."""
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


def _add_timetables(parent: ET.Element, config: Dict[str, Any]) -> Dict[str, str]:
    """Add <qbp:timetables> and return {calendar_id: timetable_id}."""
    calendars = config.get("resource_calendars", [])
    timetable_ids: Dict[str, str] = {}
    if not isinstance(calendars, list) or not calendars:
        return timetable_ids

    timetables = ET.SubElement(parent, _tag("timetables"))
    is_first = True
    for calendar in calendars:
        if not isinstance(calendar, dict):
            continue
        calendar_id = _calendar_id(calendar)
        if not calendar_id or calendar_id in timetable_ids:
            continue
        timetable_ids[calendar_id] = calendar_id
        timetable = ET.SubElement(timetables, _tag("timetable"), {
            "id": calendar_id,
            "name": calendar_id,
            "default": "true" if is_first else "false",
        })
        is_first = False
        rules = ET.SubElement(timetable, _tag("rules"))
        for period in _calendar_periods(calendar):
            if not _valid_period(period):
                continue
            ET.SubElement(rules, _tag("rule"), {
                "fromTime": str(period["beginTime"]),
                "toTime": str(period["endTime"]),
                "fromWeekDay": str(period["from"]).upper(),
                "toWeekDay": str(period.get("to", period["from"])).upper(),
            })
    return timetable_ids


def _add_resources(parent: ET.Element, resources: Dict[str, Dict[str, Any]], timetable_ids: Dict[str, str]) -> None:
    if not resources:
        return
    resources_el = ET.SubElement(parent, _tag("resources"))
    default_timetable = next(iter(timetable_ids.values()), "")
    for resource_id, resource in resources.items():
        calendar_id = str(resource.get("calendar", ""))
        timetable_id = timetable_ids.get(calendar_id, default_timetable)
        ET.SubElement(resources_el, _tag("resource"), {
            "id": resource_id,
            "name": str(resource.get("name", resource_id)),
            "totalAmount": str(max(int(_number(resource.get("amount"), 1)), 1)),
            "costPerHour": str(_number(resource.get("cost_per_hour"), 0.0)),
            "timetableId": timetable_id,
        })


def _add_elements(
    parent: ET.Element,
    tasks: List[Tuple[str, str]],
    config: Dict[str, Any],
    task_resources: Dict[str, List[str]],
) -> None:
    task_distributions = {
        str(entry.get("task_id")): entry.get("resources", [])
        for entry in config.get("task_resource_distribution", [])
        if isinstance(entry, dict) and entry.get("task_id")
    }
    elements = ET.SubElement(parent, _tag("elements"))
    for task_id, task_name in tasks:
        element = ET.SubElement(elements, _tag("element"), {"id": f"qbp_{task_id}", "elementId": task_id})
        resource_ids = task_resources.get(task_id, [])
        distributions = task_distributions.get(task_id, [])
        # QBP only supports a single duration distribution per task (no
        # per-resource differentiation): use the distribution associated
        # with the first assigned resource as a representative approximation,
        # matching the same simplification used by the Scylla adapter.
        selected: Dict[str, Any] = {}
        if distributions:
            preferred_resource = resource_ids[0] if resource_ids else None
            selected = next(
                (item for item in distributions if isinstance(item, dict) and item.get("resource_id") == preferred_resource),
                distributions[0] if isinstance(distributions[0], dict) else {},
            )
        _add_distribution_element(element, "durationDistribution", selected)

        resource_ids_el = ET.SubElement(element, _tag("resourceIds"))
        for resource_id in resource_ids:
            ET.SubElement(resource_ids_el, _tag("resourceId")).text = resource_id


def _add_sequence_flows(parent: ET.Element, config: Dict[str, Any], valid_flow_ids: set) -> None:
    gateways = config.get("gateway_branching_probabilities", [])
    if not isinstance(gateways, list) or not gateways:
        return

    sequence_flows = ET.SubElement(parent, _tag("sequenceFlows"))
    for gateway in gateways:
        if not isinstance(gateway, dict):
            continue
        for probability in gateway.get("probabilities", []):
            if not isinstance(probability, dict):
                continue
            path_id = probability.get("path_id")
            if not path_id or (valid_flow_ids and path_id not in valid_flow_ids):
                continue
            value = max(_number(probability.get("value"), 0.0), 0.0)
            ET.SubElement(sequence_flows, _tag("sequenceFlow"), {
                "elementId": str(path_id),
                "executionProbability": str(min(value, 1.0)),
            })


def json_to_bimp_bpmn(
    json_path: str,
    bpmn_path: str,
    output_bpmn_path: str,
    total_cases: int,
    starting_at: str,
    currency: str = "EUR",
) -> str:
    """Generate a QBP-annotated BPMN file ready for qbp-simulator-engine.jar.

    Parameters
    ----------
    json_path : str
        Path to the sampled JSON simulation-parameters file.
    bpmn_path : str
        Path to the base BPMN model (no simulation info yet).
    output_bpmn_path : str
        Where to write the QBP-annotated BPMN copy.
    total_cases : int
        Number of process instances BIMP should simulate.
    starting_at : str
        ISO-8601 simulation start timestamp.
    currency : str, optional
        Currency code for the QBP model (BIMP requires one), default "EUR".

    Returns
    -------
    str
        The `output_bpmn_path` that was written.
    """
    with open(json_path, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    tree, root, _process_id, tasks, start_events, sequence_flow_ids = _load_bpmn(bpmn_path)
    if not start_events:
        raise ValueError("BPMN model does not contain a start event.")

    sim_info = ET.Element(_tag("processSimulationInfo"), {
        "id": "qbp_sim_info",
        "processInstances": str(max(int(total_cases), 1)),
        "startDateTime": str(starting_at),
        "currency": currency,
    })

    timetable_ids = _add_timetables(sim_info, config)

    arrival = config.get("arrival_time_distribution", {})
    _add_distribution_element(sim_info, "arrivalRateDistribution", arrival if isinstance(arrival, dict) else {})

    resources, task_resources = _resource_definitions(config)
    _add_resources(sim_info, resources, timetable_ids)
    _add_elements(sim_info, tasks, config, task_resources)
    _add_sequence_flows(sim_info, config, set(filter(None, sequence_flow_ids)))

    root.append(sim_info)

    ET.indent(tree, space="  ")
    tree.write(output_bpmn_path, encoding="utf-8", xml_declaration=True)
    return output_bpmn_path
