"""
Prosimos simulator adapter.

Wraps the Prosimos library to conform to the BaseSimulator interface.
"""

from prosimos.simulation_engine import run_simulation as _prosimos_run
from src.simulation_pipeline.simulation.base_simulator import BaseSimulator, kpi_to_dict
from typing import Dict, Any, List
import tempfile
import json
from pathlib import Path


class ProsimosSimulator(BaseSimulator):
    """Adapter for Prosimos process simulator."""

    def __init__(self):
        """Initialize the Prosimos simulator."""
        self.validate()

    def validate(self) -> bool:
        """Check that Prosimos is installed and importable."""
        try:
            import prosimos  # noqa: F401
            return True
        except ImportError:
            raise ImportError("Prosimos is not installed. Install with: pip install prosimos")

    @property
    def name(self) -> str:
        """Return simulator name."""
        return "Prosimos"

    def simulate(
        self,
        bpmn_path: str,
        json_path: str,
        total_cases: int,
        starting_at: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run a Prosimos simulation and return structured KPI results.

        Parameters
        ----------
        bpmn_path : str
            Path to the BPMN model.
        json_path : str
            Path to the JSON configuration with sampled parameters.
        total_cases : int
            Number of cases to simulate.
        starting_at : str
            ISO timestamp for simulation start (e.g., "2023-01-01T00:00:00+02:00").
        **kwargs
            Additional arguments (unused for Prosimos).

        Returns
        -------
        Dict[str, Any]
            Dictionary with keys: "process_rows", "task_rows",
            "resource_rows", "case_rows", "error".
        """
        try:
            # Run Prosimos
            res = _prosimos_run(
                bpmn_path=str(bpmn_path),
                json_path=str(json_path),
                total_cases=total_cases,
                starting_at=starting_at,
                stat_out_path=None,
                log_out_path=None,
            )

            # Validate return shape
            if not (
                isinstance(res, tuple)
                and len(res) == 2
                and isinstance(res[0], (list, tuple))
                and len(res[0]) >= 5
            ):
                raise RuntimeError(f"Unexpected return shape from Prosimos")

            process_kpi, task_kpi, resource_kpi, started, ended = res[0][:5]
            log_info = res[1]

            # Extract element info for task names
            bpmn_graph = getattr(getattr(log_info, "sim_setup", None), "bpmn_graph", None)
            element_info = getattr(bpmn_graph, "element_info", {}) if bpmn_graph else {}

            # -------- Process-level KPIs --------
            proc_rows = [
                {"metric": "cycle_time",           **kpi_to_dict(process_kpi.cycle_time)},
                {"metric": "processing_time",      **kpi_to_dict(process_kpi.processing_time)},
                {"metric": "waiting_time",         **kpi_to_dict(process_kpi.waiting_time)},
                {"metric": "idle_cycle_time",      **kpi_to_dict(process_kpi.idle_cycle_time)},
                {"metric": "idle_processing_time", **kpi_to_dict(process_kpi.idle_processing_time)},
                {"metric": "idle_time",            **kpi_to_dict(process_kpi.idle_time)},
            ]

            # -------- Task-level KPIs --------
            task_rows: List[Dict[str, Any]] = []
            for task_id, kmap in task_kpi.items():
                task_name = None
                if element_info and task_id in element_info:
                    try:
                        task_name = element_info[task_id].name
                    except Exception:
                        pass

                task_rows.append(
                    {
                        "task_id": task_id,
                        "task_name": task_name,
                        "count": getattr(getattr(kmap, "cycle_time", None), "count", None),
                        "duration_min":   getattr(getattr(kmap, "duration", None), "min", None),
                        "duration_max":   getattr(getattr(kmap, "duration", None), "max", None),
                        "duration_avg":   getattr(getattr(kmap, "duration", None), "avg", None),
                        "duration_total": getattr(getattr(kmap, "duration", None), "total", None),
                        "waiting_min":    getattr(getattr(kmap, "waiting_time", None), "min", None),
                        "waiting_max":    getattr(getattr(kmap, "waiting_time", None), "max", None),
                        "waiting_avg":    getattr(getattr(kmap, "waiting_time", None), "avg", None),
                        "waiting_total":  getattr(getattr(kmap, "waiting_time", None), "total", None),
                        "processing_min":   getattr(getattr(kmap, "processing_time", None), "min", None),
                        "processing_max":   getattr(getattr(kmap, "processing_time", None), "max", None),
                        "processing_avg":   getattr(getattr(kmap, "processing_time", None), "avg", None),
                        "processing_total": getattr(getattr(kmap, "processing_time", None), "total", None),
                        "cycle_min":      getattr(getattr(kmap, "cycle_time", None), "min", None),
                        "cycle_max":      getattr(getattr(kmap, "cycle_time", None), "max", None),
                        "cycle_avg":      getattr(getattr(kmap, "cycle_time", None), "avg", None),
                        "cycle_total":    getattr(getattr(kmap, "cycle_time", None), "total", None),
                        "idle_min":       getattr(getattr(kmap, "idle_time", None), "min", None),
                        "idle_max":       getattr(getattr(kmap, "idle_time", None), "max", None),
                        "idle_avg":       getattr(getattr(kmap, "idle_time", None), "avg", None),
                        "idle_total":     getattr(getattr(kmap, "idle_time", None), "total", None),
                        "idle_cycle_min":    getattr(getattr(kmap, "idle_cycle_time", None), "min", None),
                        "idle_cycle_max":    getattr(getattr(kmap, "idle_cycle_time", None), "max", None),
                        "idle_cycle_avg":    getattr(getattr(kmap, "idle_cycle_time", None), "avg", None),
                        "idle_cycle_total":  getattr(getattr(kmap, "idle_cycle_time", None), "total", None),
                        "idle_proc_min":     getattr(getattr(kmap, "idle_processing_time", None), "min", None),
                        "idle_proc_max":     getattr(getattr(kmap, "idle_processing_time", None), "max", None),
                        "idle_proc_avg":     getattr(getattr(kmap, "idle_processing_time", None), "avg", None),
                        "idle_proc_total":   getattr(getattr(kmap, "idle_processing_time", None), "total", None),
                        "cost_min":       getattr(getattr(kmap, "cost", None), "min", None),
                        "cost_max":       getattr(getattr(kmap, "cost", None), "max", None),
                        "cost_avg":       getattr(getattr(kmap, "cost", None), "avg", None),
                        "cost_total":     getattr(getattr(kmap, "cost", None), "total", None),
                    }
                )

            # -------- Resource-level KPIs --------
            resource_rows: List[Dict[str, Any]] = []
            for rid, rinfo in resource_kpi.items():
                resource_rows.append(
                    {
                        "resource_id": rid,
                        "resource_name": getattr(
                            getattr(rinfo, "r_profile", None), "resource_name", None
                        ),
                        "tasks_allocated": getattr(rinfo, "task_allocated", None),
                        "worked_time_s": getattr(rinfo, "worked_time", None),
                        "available_time_s": getattr(rinfo, "available_time", None),
                        "utilization": getattr(rinfo, "utilization", None),
                    }
                )

            # -------- Case-level data --------
            case_rows: List[Dict[str, Any]] = []
            for tr in getattr(log_info, "trace_list", []):
                try:
                    dur_s = (tr.completed_at - tr.started_at).total_seconds()
                except Exception:
                    dur_s = None
                case_rows.append(
                    {
                        "case_id": getattr(tr, "p_case", None),
                        "started_at": getattr(tr, "started_at", None),
                        "completed_at": getattr(tr, "completed_at", None),
                        "cycle_time_s": dur_s,
                    }
                )

            return {
                "process_rows": proc_rows,
                "task_rows": task_rows,
                "resource_rows": resource_rows,
                "case_rows": case_rows,
                "error": None,
            }

        except Exception as e:
            return {
                "process_rows": [],
                "task_rows": [],
                "resource_rows": [],
                "case_rows": [],
                "error": str(e),
            }
