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
├── README.md
├── requirements.txt
├── app.py
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

We've included two scripts to automate the setup:

#### Bash Script (Linux-only)
```bash
chmod +x start_prometheus_stack.sh
./start_prometheus_stack.sh
```

#### Python Script (Cross-platform)
```bash
python start_prometheus_stack.py
```

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

Check that ROCm-backed PyTorch sees the GPU:

```bash
python -c "import torch; print('torch:', torch.__version__); print('cuda_available:', torch.cuda.is_available())"
```

Optional GPU tooling check:

```bash
which rocm-smi || command -v rocm-smi
```

## Run The App

Start the Gradio app:

```bash
python app.py
```

On first launch the app downloads `Qwen/Qwen2.5-7B-Instruct`, so startup may take a while.
When the server is ready, Gradio prints a local URL and may also print a public share URL.

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


