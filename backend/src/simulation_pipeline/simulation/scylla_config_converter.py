"""
Convert JSON sampled parameters to Scylla XML configuration format.

Scylla requires an XML config file that specifies simulation parameters.
This module converts our JSON parameter samples into Scylla's expected format.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any


def json_to_scylla_config(json_path: str, output_config_path: str, seed: int = 100) -> str:
    """
    Convert JSON parameter file to Scylla XML config.
    
    Parameters
    ----------
    json_path : str
        Path to JSON file with process model parameters
    output_config_path : str
        Path where Scylla XML config will be saved
    seed : int
        Random seed for Scylla simulation
        
    Returns
    -------
    str
        Path to generated config file
    """
    
    # Read JSON configuration
    with open(json_path, 'r', encoding='utf-8') as f:
        json_config = json.load(f)
    
    # Create root XML element for Scylla config
    config = ET.Element('Configuration')
    
    # Add random seed
    random_elem = ET.SubElement(config, 'Random')
    random_elem.set('seed', str(seed))
    
    # Add process model reference (Scylla expects BPMN)
    # This will be passed via command line, but we can add metadata
    metadata = ET.SubElement(config, 'Metadata')
    ET.SubElement(metadata, 'Description').text = f"Generated config from JSON with seed {seed}"
    
    # Add simulation parameters from JSON
    params_elem = ET.SubElement(config, 'SimulationParameters')
    
    # Extract parameters from JSON and add them
    if isinstance(json_config, dict):
        for key, value in json_config.items():
            if not key.startswith('_'):  # Skip internal fields
                param = ET.SubElement(params_elem, 'Parameter')
                param.set('name', key)
                param.set('value', str(value))
    
    # Add distribution parameters if present (these affect gateway probabilities, etc.)
    if 'distributions' in json_config:
        dist_elem = ET.SubElement(config, 'Distributions')
        for dist_name, dist_value in json_config['distributions'].items():
            dist = ET.SubElement(dist_elem, 'Distribution')
            dist.set('name', dist_name)
            dist.text = str(dist_value)
    
    # Add task durations if present
    if 'task_durations' in json_config:
        tasks_elem = ET.SubElement(config, 'TaskDurations')
        for task_name, duration in json_config['task_durations'].items():
            task = ET.SubElement(tasks_elem, 'Task')
            task.set('name', task_name)
            task.set('duration', str(duration))
    
    # Write XML to file
    tree = ET.ElementTree(config)
    tree.write(output_config_path, encoding='utf-8', xml_declaration=True)
    
    return output_config_path


def create_minimal_scylla_config(output_path: str, seed: int = 100) -> str:
    """
    Create a minimal Scylla configuration file.
    
    Used when JSON config is not available or needs minimal setup.
    """
    
    config = ET.Element('Configuration')
    
    random_elem = ET.SubElement(config, 'Random')
    random_elem.set('seed', str(seed))
    
    tree = ET.ElementTree(config)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    
    return output_path
