# SOWA Hackathon Code Appendix

This appendix contains the most relevant code excerpts for hackathon submission.
It focuses on the parts of the repository that demonstrate:

- multi-agent orchestration
- FastAPI backend and state flow
- telemetry and GPU contention detection
- LLM-backed placement reasoning
- frontend controls and observability
- Grafana dashboard integration

## 1. Workflow Orchestration

File: `sowa/workflow.py`

Purpose:
- defines the two-step LangGraph workflow
- runs the simulator agent first, then the DevOps agent

```python
from langgraph.graph import StateGraph, END
from sowa.state import MultiAgentState
from sowa.agents import simulator_agent, devops_agent

def build_graph():
    workflow = StateGraph(MultiAgentState)
    workflow.add_node("simulator", simulator_agent)
    workflow.add_node("devops", devops_agent)

    workflow.set_entry_point("simulator")
    workflow.add_edge("simulator", "devops")
    workflow.add_edge("devops", END)

    return workflow.compile()

agent_app = build_graph()
```

Why it matters:
- shows that the demo is structured as a repeatable agent pipeline rather than a one-off script
- cleanly separates telemetry gathering from placement reasoning

## 2. FastAPI Backend

File: `api.py`

Purpose:
- exposes the demo as a web API
- stores current workflow state
- provides endpoints for turns, telemetry refresh, workload launch, and GPU spike triggering

```python
from fastapi import FastAPI
from pydantic import BaseModel

from sowa.metrics import get_cluster_snapshot
from sowa.workflow import agent_app
from sowa.workloads import launch_workload_for_request, trigger_real_gpu_spike

app = FastAPI(
    title="SOWA API",
    version="1.0",
    description="Self-Optimizing Workload Agent API",
)

workflow_graph = agent_app
current_state: dict = {}
```

```python
def initial_state_dict() -> dict:
    snapshot = get_cluster_snapshot("None", advance_simulation=False)
    return {
        "cluster_status_text": snapshot["cluster_status_text"],
        "current_workload": "",
        "last_decision": "None",
        "devops_reasoning": "",
        "performance_summary": "",
        "yaml_output": "",
        "local_telemetry_text": snapshot["local_telemetry_text"],
        "telemetry_source": snapshot["telemetry_source"],
        "node_loads": snapshot["node_loads"],
        "tool_trace": "",
        "risk_level": "Low",
    }
```

```python
@app.post("/api/run-turn")
async def run_next_turn() -> SOWAState:
    global current_state
    result = workflow_graph.invoke(current_state)
    current_state = {**current_state, **result}
    return serialize_state(current_state)

@app.post("/api/trigger-gpu-spike")
async def trigger_gpu_spike():
    global current_state
    message = trigger_real_gpu_spike()
    refresh_snapshot()
    return {"status": "ok", "message": message, "state": serialize_state(current_state)}
```

```python
def telemetry_poller() -> None:
    while not _telemetry_poller_stop.is_set():
        try:
            snapshot = get_cluster_snapshot(
                current_state.get("last_decision", "None"),
                advance_simulation=False,
            )
            if current_state:
                current_state.update(
                    {
                        "cluster_status_text": snapshot["cluster_status_text"],
                        "local_telemetry_text": snapshot["local_telemetry_text"],
                        "telemetry_source": snapshot["telemetry_source"],
                        "node_loads": snapshot["node_loads"],
                    }
                )
        except Exception as exc:
            print(f"[SOWA API] Telemetry poller refresh failed: {exc}", flush=True)
        _telemetry_poller_stop.wait(2.0)
```

Why it matters:
- demonstrates a real backend surface, not just notebook cells
- keeps telemetry fresh enough for Prometheus and Grafana to observe short-lived GPU events

## 3. Placement Logic And Guardrails

File: `sowa/agents.py`

Purpose:
- defines workload baselines
- builds placement candidates
- avoids the local notebook node when GPU contention is active or recent

```python
NODE_LABELS = {
    "AMD-EPYC-CPU": "cpu-epyc-milan",
    "AMD-Instinct-GPU": "gpu-instinct-mi350x",
    "General-VM": "general-purpose",
    LOCAL_NODE_NAME: "local-amd-mi350",
}

WORKLOAD_BASELINES = {
    "ml training": "AMD-Instinct-GPU",
    "web serving": "AMD-EPYC-CPU",
    "data processing": "General-VM",
}
```

