"""
Base abstract class for process simulators.

Provides a common interface for integrating different simulators
(Prosimos, Scylla, etc.) into the sensitivity-analysis pipeline.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List


class BaseSimulator(ABC):
    """
    Abstract base class for process simulators.

    All simulator implementations must inherit from this class and
    implement the required methods.
    """

    @abstractmethod
    def simulate(
        self,
        bpmn_path: str,
        json_path: str,
        total_cases: int,
        starting_at: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run a single simulation and return structured KPI results.

        Parameters
        ----------
        bpmn_path : str
            Path to the BPMN model file.
        json_path : str
            Path to the JSON configuration file with sampled parameters.
        total_cases : int
            Number of process instances to simulate.
        starting_at : str
            ISO timestamp for simulation start.
        **kwargs
            Additional simulator-specific arguments.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing:
            {
                "process_rows": list[dict],  # process-level KPIs
                "task_rows": list[dict],     # task-level KPIs
                "resource_rows": list[dict], # resource-level KPIs
                "case_rows": list[dict],     # individual case data
                "error": str | None,         # error message if any
            }

            Each row dict must follow the schema expected by the
            sensitivity-analysis pipeline (see prosimos_simulator.py
            for reference).
        """
        pass

    @abstractmethod
    def validate(self) -> bool:
        """
        Validate that the simulator is properly configured and dependencies
        are available.

        Returns
        -------
        bool
            True if the simulator is ready to use, False otherwise.

        Raises
        ------
        ImportError
            If required dependencies are missing.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return a human-readable simulator name."""
        pass


def kpi_to_dict(kpi) -> dict:
    """
    Convert a KPI-like object into a plain dictionary.

    Safely reads KPI attributes and returns None when missing.

    Parameters
    ----------
    kpi : object
        Object that may expose attributes: min, max, avg, total, count.

    Returns
    -------
    dict
        {"min", "max", "avg", "total", "count"} with values or None.
    """
    return {
        "min": getattr(kpi, "min", None),
        "max": getattr(kpi, "max", None),
        "avg": getattr(kpi, "avg", None),
        "total": getattr(kpi, "total", None),
        "count": getattr(kpi, "count", None),
    }
