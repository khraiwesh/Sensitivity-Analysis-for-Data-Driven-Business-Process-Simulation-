"""
BIMP simulator adapter (JAR-based via subprocess).

Wraps the open-source BIMP/QBP simulation engine (qbp-simulator-engine.jar)
to conform to the BaseSimulator interface. BIMP is the engine behind the
bimp.cs.ut.ee web tool; here we drive the underlying JAR directly (no web
scraping / no public API involved).

Reference: https://github.com/AutomatedProcessImprovement/Prosimos
           (bimp_simulation_engine/qbp-simulator-engine.jar)
"""

from src.simulation_pipeline.simulation.base_simulator import BaseSimulator
from typing import Dict, Any
from pathlib import Path
import subprocess
import os
import re
import csv
import statistics
from datetime import datetime

# Repo-bundled copy, present after cloning on any OS.
_REPO_BIMP_JAR = Path(__file__).resolve().parents[4] / "backend" / "bimp_engine" / "qbp-simulator-engine.jar"

# BIMP/QBP engine hard-codes a maximum simulated cycle time of 1095 days
# (3 years) per case. When the sampled scenario's queue backlog projects a
# case cycle time beyond that horizon, the engine throws
# BPSimulatorException("Maximum allowed cycle time exceeded, maximum is 1095 days")
# and exits WITHOUT writing the CSV (often with returncode 0, since the
# Java Runner catches the exception itself before exiting). This is a fast,
# deterministic validation failure - not a hang/timeout/crash - so it is
# detected and labeled explicitly rather than being confused with one.
MAX_CYCLE_TIME_MARKER = "Maximum allowed cycle time exceeded"


def _parse_timestamp(value: str):
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _extract_bimp_error(stdout: str, stderr: str) -> str:
    """
    Build a clear, labeled error message from BIMP's captured stdout/stderr.

    BIMP's log interleaves diagnostic node/gateway traces with the actual
    failure cause, and the meaningful message is not necessarily near the
    start of stdout - naively truncating stdout[:500] (the previous
    behavior) could silently cut off the real cause. This searches the full
    combined output for known BIMP engine exception markers first, falling
    back to the END (not the start) of the output, since BIMP writes
    progress/trace info first and any real error message last.
    """
    combined = f"{stdout or ''}\n{stderr or ''}"

    if MAX_CYCLE_TIME_MARKER in combined:
        match = re.search(r"Simulation exception:\s*(.+)", combined)
        detail = match.group(1).strip() if match else f"{MAX_CYCLE_TIME_MARKER}, maximum is 1095 days"
        return (
            "BIMP_MAX_CYCLE_TIME_EXCEEDED: BIMP aborted because at least one case's "
            f"simulated cycle time exceeded its hard-coded 1095-day (3-year) simulation "
            f"horizon limit ({detail}). This indicates queue backlog/overload for the "
            "sampled configuration (e.g. insufficient resource-calendar availability "
            "relative to the arrival rate) - it is a fast, deterministic engine "
            "validation failure, NOT a crash, hang, or timeout."
        )

    match = re.search(r"Simulation exception:\s*(.+)", combined)
    if match:
        return f"BIMP_SIMULATION_EXCEPTION: {match.group(1).strip()}"

    tail = combined.strip()[-1000:]
    return f"BIMP simulation failed: {tail}" if tail else "BIMP simulation failed: unknown error (empty stdout/stderr)"


