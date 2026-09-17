# Sensitivity Analysis for Data-Driven Business Process Simulation

This repository contains the implementation and experimental artifacts for applying global sensitivity analysis to data-driven Business Process Simulation (BPS) models.

The tool integrates model discovery, parameter sampling and conversion, process simulation, sensitivity analysis, and visualization into a unified workflow. It supports both **Sobol** and **Morris** sensitivity analysis and enables analysis at the parameter-group and individual-parameter levels.

The repository also contains the scripts, configurations, and processed results used for the experiments reported in the accompanying paper.

---

## Installation

There are two ways to install and run the BPS Sensitivity Analysis Tool:

1. **Docker installation (recommended)**
2. **Local installation**

---

## Option 1: Docker Installation

### Option 1A: Using Pre-built Docker Images

#### Prerequisites

* Docker Desktop installed and running

#### Steps

1. Clone the repository:

```bash
git clone https://github.com/khraiwesh/Sensitivity-Analysis-for-Data-Driven-Business-Process-Simulation-.git
cd Sensitivity-Analysis-for-Data-Driven-Business-Process-Simulation-
```

2. Navigate to the pre-built Docker configuration:

```bash
cd docker_prebuilt
```

3. Pull the Docker images:

```bash
docker pull eksicek/bps_sensitivity_analysis_backend_image_final:latest
docker pull eksicek/bps_sensitivity_analysis_frontend_image_final:latest
```

4. Start the containers:

```bash
docker compose -f docker-compose.bind.yml --env-file .env up -d
```

5. Access the application:

* Frontend: `http://localhost:5173`
* Backend API: `http://localhost:5000`

Generated outputs are stored under:

```text
docker_prebuilt/output/
```

---

### Option 1B: Building Docker Images from Source

#### Prerequisites

* Docker Desktop installed and running
* Docker Hub account only if you intend to publish the built images

#### Steps

1. Clone the repository:

```bash
git clone https://github.com/khraiwesh/Sensitivity-Analysis-for-Data-Driven-Business-Process-Simulation-.git
cd Sensitivity-Analysis-for-Data-Driven-Business-Process-Simulation-
```

2. Navigate to the Docker build configuration:

```bash
cd docker_build
```

3. Build and start the containers:

```bash
docker compose -f docker-compose.yml --env-file .env up -d --build
```

4. Access the application:

* Frontend: `http://localhost:5173`
* Backend API: `http://localhost:5000`

Generated outputs are stored under:

```text
docker_build/output/
```

### Publishing Docker Images (Optional)

If you want to publish locally built images to Docker Hub:

```bash
docker login
```

Tag the images using your Docker Hub username:

```bash
docker tag bps_sensitivity_analysis_backend_image_final:latest <dockerhub_username>/bps_sensitivity_analysis_backend_image_final:latest
docker tag bps_sensitivity_analysis_frontend_image_final:latest <dockerhub_username>/bps_sensitivity_analysis_frontend_image_final:latest
```

Then push the images:

```bash
docker push <dockerhub_username>/bps_sensitivity_analysis_backend_image_final:latest
docker push <dockerhub_username>/bps_sensitivity_analysis_frontend_image_final:latest
```

---

## Option 2: Local Installation

### Prerequisites

Make sure the following software is installed and available from your command line:

* **Python 3.11** (must be < 3.12)
* **Node.js with npm**
* **Java 8**

Verify the installations:

```bash
python --version
npm -v
java -version
```

### Frontend Setup

From the repository root, navigate to the frontend directory:

```bash
cd frontend
```

Install the frontend dependencies:

```bash
npm install
```

Start the frontend development server:

```bash
npm run dev
```

The frontend is available by default at:

```text
http://localhost:5173
```

### Backend Setup

Open another terminal and navigate from the repository root to the backend directory:

```bash
cd backend
```

Create a Python virtual environment:

```bash
python -m venv venv
```

Activate the virtual environment using the command appropriate for your operating system.

Install the required Python packages:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Start the backend:

```bash
python app.py
```

The backend API is available by default at:

```text
http://localhost:5000
```

### Running the Application Again

After the initial installation, start the frontend from the `frontend/` directory:

```bash
npm run dev
```

Then activate the Python virtual environment and start the backend from the `backend/` directory:

```bash
python app.py
```

---

# Usage

## Overview

The BPS Sensitivity Analysis Tool supports the analysis of how variations in simulation parameters influence simulation outcomes and KPIs.

The workflow integrates model discovery, parameter sampling and conversion, simulation, and sensitivity analysis.

## Workflow

The tool consists of three main modules:

1. **SIMOD – Model Discovery**
   Discovers a BPS model from an event log.

2. **Sampling & Simulation**
   Generates sensitivity-analysis samples, converts them into valid BPS parameter configurations, executes simulations, and extracts KPIs.

