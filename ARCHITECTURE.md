# SOWA Architecture Document

## 1. Overview
SOWA (Self-Optimizing Workload Agent) is a GenAI-powered Kubernetes workload placement demo for AMD hardware. It combines real-time telemetry, multi-agent orchestration, and explainable AI decisions.


## 2. Full Stack Architecture Diagram
```mermaid
flowchart TB
    subgraph "User Interface Layer"
        UI[Gradio Web UI]
    end

    subgraph "GenAI Orchestration Layer"
        LG[LangGraph State Machine]
        SA[Simulator Agent]
        DA[DevOps Agent]
    end

    subgraph "Telemetry & Context Layer"
        LC[Local Collectors<br/>(psutil, rocm-smi)]
        PC[Prometheus Integration<br/>(Node Exporter, Textfile Collector)]
        WC[Workload Controller]
    end

    subgraph "Model & Inferencing Layer"
        LLM[Qwen2.5-7B-Instruct]
        HF[HuggingFace Transformers]
        LC_PT[LangChain + LangChain-HuggingFace]
    end

    subgraph "Infrastructure Layer"
        AMD[AMD MI350X / ROCm]
        K8S[Kubernetes (Simulated)]
    end

    UI -->|Run Turn / Trigger Spike| LG
    LG -->|Get Cluster Snapshot| SA
    SA -->|Read Telemetry| LC
    SA -->|Read Telemetry| PC
    LG -->|Make Placement Decision| DA
    DA -->|Inference Request| LC_PT
    LC_PT -->|Text Generation| HF
    HF -->|Run on GPU| LLM
    LLM -->|Deployed on| AMD
    DA -->|Generate Manifest| K8S
    DA -->|Update UI| UI
    WC -->|Write Metric| PC
    WC -->|Run Local Workload| LC
```


## 3. Technology Stack
| Layer               | Technologies                                                                 |
|---------------------|-----------------------------------------------------------------------------|
| **UI**              | Gradio                                                                      |
| **Orchestration**   | LangGraph, LangChain                                                         |
| **Inferencing**     | HuggingFace Transformers, Accelerate, PyTorch, Qwen2.5-7B-Instruct          |
| **Telemetry**       | psutil, rocm-smi, Prometheus, Node Exporter (Textfile Collector), requests  |
| **Hardware**        | AMD EPYC, AMD Instinct MI350X, ROCm                                         |
| **Language**        | Python 3.x                                                                  |


## 4. GenAI Fundamentals & Principles Used

### 4.1 Multi-Agent Systems
SOWA uses a **two-agent system** orchestrated by LangGraph:
1. **Simulator Agent**:
   - Prepares context: Mixes real local telemetry with simulated cluster nodes
   - Selects next workload
2. **DevOps Agent**:
   - Makes placement decision
   - Generates Kubernetes manifest
   - Explains reasoning and performance impact

### 4.2 Retrieval-Augmented Generation (RAG) / Context Engineering
- **Telemetry as Context**: We inject real-time cluster state, local CPU/GPU/memory usage, and recent events directly into the LLM prompt
- **No fine-tuning needed**: All decisions are context-driven

### 4.3 Structured Prompting
- **Role Prompting**: LLM is explicitly instructed: "You are an AI DevOps Orchestrator managing an AMD cluster"
- **Rule-Based Prompting**:
  - Hardware preferences (ML training → GPU, web serving → CPU)
  - Load constraints (>80% nodes are avoided)
  - Contention avoidance rules
- **Structured Output Enforcement**: LLM returns JSON with predefined keys:
  - `reasoning`, `decision`, `risk_level`, `performance_explanation`, `tool_trace_summary`

### 4.4 Output Normalization & Robustness
- **`_normalize_decision`**: Maps messy LLM outputs ("epyc", "GPU") to canonical node names
- **`_parse_structured_response`**: Robust JSON extraction with fallback logic

### 4.5 Explainable AI (XAI)
- Tracks and displays `tool_trace` for transparency
- Generates `devops_reasoning`
- Compares baseline placement to SOWA placement with `performance_summary`

### 4.6 Responsible AI / Safety
- Uses low temperature (0.2) for consistent decisions
- All generated manifests are demo-only (not applied to real clusters)
- GPU spike workloads are bounded (short duration)


## 5. Key Components

### 5.1 State Management
`MultiAgentState` (TypedDict) maintains all data passed between agents and displayed in the UI:
- Cluster status, current workload, last decision
- DevOps reasoning, performance summary, Kubernetes YAML
- Local telemetry, node loads, tool trace, risk level

### 5.2 Telemetry System
Supports two modes:
1. **Local Mode (default)**: Uses `psutil` (CPU/memory) and `rocm-smi` (GPU)
2. **Prometheus Mode**: Queries Prometheus for metrics, uses custom textfile metrics for GPU spikes

### 5.3 Workload Controller
Manages local demo workloads:
- CPU, Memory, GPU stress jobs
- GPU spike trigger
- Tracks active jobs and recent spikes


## 6. Data Flow
1. User clicks "Run Next Simulation Turn"
2. Simulator Agent:
   - Gets cluster snapshot (telemetry + simulated nodes)
   - Picks next workload
3. DevOps Agent:
   - Refreshes live telemetry
   - Injects all context into LLM prompt
   - Runs inference on Qwen2.5-7B
   - Parses and normalizes decision
   - Generates Kubernetes manifest
4. UI updates with all results


## 7. Future Work
- Real Kubernetes integration (apply manifests to real clusters)
- Prometheus Alertmanager webhook triggering
- Policy modes (Performance / Balanced / Eco)
- Multi-node real cluster support