class BimpSimulator(BaseSimulator):
    """Adapter for the BIMP/QBP BPMN process simulator (JAR-based)."""

    # BIMP/QBP simulator engine JAR location: repo-bundled copy by default
    # (works on any OS after cloning), overridable via BIMP_JAR_PATH env var.
    BIMP_JAR = os.environ.get("BIMP_JAR_PATH", str(_REPO_BIMP_JAR))

    # BIMP's JAR needs javax.xml.bind (JAXB), removed from the JDK in Java 9+
    # and fully gone in 11/17/21. Default to "java" on PATH, but allow
    # pointing at a Java 8 install without touching the system default.
    BIMP_JAVA = os.environ.get("BIMP_JAVA_PATH", "java")

    def __init__(self):
        """Initialize the BIMP simulator."""
        self.validate()

    def validate(self) -> bool:
        """Check that the BIMP JAR is installed and Java is available."""
        if not os.path.exists(self.BIMP_JAR):
            raise FileNotFoundError(
                f"BIMP JAR not found at {self.BIMP_JAR}. "
                f"Download qbp-simulator-engine.jar from "
                f"https://github.com/AutomatedProcessImprovement/Prosimos/tree/main/bimp_simulation_engine"
            )

        result = subprocess.run([self.BIMP_JAVA, "-version"], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Java not found at '{self.BIMP_JAVA}'. Install Java 8 and set BIMP_JAVA_PATH, "
                f"or install Java from https://adoptium.net/"
            )
        return True

    @property
    def name(self) -> str:
        """Return simulator name."""
        return "BIMP (QBP)"

    def simulate(
        self,
        bpmn_path: str,
        json_path: str,
        total_cases: int,
        starting_at: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run a BIMP simulation and return structured KPI results.

        1. Embed sampled JSON parameters into a QBP-annotated BPMN copy.
        2. Run qbp-simulator-engine.jar with `-csv <file>` (writes a
           per-activity event log: caseid, task, start_timestamp,
           end_timestamp, resource).
        3. Aggregate the event log into per-case cycle/processing/waiting
           times, then summarize into process_rows / case_rows.
        """
        import tempfile
        from pathlib import Path
        from src.simulation_pipeline.simulation.bimp_model_generator import json_to_bimp_bpmn

        try:
            print(f"\n[BIMP] Starting simulation...")
            print(f"   JAR: {self.BIMP_JAR}")
            print(f"   BPMN: {bpmn_path}")
            print(f"   JSON Config: {json_path}")
            print(f"   Cases: {total_cases}")

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir = Path(temp_dir)

                # Step 1: Generate QBP-annotated BPMN (simulation info embedded)
                annotated_bpmn = temp_dir / "bimp_model.bpmn"
                print(f"\n[BIMP] Step 1: Generating QBP-annotated BPMN...")
                json_to_bimp_bpmn(
                    json_path,
                    bpmn_path,
                    str(annotated_bpmn),
                    total_cases=total_cases,
                    starting_at=starting_at,
                )
                print(f"   OK Annotated BPMN created: {annotated_bpmn.stat().st_size} bytes")

                # Step 2: Run BIMP JAR with -csv output
                stats_csv = temp_dir / "bimp_stats.csv"
                print(f"\n[BIMP] Step 2: Running BIMP JAR simulation...")

                bimp_cmd = [
                    self.BIMP_JAVA, "-jar", self.BIMP_JAR,
                    str(annotated_bpmn), "-csv", str(stats_csv),
                ]
                result = subprocess.run(
                    bimp_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )

                print(f"   Return code: {result.returncode}")
                if result.returncode != 0 or not stats_csv.exists():
                    error_detail = _extract_bimp_error(result.stdout, result.stderr)
                    print(f"[BIMP] ERROR detail: {error_detail}")
                    raise RuntimeError(error_detail)

                # Step 3: Parse the per-activity event log CSV
                print(f"\n[BIMP] Step 3: Parsing BIMP CSV output...")
                case_events: Dict[str, list] = {}
                with open(stats_csv, "r", encoding="utf-8", newline="") as csv_file:
                    reader = csv.DictReader(csv_file)
                    for row in reader:
                        case_id = row.get("caseid")
                        start = _parse_timestamp(row.get("start_timestamp", ""))
                        end = _parse_timestamp(row.get("end_timestamp", ""))
                        if case_id is None or start is None or end is None:
                            continue
                        case_events.setdefault(case_id, []).append((start, end))

                if not case_events:
                    return {
                        "process_rows": [],
                        "task_rows": [],
                        "resource_rows": [],
                        "case_rows": [],
                        "error": "BIMP CSV parsed but no case events extracted",
                    }

                case_kpis = []
                for case_id, events in case_events.items():
                    case_start = min(ev[0] for ev in events)
                    case_end = max(ev[1] for ev in events)
                    cycle_time = max((case_end - case_start).total_seconds(), 0.0)
                    processing_time = min(
                        sum(max((ev[1] - ev[0]).total_seconds(), 0.0) for ev in events),
                        cycle_time,
                    )
                    waiting_time = max(cycle_time - processing_time, 0.0)
                    case_kpis.append({
                        "case_id": case_id,
                        "cycle_time": cycle_time,
                        "processing_time": processing_time,
                        "waiting_time": waiting_time,
                    })

                print(f"   OK Extracted {len(case_kpis)} case KPI records")

                process_rows = []
                for metric in ("cycle_time", "processing_time", "waiting_time"):
                    values = [row[metric] for row in case_kpis]
                    if values:
                        process_rows.append({
                            "metric": metric,
                            "min": min(values),
                            "max": max(values),
                            "avg": statistics.mean(values),
                            "total": sum(values),
                            "count": len(values),
                        })

                case_rows = [
                    {"case_id": row["case_id"], "cycle_time_s": row["cycle_time"]}
                    for row in case_kpis
                ]

                return {
                    "process_rows": process_rows,
                    "task_rows": [],
                    "resource_rows": [],
                    "case_rows": case_rows,
                    "error": None,
                }

        except subprocess.TimeoutExpired:
            error_msg = "BIMP simulation timeout after 5 minutes"
            print(f"[BIMP] ERROR: {error_msg}")
            return {
                "process_rows": [],
                "task_rows": [],
                "resource_rows": [],
                "case_rows": [],
                "error": error_msg,
            }

        except Exception as e:
            error_msg = f"BIMP simulation error: {str(e)}"
            print(f"[BIMP] ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return {
                "process_rows": [],
                "task_rows": [],
                "resource_rows": [],
                "case_rows": [],
                "error": error_msg,
            }