3. **Sensitivity Analysis & Visualization**
   Computes sensitivity measures and visualizes parameter influence.

The modules are designed to be used sequentially, but the sensitivity-analysis workflow can also start from an existing BPS model consisting of a BPMN model and its simulation-parameter configuration.

---

# Module 1: SIMOD – Model Discovery

This module discovers a BPMN process model and its simulation parameters from an event log.

## Example Inputs

The `example_simod_inputs/` directory contains example event logs that can be used to test the model-discovery workflow.

## Event Log Requirements

The input event log is provided as a CSV file containing the following attributes:

* `case_id`
* `activity`
* `resource`
* `start_time`
* `end_time`

## Outputs

The discovery module produces:

* a BPMN process model (`.bpmn`)
* a simulation-parameter configuration (`.json`)

Outputs are stored under:

```text
output/simod_outputs/<run_name>/
```

If no run name is provided, an output directory is generated automatically.

## Configuration

The implementation uses:

* **SIMOD version:** 5.1.6
* **Calendars:** Crisp (discrete)
* **Extraneous delays:** Disabled
* **Model discovery:** Includes optimization
* **Test log:** Not performed

For additional information about SIMOD, see the official SIMOD documentation.

---

# Module 2: Sampling & Simulation

This module takes a BPMN process model and its simulation-parameter configuration as input, generates sensitivity-analysis samples, converts them into executable BPS configurations, and performs simulation.

## Example Inputs

The `example_sensitivity_analysis_inputs/` directory contains example BPMN models and parameter configurations that can be used to test the sensitivity-analysis workflow without first executing SIMOD.

---

## Sampling

Sampling systematically varies the selected BPS parameters according to the selected sensitivity-analysis method.

The framework supports a normalized sampling space, after which sampled values are transformed into valid parameter values according to the semantics and constraints of the corresponding BPS parameter type.

Each resulting parameter configuration is simulated and the selected KPIs are recorded for subsequent sensitivity analysis.

---

## Sensitivity Analysis Methods

### Sobol

Sobol is a variance-based global sensitivity-analysis method that decomposes output variance into contributions associated with the analyzed inputs.

The implementation supports:

* **First-order index (S₁):** contribution of an individual input to output variance
* **Total-order index (Sₜ):** contribution of an input including effects involving interactions
* **Second-order index (Sᵢⱼ):** pairwise interaction effects, when enabled

The base sample size controls the number of model evaluations required for estimating the sensitivity indices. Increasing the sample size generally improves estimation but also increases computational cost.

---

### Morris

Morris is a global sensitivity-analysis method designed for computationally efficient screening of influential inputs.

The implementation computes:

* **μ*:** magnitude of the elementary effects, used to characterize overall input influence
* **σ:** variation in elementary effects across the input space, which can indicate nonlinearities.

The number of trajectories controls the sampling effort. Increasing the number of trajectories provides more observations of the elementary effects but increases computational cost.

The number of levels determines the discretization of the normalized input space used by the Morris design.

The implementation uses **SALib** for Sobol and Morris sampling and analysis.

---

## Simulation Settings

### Number of Cases

The number of cases determines how many process instances are simulated for each configuration.

Increasing the number of cases can reduce stochastic variation in the estimated process-level KPIs but increases simulation runtime.

### Simulation Replications per Sample

Multiple simulation replications can be performed for each sampled parameter configuration.

The KPI values obtained from the replications are aggregated before sensitivity analysis.

Increasing the number of replications can reduce simulation noise but also increases computational cost.

### Random Seed

A random seed can be specified for reproducible sampling and analysis where supported by the underlying components.

Because simulation engines may have their own stochastic behavior and seed-handling semantics, exact simulation reproducibility can depend on the selected BPS engine.

---

## Analysis Scope

The tool supports sensitivity analysis at two levels.

### Parameter-Group Level

Parameters belonging to the same BPS parameter group are analyzed together.

Examples of supported parameter groups include:

* Gateway probabilities
* Arrival distributions
* Arrival calendars
* Task–resource distributions
* Resource calendars
* Resource quantities

For non-gateway groups, parameters within the selected group are perturbed jointly using a shared sampled input. Gateway branches are sampled independently and assigned to the common Gateways group for group-level sensitivity attribution.

### Within-Group Level

Individual parameters within a selected parameter group are analyzed separately.

This enables the user to identify which individual parameters drive the sensitivity observed at the group level.

The number of sensitivity-analysis dimensions therefore depends on the selected analysis scope and parameter configuration.

---

## Runtime Considerations

Sensitivity analysis can require a large number of simulation runs. Runtime depends primarily on:

* sensitivity-analysis method
* sampling effort
* number of analyzed dimensions
* number of simulated cases
* number of simulation replications
* selected simulation engine

### Sobol

For first- and total-order indices, the number of required model evaluations grows approximately with:

```text
N × (D + 2)
```

where:

* `N` = base sample size
* `D` = number of sensitivity-analysis dimensions

The total simulation workload additionally depends on the number of cases and replications.

If second-order effects are enabled, additional model evaluations are required.

### Morris

The number of model evaluations grows approximately with:

```text
r × (D + 1)
```

where:

* `r` = number of trajectories
* `D` = number of sensitivity-analysis dimensions

Morris therefore generally requires fewer model evaluations than variance-based Sobol analysis for comparable dimensionality.

---

## Outputs

Module 2 stores its outputs under:

```text
output/simulation_and_sensitivity_analysis_outputs/<run_name>/
```

The generated artifacts include:

```text
user_config.json
samples/
simulation_results/
sensitivity_analysis_inputs/
```

These contain the run configuration, sampled parameter values, simulation KPIs, and inputs required for subsequent sensitivity analysis.

---

# Module 3: Sensitivity Analysis & Visualization

Module 3 takes the simulation outputs generated by Module 2 and computes the requested sensitivity measures.

The workflow is:

1. Select a simulation-results directory.
2. Select the KPI and statistic to analyze.
3. Run the selected sensitivity-analysis method.
4. Inspect and visualize the resulting sensitivity measures.

## Supported KPIs

Sensitivity analysis currently focuses on **process-level KPIs**.

Simulation outputs may additionally contain case-, task-, and resource-level statistics that can be used for further analysis.

## Outputs

Sensitivity-analysis results are stored under the corresponding simulation run:

```text
output/simulation_and_sensitivity_analysis_outputs/<run_name>/
└── sensitivity_analysis_outputs/
    └── <analysis_name>/
```

The outputs include the analysis configuration and computed sensitivity measures.

---

# Architecture and System Flow

## Overview

The BPS Sensitivity Analysis Tool follows a client–server architecture with a React frontend and Flask backend.

The backend coordinates the main research workflow:

```text
Event Log
    │
    ▼
┌──────────────────────────────┐
│ Module 1                     │
│ SIMOD Model Discovery        │
│                              │
│ Event Log                    │
│    ↓                         │
│ BPMN + Parameter JSON        │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Module 2                     │
│ Sampling & Simulation        │
│                              │
│ Parameter Extraction         │
│    ↓                         │
│ SA Sampling                  │
│    ↓                         │
│ Parameter Conversion         │
│    ↓                         │
│ Simulation                   │
│    ↓                         │
│ KPI Extraction               │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│ Module 3                     │
│ Sensitivity Analysis         │
│                              │
│ KPI Results                  │
│    ↓                         │
│ Sobol / Morris Analysis      │
│    ↓                         │
│ Sensitivity Measures         │
│    ↓                         │
│ Visualization                │
└──────────────────────────────┘
```

Alternatively, Module 2 can be executed directly using an existing BPMN model and simulation-parameter configuration.

---

# System Components

## Frontend

The frontend is implemented using React and Vite.

Location:

```text
frontend/src/
```

Main entry:

```text
frontend/src/App.jsx
```

Key components include:

* `InstructionsPanel.jsx` – user guidance
* `SimodModelDiscovery.jsx` – model-discovery interface
* `SamplingAndSimulation.jsx` – sampling and simulation configuration
* `SensitivityAnalysis.jsx` – sensitivity-analysis execution
* `Visualization.jsx` – visualization of results
* `VisualizationComponents/` – reusable visualization components

---

## Backend

The backend is implemented using Flask and Python.

Location:

```text
backend/
```

Main entry:

```text
backend/app.py
```

### Main API Endpoints

#### `POST /simod`

Performs BPS model discovery.

**Input:**

* event log
* discovery configuration

**Output:**

* BPMN process model
* simulation-parameter JSON

#### `POST /simulate`

Executes the sampling and simulation pipeline.

**Input:**

* BPMN model
* parameter JSON
* sensitivity-analysis configuration

**Output:**

* sampled configurations
* simulation results
* KPIs

#### `POST /sensitivity-analysis`

Executes sensitivity analysis.

**Input:**

* simulation results
* sensitivity-analysis configuration
* KPI selection

**Output:**

* Sobol or Morris sensitivity measures

---

# Core Backend Modules

## 1. SIMOD Module

Location:

```text
src/simod/
```

Main function:

```text
run_simod(...)
```

The module:

* prepares the model-discovery inputs
* configures the discovery procedure
* executes SIMOD
* stores the discovered BPMN model
* stores the discovered simulation parameters

The resulting BPS model contains the process structure and discovered simulation parameters required by the subsequent modules.

