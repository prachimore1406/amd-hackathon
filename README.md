# SOWA: Self-Optimizing Workload Agent

SOWA is a hackathon prototype for explainable workload placement on AMD infrastructure.
It combines:

- real local telemetry from the notebook CPU, memory, and AMD GPU when `rocm-smi` is available
- simulated cluster nodes so the demo still feels like a multi-node placement problem
- an LLM-based DevOps agent that explains its reasoning in plain English
- generated Kubernetes `Deployment` YAML targeting AMD hardware labels

The current demo is optimized for the AMD Developer Cloud Jupyter environment with hardware close to:

- 10-13 CPU cores
- 240 GB RAM
- 25 GB persistent storage
- 16 GB temporary storage
- AMD MI350 class GPU
- 192 GB VRAM

## Why This Project

Modern infrastructure teams often use static placement rules such as `nodeAffinity`, taints, or hand-written heuristics.
That works poorly when clusters contain a mix of CPU-heavy nodes, general-purpose nodes, and expensive accelerators.

SOWA focuses on three demo goals:

- choose a sensible node for each incoming workload
- explain the decision clearly
- show how live telemetry changes the decision

## Current Demo Features

- `Hybrid telemetry`: combines real local notebook telemetry with simulated remote node load
- `Explainable decisions`: returns a human-readable placement reason
- `Performance impact panel`: compares the baseline hardware choice with the current SOWA placement
- `Valid Kubernetes output`: generates `apps/v1` deployment YAML with selectors and labels
- `Real GPU spike button`: runs a short, bounded GPU burst on the local notebook and marks a recent accelerator contention event
- Professional React UI

## Architecture

The app uses a simple two-step LangGraph flow:

1. `simulator_agent`
   - picks the next workload
   - gathers real local telemetry
   - combines it with simulated cluster node load

2. `devops_agent`
   - reasons over the current hybrid cluster snapshot
   - selects a target node
   - generates a Kubernetes manifest
   - summarizes performance impact

This is a linear flow:

```text
simulator -> devops -> end
```

## Repository Layout

```text
.
├── api.py
├── README.md
├── requirements.txt
├── setup_and_run.py
├── frontend/
│   ├── src/
│   ├── index.html
│   └── package.json
└── sowa/
    ├── __init__.py
    ├── agents.py
    ├── llm.py
    ├── metrics.py
    ├── state.py
    ├── workflow.py
    └── workloads.py
```

## AMD Developer Cloud Setup

Open a terminal in the AMD Developer Cloud Jupyter environment and run:

```bash
git clone <your-repo-url>
cd amd-hackathon
```

If your environment is storage-constrained, move the Hugging Face cache to temporary storage before the first run:

```bash
export HF_HOME=/tmp/hf-cache
export TRANSFORMERS_CACHE=/tmp/hf-cache
mkdir -p /tmp/hf-cache
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## (Optional) Setup Local Prometheus + Node Exporter in Your Single GPU Pod

For a more production-like telemetry source inside your JupyterHub pod:

### Option 1: Use the Automated Scripts (Recommended)

Use the built-in one-click setup script:

```bash
python setup_and_run.py
```

This script is intended for the Linux-based AMD Developer Cloud or similar Linux environments because it downloads Linux binaries for Prometheus, Node Exporter, Grafana, and Node.js.

### Option 2: Manual Setup

If you prefer to set it up manually, follow these steps:

#### Step 1: Download and Start Prometheus
```bash
# Download Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.52.0/prometheus-2.52.0.linux-amd64.tar.gz
tar xzf prometheus-2.52.0.linux-amd64.tar.gz
cd prometheus-2.52.0.linux-amd64

# Create prometheus.yml
cat > prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
EOF

# Start Prometheus in background
nohup ./prometheus --config.file=prometheus.yml --web.listen-address=:9090 > prometheus.log 2>&1 &
echo "Prometheus started at http://localhost:9090"

# Go back to workspace
cd /workspace/shared
```

#### Step 2: Download and Start Node Exporter
```bash
# Download node_exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz
tar xzf node_exporter-1.8.2.linux-amd64.tar.gz
cd node_exporter-1.8.2.linux-amd64

# Start node_exporter in background
nohup ./node_exporter > node_exporter.log 2>&1 &
echo "Node Exporter started at http://localhost:9100"

# Go back to workspace
cd /workspace/shared
```

### Step 3: Access the Prometheus UI
Once Prometheus is running, you can view its UI! In a JupyterHub environment:

1. **Using Jupyter Port Forwarding** (if supported):
   - Look for a "Port Forwarding" or "Proxy" section in your JupyterHub interface
   - Forward local port 9090 to the pod's port 9090

2. **Using `jupyter-server-proxy`** (if installed):
   - Try accessing: `http://<your-jupyterhub-url>/proxy/9090`

Once accessible, open `http://localhost:9090` (or the proxied URL) in your browser to explore Prometheus!

### Step 4: Enable Prometheus in SOWA
To use Prometheus as your telemetry source, edit `sowa/metrics.py` and change:
```python
USE_PROMETHEUS = True
```

## Prometheus Metrics Used

When `USE_PROMETHEUS = True` in `sowa/metrics.py`, SOWA reads the following metrics to make placement decisions:

### Standard Metrics (from Node Exporter)
- `node_cpu_seconds_total{mode="idle"}`: Used to calculate total CPU utilization
- `node_memory_MemTotal_bytes`: Total memory on the node
- `node_memory_MemAvailable_bytes`: Available memory on the node
- `node_memory_Active_bytes`: Currently active memory

### Custom Metrics (from SOWA textfile collector)
- `sowa_gpu_spike_active`: 1 if a GPU spike is currently active, 0 otherwise
- `sowa_gpu_spike_recent`: Time in seconds since the last GPU spike

### How Metrics Are Used
- **CPU Utilization**: Calculated as `100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)`
- **Memory Utilization**: Calculated as `((node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes) * 100`
- **GPU Contention**: Uses `sowa_gpu_spike_active` and `sowa_gpu_spike_recent` to avoid placing new ML workloads on a contended GPU node

Check that ROCm-backed PyTorch sees the GPU:

```bash
python -c "import torch; print('torch:', torch.__version__); print('cuda_available:', torch.cuda.is_available())"
```

Optional GPU tooling check:

```bash
which rocm-smi || command -v rocm-smi
```

## (RECOMMENDED) ONE-CLICK COMPLETE SETUP! 🚀

Just run **ONE SINGLE SCRIPT** — `setup_and_run.py` — it does *EVERYTHING* automatically:
1. Installs Python dependencies
2. Installs Node.js/npm (if not present)
3. Installs Prometheus, Node Exporter, and Grafana
4. Builds the React frontend
5. Starts ALL services together!

### Step 1: Run the ONE-CLICK Script!
That's it! No other steps needed!
```bash
python setup_and_run.py
```

If you are not on Linux, use the manual setup path instead. The one-click script intentionally exits early on unsupported operating systems instead of attempting a broken install.

### Done! Open your browsers!
1. **SOWA UI**: http://localhost:8000
2. **Grafana Dashboards**: http://localhost:3000
   - Login: `admin` / `admin`
   - Import dashboard: Upload `grafana_sowa_dashboard.json` from the project root!
3. **Prometheus**: http://localhost:9090

### Stop everything gracefully:
Press **Ctrl+C** in the terminal — all services will stop cleanly!

---

## (Optional) Manual Setup Steps (for advanced use)
For full control, you can still use the individual scripts:
- `api.py`: Start just the FastAPI backend
- `frontend/`: Build or run the React UI separately with Vite
- `sowa/`: Core scheduling, telemetry, and workload logic used by the backend

---

## Grafana Pre-Built Dashboards (Optional!)

For beautiful, pre-built visualizations instead of manual PromQL queries, set up Grafana!

### Install Grafana on AMD Jupyter Environment

1. **Download Grafana**:
```bash
cd /workspace/shared
wget https://dl.grafana.com/oss/release/grafana-11.1.0.linux-amd64.tar.gz
tar -xzf grafana-11.1.0.linux-amd64.tar.gz
```

2. **Run Grafana**:
```bash
cd /workspace/shared/grafana-11.1.0
./bin/grafana-server web &
```
Grafana runs at http://localhost:3000!

3. **Login**:
Default username/password: `admin`/`admin` (you'll be prompted to change it!)

4. **Add Prometheus Data Source**:
- Go to **Connections > Data Sources > Add New Data Source**
- Select **Prometheus**
- Set URL to `http://localhost:9090`
- Click "Save & Test"

5. **Import SOWA Dashboard**:
- Go to **Dashboards > New > Import**
- Click "Upload JSON file" and select `grafana_sowa_dashboard.json` from the project root!
- Select your Prometheus data source!
- Click "Import"! That's it!

---

On first launch the app may download `Qwen/Qwen2.5-7B-Instruct`, so backend startup may take a while when the full LLM stack is installed. If the optional LLM dependencies are unavailable, SOWA now falls back to a deterministic rule-based scheduler so the backend can still start.

## Demo Flow

Use this order during the hackathon demo:

1. Click `Run Next Simulation Turn`
2. Show the workload request, target node, reasoning, and performance impact
3. Click `Trigger Real GPU Spike`
4. Wait a few seconds, then click `Refresh Telemetry`
5. Point out the `Recent Accelerator Event` line in the local telemetry
6. Click `Run Next Simulation Turn` again to show the updated decision
7. Optionally click `Run Current Workload On Notebook` to create additional local CPU, memory, or GPU pressure

## What Each Button Does

- `Run Next Simulation Turn`
  - advances the simulated cluster state
  - picks the next workload
  - asks the agent for a fresh placement decision

- `Run Current Workload On Notebook`
  - runs a real local stress job that matches the current workload type
  - affects notebook telemetry, not a remote Kubernetes cluster

- `Trigger Real GPU Spike`
  - launches a short real GPU burst on the notebook GPU
  - records a recent accelerator contention event for the scheduler to consider

- `Refresh Telemetry`
  - refreshes local telemetry without advancing simulated cluster drift

- `Reset`
  - clears the current demo state

## Notes And Limitations

- The local notebook node is real. The other cluster nodes are simulated for demo storytelling.
- The generated Kubernetes manifest is a placement artifact only. The app does not apply it to a live cluster.
- If `rocm-smi` is unavailable, the demo still runs, but GPU telemetry becomes less detailed.
- The first model download may be the slowest part of the setup because persistent storage is limited.