```python
def _candidate_decisions_for_workload(workload_request: str, accelerator_event: str) -> list[str]:
    baseline = _baseline_decision(workload_request)
    ordered = [baseline, "AMD-EPYC-CPU", "AMD-Instinct-GPU", "General-VM", LOCAL_NODE_NAME]
    unique_choices = []
    for decision in ordered:
        if decision not in unique_choices:
            unique_choices.append(decision)

    accelerator_text = accelerator_event.lower()
    if "ml training" in _workload_type(workload_request) and (
        "active" in accelerator_text or "recent" in accelerator_text
    ):
        unique_choices = [choice for choice in unique_choices if choice != LOCAL_NODE_NAME]
    return unique_choices
```

```python
def _deterministic_decision(workload_request: str, node_loads: dict[str, int], accelerator_event: str) -> str:
    candidates = _candidate_decisions_for_workload(workload_request, accelerator_event)
    safe_candidates = [choice for choice in candidates if node_loads.get(choice, 100) <= 80]
    if safe_candidates:
        return min(safe_candidates, key=lambda choice: (node_loads.get(choice, 100), candidates.index(choice)))
    return min(candidates, key=lambda choice: (node_loads.get(choice, 100), candidates.index(choice)))
```

Why it matters:
- shows explicit safety rules beyond the LLM prompt
- keeps the system demoable even when the model output is imperfect

## 4. DevOps Agent Prompt And Structured Output

File: `sowa/agents.py`

Purpose:
- refreshes telemetry at decision time
- invokes the LLM with explicit rules
- expects strict JSON output for downstream reliability

```python
def devops_agent(state: MultiAgentState) -> MultiAgentState:
    live_snapshot = get_live_telemetry(state.get("last_decision", "None"), advance_simulation=False)
    recent_gpu_event = get_recent_gpu_event()
    tool_trace = (
        "Tool 1: get_live_telemetry() -> refreshed local telemetry without advancing simulator\n"
        f"Tool 2: get_recent_gpu_event() -> {recent_gpu_event}"
    )
    prompt = f"""
    You are an AI DevOps Orchestrator managing an AMD cluster.
    Cluster Status: {live_snapshot["cluster_status_text"]}
    Local Telemetry Source: {live_snapshot.get("telemetry_source", state.get("telemetry_source", "simulated"))}
    Local Telemetry Details: {live_snapshot.get("local_telemetry_text", state.get("local_telemetry_text", "Unavailable"))}
    Recent GPU Event Tool: {recent_gpu_event}
    Incoming Workload: {state["current_workload"]}

    Rules:
    - ML Training prefers AMD-Instinct-GPU.
    - Web Serving prefers AMD-EPYC-CPU.
    - Data Processing prefers General-VM.
    - If a physical node load is above 80%, avoid it and choose another node.
    - Avoid Local-Notebook-Node for new ML work when the recent GPU event reports an active or recent spike.
    - decision must be exactly one of: AMD-EPYC-CPU, AMD-Instinct-GPU, General-VM, Local-Notebook-Node.
    """.strip()
```

```python
response = llm.invoke(prompt)
parsed = _parse_structured_response(response)
if parsed is None:
    parsed = _fallback_response(
        state,
        live_snapshot,
        reason="Invalid JSON response. Used deterministic fallback scheduler.",
        raw_response=str(response),
    )
```

Why it matters:
- demonstrates a telemetry-grounded agent pattern
- uses structured output and deterministic fallback for reliability

## 5. Local Telemetry And Cluster Snapshot

File: `sowa/metrics.py`

Purpose:
- reads local CPU, memory, and ROCm GPU telemetry
- combines the real notebook node with simulated remote nodes
- produces the hybrid cluster state that the agent reasons over

```python
_SIM_NODES = {
    "AMD-EPYC-CPU": 35,
    "AMD-Instinct-GPU": 20,
    "General-VM": 55,
}
LOCAL_NODE_NAME = "Local-Notebook-Node"
```

