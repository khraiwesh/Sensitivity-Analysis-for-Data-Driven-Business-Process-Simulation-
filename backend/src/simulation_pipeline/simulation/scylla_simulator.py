"""
Scylla simulator adapter (JAR-based via subprocess).

Wraps the Scylla BPMN simulator (Java JAR) to conform to the BaseSimulator interface.
Scylla is an extensible BPMN process simulator designed for sensitivity analysis.
Reference: https://github.com/bptlab/scylla
"""

from src.simulation_pipeline.simulation.base_simulator import BaseSimulator, kpi_to_dict
from typing import Dict, Any, List
import json
import subprocess
import os
from pathlib import Path
from datetime import datetime
import statistics
import shutil


class ScyllaSimulator(BaseSimulator):
    """Adapter for Scylla BPMN process simulator (JAR-based)."""

    # Scylla JAR location
    SCYLLA_JAR = r"C:\Users\Samira\Downloads\scylla\scylla.jar"

    def __init__(self):
        """Initialize the Scylla simulator."""
        self.validate()

    def validate(self) -> bool:
        """Check that Scylla JAR is installed."""
        if not os.path.exists(self.SCYLLA_JAR):
            raise FileNotFoundError(
                f"Scylla JAR not found at {self.SCYLLA_JAR}. "
                f"Download from https://github.com/bptlab/scylla/releases"
            )
        
        # Check Java is available
        result = subprocess.run(["java", "-version"], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "Java not found. Install Java 11+ from https://adoptium.net/"
            )
        return True

    @property
    def name(self) -> str:
        """Return simulator name."""
        return "Scylla (JAR)"

    def simulate(
        self,
        bpmn_path: str,
        json_path: str,
        total_cases: int,
        starting_at: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run a Scylla simulation and return structured KPI results.
        
        Full integration:
        1. Convert JSON parameters to Scylla XML config
        2. Run Scylla in headless mode with JAR (requires --sim parameter)
        3. Parse XES event logs
        4. Extract KPIs (cycle_time, processing_time, waiting_time)
        """
        import subprocess
        import tempfile
        from pathlib import Path
        from src.simulation_pipeline.simulation.xes_parser import XESParser
        from src.simulation_pipeline.simulation.scylla_model_generator_v2 import (
            ScyllaModelGeneratorV2,
            compute_end_date_time,
        )
        
        try:
            print(f"\n[SCYLLA] Starting simulation...")
            print(f"   JAR: {self.SCYLLA_JAR}")
            print(f"   BPMN: {bpmn_path}")
            print(f"   JSON Config: {json_path}")
            print(f"   Cases: {total_cases}")
            
            # Get seed from kwargs or use default
            seed = kwargs.get('seed', 100)

            # endDateTime is optional and configurable: pass it explicitly via
            # kwargs['end_date_time'], or supply kwargs['horizon_days'] to
            # derive one from starting_at (defaults to a 365-day horizon when
            # horizon_days is requested but no explicit value is given).
            end_date_time = kwargs.get('end_date_time')
            horizon_days = kwargs.get('horizon_days')
            if not end_date_time and horizon_days:
                end_date_time = compute_end_date_time(starting_at, horizon_days=horizon_days)

            
            # Create temporary directory for Scylla config and output
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir = Path(temp_dir)
                
                # Step 1: Create Scylla global configuration XML.
                config_path = temp_dir / "scylla_config.xml"
                print(f"\n[SCYLLA] Step 1: Creating Scylla XML config...")
                generator = ScyllaModelGeneratorV2()
                generator.json_to_global_xml(json_path, str(config_path), seed=seed)
                print(f"   OK Config created: {config_path.stat().st_size} bytes")
                
                # Step 1.5: Generate Scylla XML simulation model from JSON
                print(f"\n[SCYLLA] Step 1.5: Generating Scylla XML simulation model...")
                print(f"   Input JSON: {json_path}")
                
                # Use a path that persists beyond the temp directory context manager
                sim_model_xml = Path(temp_dir) / "sim_model.xml"
                sim_model_path = None
                
                try:
                    print(f"   Attempting to generate XML from JSON...")
                    result_path = generator.json_to_scylla_xml(
                        json_path,
                        str(sim_model_xml),
                        bpmn_path,
                        total_cases,
                        starting_at,
                        seed=seed,
                        end_date_time=end_date_time,
                    )
                    
                    # Verify the XML file was created
                    if sim_model_xml.exists():
                        file_size = sim_model_xml.stat().st_size
                        with open(sim_model_xml, 'r') as f:
                            first_lines = '\n'.join(f.read().split('\n')[:5])
                        print(f"   OK XML model generated: {file_size} bytes")
                        print(f"   XML path: {sim_model_xml}")
                        print(f"   XML preview (first 5 lines):")
                        for line in first_lines.split('\n'):
                            print(f"      {line}")
                        sim_model_path = str(sim_model_xml)
                    else:
                        print(f"   ERROR: File does not exist at {sim_model_xml}")
                        raise FileNotFoundError(f"XML generator reported success but file not found at {sim_model_xml}")
                        
                except Exception as e:
                    print(f"   ERROR generating XML: {type(e).__name__}: {str(e)}")
                    raise RuntimeError("Scylla simulation configuration generation failed.") from e
                
                if not sim_model_path:
                    raise RuntimeError("sim_model_path is not set after generation attempts")
                    
                print(f"   Final SIM Model path: {sim_model_path}")
                print(f"   File exists: {Path(sim_model_path).exists()}")
                print(f"   File size: {Path(sim_model_path).stat().st_size if Path(sim_model_path).exists() else 'N/A'} bytes")
                
                # Step 2: Run Scylla in headless mode
                output_dir = temp_dir / "output"
                output_dir.mkdir(exist_ok=True)
                output_prefix = f"{output_dir}{os.sep}"
                
                print(f"\n[SCYLLA] Step 2: Running Scylla JAR simulation...")
                
                # Build Scylla command with required parameters
                java_path = "C:\\Java11\\jdk-11.0.20+8-jre\\bin\\java.exe"
                scylla_cmd = [
                    java_path,
                    "-jar", self.SCYLLA_JAR,
                    "--headless",
                    f"--config={config_path}",
                    f"--bpmn={bpmn_path}",
                    f"--sim={sim_model_path}",  # REQUIRED: simulation model file
                    "--enable-bps-logging",
                    f"--output={output_prefix}",
                ]
                
                print(f"   Command: java -jar scylla.jar --headless ...")
                print(f"   --sim={sim_model_path}")
                print(f"   Sim file type: {'XML' if sim_model_path.endswith('.xml') else 'YML'}")
                
                result = subprocess.run(
                    scylla_cmd,
                    capture_output=True,
                    text=True,
                    timeout=1200  # 20 minute timeout (comfortably above the known ~900s Scylla JVM "genuine hang" bug, see backend/_scylla_hang_diag/)
                )
                
                print(f"   Return code: {result.returncode}")
                if result.stdout:
                    print(f"   Output: {result.stdout[:200]}")
                if result.returncode != 0:
                    print(f"   Error output: {result.stderr[:500]}")
                    if "XES" in result.stderr or list(output_dir.parent.glob("output_*/*.xes")):
                        print(f"   Note: Continuing to parse XES even with non-zero return...")
                    else:
                        raise RuntimeError(f"Scylla failed: {result.stderr[:500]}")
                
                # Step 3: Parse XES output
                print(f"\n[SCYLLA] Step 3: Parsing XES output...")
                
                xes_files = list(output_dir.parent.glob("output_*/*.xes"))
                if xes_files:
                    output_xes = xes_files[0]
                    print(f"   [OK] XES file found: {output_xes.stat().st_size} bytes")
                    parser = XESParser()
                    case_kpis = parser.xes_to_process_rows(str(output_xes), num_cases=total_cases)
                    print(f"   [OK] Extracted {len(case_kpis)} case KPI records from XES")
                    
                    if not case_kpis:
                        print(f"   [WARNING] XES parsed but no KPI rows extracted")
                        # Return empty but don't fail
                        return {
                            "process_rows": [],
                            "task_rows": [],
                            "resource_rows": [],
                            "case_rows": [],
                            "error": "XES parsed but no KPI data extracted",
                        }

                    process_rows = []
                    for metric in ("cycle_time", "processing_time", "waiting_time"):
                        values = [float(row[metric]) * 60.0 for row in case_kpis if row.get(metric) is not None]
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
                        {
                            "case_id": row["case_id"],
                            "cycle_time_s": float(row["cycle_time"]) * 60.0,
                        }
                        for row in case_kpis
                        if row.get("cycle_time") is not None
                    ]
                    
                    return {
                        "process_rows": process_rows,
                        "task_rows": [],
                        "resource_rows": [],
                        "case_rows": case_rows,
                        "error": None
                    }
                else:
                    raise FileNotFoundError(f"XES output not created at: {output_xes}")
        
        except subprocess.TimeoutExpired:
            error_msg = f"Scylla simulation timeout after 20 minutes"
            print(f"[SCYLLA] ERROR: {error_msg}")
            return {
                "process_rows": [],
                "task_rows": [],
                "resource_rows": [],
                "case_rows": [],
                "error": error_msg,
            }
        
        except Exception as e:
            error_msg = f"Scylla simulation error: {str(e)}"
            print(f"[SCYLLA] ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return {
                "process_rows": [],
                "task_rows": [],
                "resource_rows": [],
                "case_rows": [],
                "error": error_msg,
            }


def run_scylla_headless(
    jar_path: str,
    bpmn_path: str,
    config_path: str,
    output_dir: str,
    num_cases: int = 100,
) -> str:
    """
    Run Scylla in headless mode via subprocess.
    
    This is a helper function for future full integration.
    
    Parameters
    ----------
    jar_path : str
        Path to scylla.jar
    bpmn_path : str
        Path to BPMN model
    config_path : str
        Path to Scylla configuration (XML or YML)
    output_dir : str
        Output directory for XES logs
    num_cases : int
        Number of cases to simulate
        
    Returns
    -------
    str
        Path to generated XES file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    cmd = [
        "java",
        "-jar", jar_path,
        "--headless",
        f"--config={config_path}",
        f"--bpmn={bpmn_path}",
        f"--output={output_dir}",
    ]
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"Scylla failed with code {result.returncode}: {result.stderr}")
    
    print(f"STDOUT: {result.stdout}")
    
    # Find generated XES file
    xes_files = list(Path(output_dir).glob("*.xes"))
    if xes_files:
        return str(xes_files[0])
    else:
        raise FileNotFoundError(f"No XES file generated in {output_dir}")