---

## 2. Simulation Pipeline

Location:

```text
src/simulation_pipeline/
```

Main function:

```text
run_simulation_pipeline(...)
```

The simulation pipeline coordinates the following steps.

### 2.1 Parameter Extraction

Location:

```text
extract_parameters/
```

The parameter-extraction component:

* parses the simulation-parameter configuration
* identifies modifiable BPS parameters
* organizes parameters according to their parameter groups
* reports extraction issues where applicable

### 2.2 Sampling

Location:

```text
sampling/
```

The sampling component:

* constructs the sensitivity-analysis problem definition
* generates Sobol or Morris samples using SALib
* stores the generated sample matrix for subsequent conversion

### 2.3 Parameter Conversion

Location:

```text
convert_samples/
```

The conversion component transforms normalized sensitivity-analysis samples into valid BPS parameter values.

It handles:

* gateway probabilities
* arrival distributions
* task–resource distributions
* arrival calendars
* resource calendars
* resource quantities

The parameter-specific transformations preserve the relevant structural constraints of each parameter type, such as valid routing-probability vectors and executable calendar/resource configurations.

### 2.4 Simulation Configuration Generation

Each sampled point is converted into a complete simulation-parameter configuration that can be executed by the selected BPS engine.

### 2.5 Simulation

The simulation component:

* executes the sampled configurations
* performs the requested number of replications
* extracts simulation KPIs
* aggregates KPI values across replications where applicable
* stores the resulting process-, case-, task-, and resource-level statistics

---

## 3. Sensitivity Analysis Module

Location:

```text
src/sensitivity_analysis/
```

Main function:

```text
run_sensitivity_analysis(...)
```

The module reads the sampling design and corresponding simulation outcomes and applies the selected sensitivity-analysis method.

### Sobol Analysis

The Sobol implementation computes:

* first-order indices (S₁)
* total-order indices (Sₜ)
* optional second-order indices (Sᵢⱼ)

### Morris Analysis

The Morris implementation computes:

* μ*
* σ

The resulting sensitivity measures are stored for subsequent interpretation and visualization.

---

# Key Libraries and Dependencies

The implementation uses the following main libraries and frameworks:

* **SIMOD 5.1.6** – data-driven BPS model discovery
* **Prosimos** – business process simulation
* **SALib** – Sobol and Morris sampling and sensitivity analysis
* **Pandas** – data processing and KPI aggregation
* **NumPy** – numerical computation
* **React + Vite** – frontend
* **Flask + Flask-CORS** – backend API


# Experimental Artifacts

The `SAExperiments/` directory contains the scripts, configuration templates, and processed results used to produce the experiments and figures reported in the accompanying paper.

The experimental artifacts are organized to support inspection and reproduction of the reported analyses.

## Included Artifacts

Depending on the experiment, the repository includes:

* experiment scripts
* analysis scripts
* configuration files
* processed simulation results
* sensitivity-analysis results
* result tables
* figures

Common output formats include:

* `.parquet`
* `.csv`
* `.xlsx`
* `.png`
* `.txt`

# Extension Points

The modular architecture supports extensions to different parts of the workflow.

### Additional Sensitivity-Analysis Methods

New sensitivity-analysis methods can be integrated into:

```text
src/sensitivity_analysis/
```

### Additional KPIs

Additional KPI computations can be incorporated into the simulation-output aggregation.

### Additional Visualizations

New visualization components can be added to:

```text
VisualizationComponents/
```

### Alternative Simulation Engines

The modular simulation layer can be extended to support additional BPS engines, subject to their parameter semantics and simulation interfaces.

---

# Reproducibility

The repository provides the implementation, example inputs, experiment configurations, scripts, and processed results required to inspect and reproduce the sensitivity-analysis workflow and the analyses reported in the accompanying paper.

For reproducing an analysis:

1. Install the tool using Docker or the local installation procedure.
2. Use either an event log with Module 1 or an existing BPMN model and parameter configuration with Module 2.
3. Configure the sensitivity-analysis method, parameter scope, sampling effort, and simulation settings.
4. Execute sampling and simulation.
5. Run Module 3 on the resulting KPIs.
6. Compare the generated sensitivity measures with the provided processed experimental results.

Because BPS execution can be stochastic and simulator-specific, exact numerical reproduction may depend on the simulation engine, randomization behavior, number of cases, and replication settings.

---

# Repository Purpose

This repository accompanies the research on sensitivity analysis for data-driven Business Process Simulation. It is intended to:

* provide the implementation of the proposed sensitivity-analysis workflow;
* document how the framework can be executed;
* provide example inputs for testing the implementation;
* make the experimental scripts and processed results available for inspection; and
* support reproduction and extension of the reported experiments.