```python
def _read_rocm_smi() -> Dict[str, str]:
    try:
        result = subprocess.run(
            ["rocm-smi", "--showuse", "--showmemuse", "--showtemp", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            set_gpu_utilization(0.0, available=False)
            return {"available": "false", "details": "rocm-smi unavailable"}
        utilization_percent = _gpu_utilization_from_rocm_output(result.stdout)
        set_gpu_utilization(utilization_percent or 0.0, available=utilization_percent is not None)
        return {
            "available": "true",
            "details": result.stdout.strip()[:1200],
            "utilization_percent": f"{(utilization_percent or 0.0):.1f}",
        }
    except FileNotFoundError:
        set_gpu_utilization(0.0, available=False)
        return {"available": "false", "details": "rocm-smi not installed"}
```

```python
def _read_local_telemetry() -> Dict[str, str]:
    cpu = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory().percent
    gpu = _read_rocm_smi()
    active_jobs = get_active_workloads_text()
    accelerator_event = get_recent_accelerator_event_text()

    return {
        "cpu_percent": f"{cpu:.1f}",
        "memory_percent": f"{memory:.1f}",
        "telemetry_source": "local-cpu-memory+rocm-smi" if gpu["available"] == "true" else "local-cpu-memory",
        "local_telemetry_text": "...",
        "active_workload_count": str(get_active_workload_count()),
        "accelerator_event": accelerator_event,
    }
```

```python
def get_cluster_snapshot(last_decision: str, advance_simulation: bool = True) -> Dict[str, str]:
    local = _read_local_telemetry()
    sim_nodes = _update_simulated_nodes(last_decision) if advance_simulation else _simulated_node_text()
    node_loads = _current_node_loads(local)

    local_node_line = (
        f"{LOCAL_NODE_NAME} (CPU: {local['cpu_percent']}%, Memory: {local['memory_percent']}%, Active Jobs: {local['active_workload_count']})"
    )
    cluster_status = f"{local_node_line}, {sim_nodes}"

    return {
        "cluster_status_text": cluster_status,
        "local_telemetry_text": local["local_telemetry_text"],
        "telemetry_source": local["telemetry_source"],
        "node_loads": node_loads,
    }
```

Why it matters:
- this is the hybrid telemetry core of the demo
- it mixes real notebook signals with simulated cluster storytelling

## 6. GPU Activity, Spike, And Utilization Metrics

File: `sowa/workloads.py`

Purpose:
- tracks active workloads
- exports GPU spike, activity, and utilization metrics for Prometheus and Grafana
- aligns custom signals with real ROCm utilization thresholds

```python
_GPU_SPIKE_WINDOW_SEC = 20
_GPU_ACTIVITY_WINDOW_SEC = 45
_GPU_ACTIVITY_THRESHOLD_PERCENT = 5.0
_GPU_SPIKE_THRESHOLD_PERCENT = 70.0
```

```python
def _update_gpu_metrics():
    with _LOCK:
        explicit_spike = any("[GPU-SPIKE]" in job for job in _ACTIVE_WORKLOADS)
        active_gpu_work = any(_is_gpu_workload(job) for job in _ACTIVE_WORKLOADS)
        gpu_utilization_active = (
            _GPU_UTILIZATION_AVAILABLE == 1 and _GPU_UTILIZATION_PERCENT >= _GPU_ACTIVITY_THRESHOLD_PERCENT
        )
        gpu_utilization_spike = (
            _GPU_UTILIZATION_AVAILABLE == 1 and _GPU_UTILIZATION_PERCENT >= _GPU_SPIKE_THRESHOLD_PERCENT
        )
        active_spike = explicit_spike or gpu_utilization_spike
        active_gpu_activity = active_gpu_work or bool(_ACTIVE_GPU_ACTIVITIES) or gpu_utilization_active

    with open(TEXTFILE_PATH, "w") as f:
        f.write(f"sowa_gpu_spike_active {1 if active_spike else 0}\n")
        f.write(f"sowa_gpu_activity_active {1 if active_gpu_activity else 0}\n")
        f.write(f"sowa_gpu_utilization_percent {gpu_utilization_percent:.2f}\n")
        f.write(f"sowa_gpu_utilization_available {gpu_utilization_available}\n")
```

