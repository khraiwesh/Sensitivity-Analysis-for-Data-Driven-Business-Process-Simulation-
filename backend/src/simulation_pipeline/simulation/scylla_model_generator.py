"""
Generate Scylla XML simulation model from JSON parameters
"""
import json
from pathlib import Path
from typing import Dict, Any


class ScyllaModelGenerator:
    """Generate Scylla XML simulation models from JSON configuration"""
    
    @staticmethod
    def json_to_scylla_xml(json_path: str, output_xml_path: str, seed: int = 100) -> str:
        """
        Convert sensitivity analysis JSON parameters to Scylla XML simulation model
        
        Args:
            json_path: Path to JSON file with sensitivity parameters
            output_xml_path: Path to output XML file
            seed: Random seed
            
        Returns:
            Path to generated XML file
        """
        try:
            with open(json_path, 'r') as f:
                json_data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load JSON: {e}")
            return ScyllaModelGenerator.create_minimal_model(output_xml_path, seed)
        
        # Build Scylla XML simulation model with proper structure
        # Reference: https://github.com/bptlab/scylla/wiki
        xml_lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<SimulationModel>',
            f'  <Random seed="{seed}" />',
            '',
            '  <!-- Global Simulation Configuration -->',
            '  <GlobalConfiguration>',
            '    <Seed>{}</Seed>'.format(seed),
            '    <LogFilePath>simulation.xes</LogFilePath>',
            '  </GlobalConfiguration>',
            '',
            '  <!-- Simulation Configuration -->',
            '  <SimulationConfiguration>',
            '    <StartTime>2020-01-01 00:00:00</StartTime>',
            '    <EndTime>2020-12-31 23:59:59</EndTime>',
            '    <Currency>EUR</Currency>',
            '  </SimulationConfiguration>',
            '',
        ]
        
        # Extract task names from task_resource_distribution (most reliable source)
        task_names = []
        if isinstance(json_data, dict) and 'task_resource_distribution' in json_data:
            for task_entry in json_data.get('task_resource_distribution', []):
                if isinstance(task_entry, dict) and 'task_id' in task_entry:
                    task_names.append(task_entry['task_id'])
        
        # If still no tasks, try process model
        if not task_names and isinstance(json_data, dict) and 'process_model' in json_data:
            process_model = json_data['process_model']
            if isinstance(process_model, dict):
                for key, value in process_model.items():
                    if isinstance(value, dict) and value.get('element_type') == 'task':
                        task_names.append(key)
        
        # Add resource definitions
        xml_lines.append('  <!-- Resources -->')
        xml_lines.append('  <Resources>')
        
        # Extract resources from resource_profiles
        resources_added = set()
        if isinstance(json_data, dict) and 'resource_profiles' in json_data:
            profiles = json_data.get('resource_profiles', [])
            if isinstance(profiles, list):
                for profile in profiles:
                    if isinstance(profile, dict):
                        profile_name = profile.get('name', profile.get('id', ''))
                        if profile_name and profile_name not in resources_added:
                            xml_lines.append(f'    <Resource id="{profile_name}" name="{profile_name}">')
                            xml_lines.append('      <Role>Worker</Role>')
                            xml_lines.append('      <CostPerHour>20</CostPerHour>')
                            xml_lines.append('    </Resource>')
                            resources_added.add(profile_name)
                        
                        # Also add individual resources from resource_list
                        resource_list = profile.get('resource_list', [])
                        if isinstance(resource_list, list):
                            for resource in resource_list:
                                if isinstance(resource, dict):
                                    res_id = resource.get('id', resource.get('name', ''))
                                    res_name = resource.get('name', res_id)
                                    cost = resource.get('cost_per_hour', 20)
                                    
                                    if res_id and res_id not in resources_added:
                                        xml_lines.append(f'    <Resource id="{res_id}" name="{res_name}">')
                                        xml_lines.append('      <Role>Worker</Role>')
                                        xml_lines.append(f'      <CostPerHour>{cost}</CostPerHour>')
                                        xml_lines.append('    </Resource>')
                                        resources_added.add(res_id)
        
        xml_lines.append('  </Resources>')
        xml_lines.append('')
        
        # Add task definitions
        xml_lines.append('  <!-- Tasks -->')
        xml_lines.append('  <Tasks>')
        
        for task_id in task_names[:10]:  # Limit to first 10 for safety
            xml_lines.append(f'    <Task id="{task_id}" name="{task_id}">')
            xml_lines.append('      <InstanceDuration>')
            xml_lines.append('        <Duration>PT5M</Duration>')  # Default 5 minutes per task
            xml_lines.append('        <DistributionType>EXPONENTIAL</DistributionType>')
            xml_lines.append('        <Mean>300000</Mean>')  # 5 minutes in milliseconds
            xml_lines.append('      </InstanceDuration>')
            
            # Add resource assignments if available
            if 'task_resource_distribution' in json_data:
                for task_res in json_data['task_resource_distribution']:
                    if isinstance(task_res, dict) and task_res.get('task_id') == task_id:
                        resources = task_res.get('resources', [])
                        if resources:
                            xml_lines.append('      <ResourceAssignments>')
                            for resource in resources[:1]:  # Assign primary resource
                                xml_lines.append(f'        <Resource id="{resource}" />')
                            xml_lines.append('      </ResourceAssignments>')
                        break
            
            xml_lines.append('    </Task>')
        
        xml_lines.append('  </Tasks>')
        xml_lines.append('')
        
        # Add gateway probabilities
        if isinstance(json_data, dict) and 'gateway_branching_probabilities' in json_data:
            xml_lines.append('  <!-- Gateway Probabilities -->')
            xml_lines.append('  <GatewayProbabilities>')
            for gateway in json_data['gateway_branching_probabilities']:
                gateway_id = gateway.get('gateway_id', '')
                probabilities = gateway.get('probabilities', [])
                if gateway_id and probabilities:
                    xml_lines.append(f'    <Gateway id="{gateway_id}">')
                    for prob in probabilities:
                        path_id = prob.get('path_id', '')
                        value = prob.get('value', 0)
                        if path_id:
                            xml_lines.append(f'      <Path id="{path_id}" probability="{value}" />')
                    xml_lines.append('    </Gateway>')
            xml_lines.append('  </GatewayProbabilities>')
            xml_lines.append('')
        
        # Add arrival distribution
        if isinstance(json_data, dict) and 'arrival_time_distribution' in json_data:
            arrival_dist = json_data['arrival_time_distribution']
            xml_lines.append('  <!-- Arrival Distribution -->')
            xml_lines.append('  <ArrivalDistribution>')
            if isinstance(arrival_dist, dict):
                dist_type = arrival_dist.get('type', 'exponential').upper()
                if dist_type == 'EXPONENTIAL':
                    mean_seconds = arrival_dist.get('mean_seconds', 300)
                    xml_lines.append(f'    <DistributionType>EXPONENTIAL</DistributionType>')
                    xml_lines.append(f'    <Mean>{mean_seconds * 1000}</Mean>')  # Convert to milliseconds
            xml_lines.append('  </ArrivalDistribution>')
        
        xml_lines.append('')
        xml_lines.append('</SimulationModel>')
        
        # Write XML file
        xml_content = '\n'.join(xml_lines)
        with open(output_xml_path, 'w') as f:
            f.write(xml_content)
        
        print(f"[OK] Scylla XML model generated: {len(xml_content)} bytes")
        print(f"     Tasks: {len(task_names)} | Resources: {len(resources_added)}")
        return output_xml_path
    
    @staticmethod
    def create_minimal_model(output_path: str, seed: int = 100) -> str:
        """Create minimal Scylla XML model with just seed"""
        xml_content = f'''<?xml version="1.0" encoding="utf-8"?>
<SimulationModel>
  <Random seed="{seed}" />
  <SimulationConfiguration>
    <StartTime>2020-01-01 00:00:00</StartTime>
    <EndTime>2020-12-31 23:59:59</EndTime>
  </SimulationConfiguration>
</SimulationModel>'''
        
        with open(output_path, 'w') as f:
            f.write(xml_content)
        
        return output_path


if __name__ == '__main__':
    # Test
    import tempfile
    json_file = r'c:\Users\Samira\OneDrive - GJU\Desktop\PhD Progress -Submissions\Sensitivity Analysis\bps_sensitivity_analysis\example_sensitivity_analysis_inputs\BPIC_2012\BPIC_2012_train.json'
    
    with tempfile.TemporaryDirectory() as tmpdir:
        xml_out = Path(tmpdir) / 'sim_model.xml'
        ScyllaModelGenerator.json_to_scylla_xml(json_file, str(xml_out), seed=100)
        print(f"\nGenerated: {xml_out}")
        print(f"Content:\n{open(xml_out).read()}")