```python
def set_gpu_utilization(percent: float, available: bool) -> None:
    global _GPU_UTILIZATION_PERCENT, _GPU_UTILIZATION_AVAILABLE, _LAST_GPU_SPIKE_AT
    with _LOCK:
        _GPU_UTILIZATION_PERCENT = max(0.0, min(100.0, float(percent)))
        _GPU_UTILIZATION_AVAILABLE = 1 if available else 0
        if _GPU_UTILIZATION_AVAILABLE == 1:
            if _GPU_UTILIZATION_PERCENT >= _GPU_ACTIVITY_THRESHOLD_PERCENT:
                _mark_gpu_activity_event_locked()
            if _GPU_UTILIZATION_PERCENT >= _GPU_SPIKE_THRESHOLD_PERCENT:
                _LAST_GPU_SPIKE_AT = time.time()
    _update_gpu_metrics()
```

```python
def get_recent_accelerator_event_text() -> str:
    with _LOCK:
        explicit_spike = any("[GPU-SPIKE]" in job for job in _ACTIVE_WORKLOADS)
        seconds_since_spike = time.time() - _LAST_GPU_SPIKE_AT
        gpu_utilization_available = _GPU_UTILIZATION_AVAILABLE == 1
        gpu_utilization_percent = _GPU_UTILIZATION_PERCENT
        gpu_utilization_spike = gpu_utilization_available and gpu_utilization_percent >= _GPU_SPIKE_THRESHOLD_PERCENT

    if explicit_spike:
        return "Real GPU spike is active on the local notebook node."
    if gpu_utilization_spike:
        return (
            f"GPU contention is active on the local notebook node "
            f"({gpu_utilization_percent:.1f}% utilization)."
        )
```

Why it matters:
- this is the core observability logic behind the Grafana metrics
- it connects demo actions and real GPU load to scheduling-relevant events

## 7. Real Local Workload And GPU Spike Triggers

File: `sowa/workloads.py`

Purpose:
- creates bounded local CPU, memory, and GPU pressure
- provides a real GPU spike button for demo storytelling

```python
def _gpu_job(name: str, duration_sec: int = 12) -> None:
    label = f"{name} [GPU]"
    _add_job(label)
    try:
        if torch is None or not torch.cuda.is_available():
            time.sleep(2)
            return
        device = torch.device("cuda")
        end_time = time.time() + duration_sec
        a = torch.randn((4096, 4096), device=device)
        b = torch.randn((4096, 4096), device=device)
        while time.time() < end_time:
            c = torch.matmul(a, b)
            a = torch.relu(c)
            b = torch.tanh(c)
        torch.cuda.synchronize()
    finally:
        _remove_job(label)
```

```python
def _gpu_spike_job(duration_sec: int = 4, matrix_size: int = 4096, warmup_iterations: int = 6) -> None:
    label = "Demo-GPU-Spike [GPU-SPIKE]"
    _add_job(label)
    try:
        if torch is None or not torch.cuda.is_available():
            time.sleep(1)
            return

        _mark_gpu_spike_event()
        device = torch.device("cuda")
        dtype = torch.float16
        a = torch.randn((matrix_size, matrix_size), device=device, dtype=dtype)
        b = torch.randn((matrix_size, matrix_size), device=device, dtype=dtype)
        end_time = time.time() + duration_sec

        for _ in range(warmup_iterations):
            a = torch.matmul(a, b)
            b = torch.relu(a)

        while time.time() < end_time:
            a = torch.matmul(a, b)
            b = torch.tanh(a)

        torch.cuda.synchronize()
    finally:
        _remove_job(label)
```

Why it matters:
- proves the demo can generate real local accelerator pressure
- makes telemetry changes visible and actionable

## 8. Lazy LLM Initialization With GPU Activity Tracking

File: `sowa/llm.py`

Purpose:
- lazily loads the main LLM on first use
- tracks model load as GPU activity
- falls back to a deterministic scheduler when dependencies are unavailable

```python
class FallbackLLM:
    def invoke(self, prompt_input):
        prompt_lower = str(prompt_input).lower()
        if "ml training" in prompt_lower:
            decision = "AMD-Instinct-GPU"
            risk_level = "Medium"
            reasoning = "Selected the GPU node because the workload is ML training and the fallback scheduler prioritizes accelerator hardware."
        elif "web serving" in prompt_lower:
            decision = "AMD-EPYC-CPU"
            risk_level = "Low"
            reasoning = "Selected the EPYC CPU node because the workload is web serving and benefits from predictable CPU performance."
        else:
            decision = "General-VM"
            risk_level = "Low"
            reasoning = "Selected the general-purpose node because the workload does not require specialized hardware."
```

```python
def _build_llm():
    model_id = "Qwen/Qwen2.5-7B-Instruct"
    use_accelerator = torch.cuda.is_available()
    device = 0 if use_accelerator else -1
    torch_dtype = torch.float16 if use_accelerator else torch.float32

    if use_accelerator:
        begin_gpu_activity("LLM Model Load")
    try:
        pipe = pipeline(
            "text-generation",
            model=model_id,
            device=device,
            max_new_tokens=250,
            temperature=0.2,
            torch_dtype=torch_dtype,
            return_full_text=False,
        )
    finally:
        if use_accelerator:
            end_gpu_activity("LLM Model Load")
```

```python
class LazyLLM:
    def __init__(self):
        self._client = None

    def invoke(self, prompt_input):
        if self._client is None:
            _log("First inference requested; loading model client now.")
            self._client = _build_llm()
        response = self._client.invoke(prompt_input)
        return response
```

Why it matters:
- shows a practical GenAI integration with a robust fallback path
- makes model initialization visible inside the GPU observability story

## 9. React Frontend Controls

File: `frontend/src/App.jsx`

Purpose:
- exposes the demo flow in a usable interface
- allows judges to run turns, refresh telemetry, trigger GPU spike, and run local workloads

```jsx
const fetchState = async () => {
  try {
    const res = await axios.get(`${API_BASE}/state`)
    setState(res.data)
  } catch (err) {
    console.error('Error fetching state:', err)
  }
}

useEffect(() => {
  fetchState()
}, [])
```

```jsx
const handleTriggerSpike = async () => {
  setLoading(true)
  try {
    await axios.post(`${API_BASE}/trigger-gpu-spike`)
    await fetchState()
  } catch (err) {
    console.error(err)
  } finally {
    setLoading(false)
  }
}
```

```jsx
<Button onClick={handleRunTurn} variant="primary" loading={loading} icon="▶">
  Run Simulation Turn
</Button>
<Button onClick={handleRefresh} variant="secondary" loading={loading} icon="↻">
  Refresh Telemetry
</Button>
<Button onClick={handleTriggerSpike} variant="accent" loading={loading} icon="⚡">
  Trigger GPU Spike
</Button>
<Button onClick={handleRunWorkload} variant="secondary" loading={loading} disabled={!state?.current_workload} icon="⏵">
  Run Workload Locally
</Button>
```

Why it matters:
- shows the demo is operable by judges without code changes
- connects the backend actions directly to visible UI controls

## 10. Grafana Dashboard Metrics

File: `grafana_sowa_dashboard.json`

Purpose:
- visualizes the custom GPU metrics in Grafana
- separates spike, activity, and utilization into distinct panels

```json
{
  "expr": "clamp_max(sowa_gpu_spike_active + (sowa_gpu_spike_recent > bool 0), 1)",
  "legendFormat": "GPU Spike"
}
```

```json
{
  "expr": "clamp_max(sowa_gpu_activity_active + (sowa_gpu_activity_recent > bool 0), 1)",
  "legendFormat": "GPU Activity"
}
```

```json
{
  "expr": "(sowa_gpu_utilization_percent * sowa_gpu_utilization_available) + ((sowa_gpu_utilization_available - 1) * 1)",
  "legendFormat": "GPU Utilization"
}
```

Why it matters:
- shows that the observability layer is not generic boilerplate
- directly reflects the custom telemetry model built for the demo

## 11. Submission Notes

Recommended use for hackathon submission:

- include this document as an appendix or "selected source code" section
- include the main project summary from `hackathon-submission.md` as the narrative portion
- export this Markdown file to PDF from VS Code preview, Typora, or a browser-based Markdown renderer

Suggested attachment set:

- `hackathon-submission.md` for narrative and architecture
- `hackathon_code_appendix.md` for code evidence

Key explanation for judges:

- the local notebook node is real
- the remote cluster nodes are simulated for placement storytelling
- the telemetry, GPU load, model loading, API, and UI interactions are real and executable
