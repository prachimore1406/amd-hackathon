#!/usr/bin/env python3
"""FastAPI backend for SOWA (Self-Optimizing Workload Agent)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from sowa.workflow import create_workflow
from sowa.workloads import (
    run_stress_cpu,
    run_stress_memory,
    run_stress_gpu,
    run_stress_all,
    mark_gpu_spike,
    stop_stress_jobs,
    get_active_jobs,
    get_recent_gpu_event,
    LOCAL_NODE_NAME,
    TEXTFILE_DIR
)
from sowa.metrics import get_cluster_snapshot, get_recent_accelerator_event_text

app = FastAPI(title="SOWA API", version="1.0", description="Self-Optimizing Workload Agent API")

# Enable CORS for React frontend (allow all origins for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state management
current_state: Optional[dict] = None
is_reset_flag = False

# Initialize the workflow graph
workflow_graph = create_workflow()


class SOWAState(BaseModel):
    cluster_status: str
    current_workload: str
    devops_reasoning: str
    last_decision: str
    performance_summary: str
    k8s_manifest: str
    local_telemetry: str
    tool_trace: str
    risk_level: str
    risk_details: str
    simulated_cluster_snapshot: str


@app.on_event("startup")
async def startup_event():
    global current_state
    current_state = initial_state_dict()


def initial_state_dict() -> dict:
    """Create an initial, empty state dict
    """
    snapshot = get_cluster_snapshot("None", False)
    return {
        "cluster_status": "",
        "current_workload": "",
        "devops_reasoning": "",
        "last_decision": "None",
        "performance_summary": "",
        "k8s_manifest": "",
        "local_telemetry": snapshot,
        "tool_trace": "",
        "risk_level": "Low",
        "risk_details": "",
        "simulated_cluster_snapshot": snapshot
    }


@app.get("/api/state")
async def get_current_state() -> SOWAState:
    return SOWAState(**current_state)


@app.post("/api/run-turn")
async def run_next_turn():
    """Run a single simulation turn!
    """
    global current_state
    # Convert state dict to types for graph
    from sowa.state import MultiAgentState

    state_dict = current_state.copy()

    # Run workflow graph
    result = workflow_graph.invoke(MultiAgentState(**state_dict))

    current_state = {k: v for k, v in result.items() if k in state_dict}
    return SOWAState(**current_state)


@app.post("/api/trigger-gpu-spike")
async def trigger_gpu_spike():
    """Mark a GPU spike event and optionally runs a real GPU stress test!
    """
    mark_gpu_spike()
    run_stress_gpu()
    return {"status": "ok", "message": "GPU spike triggered"}


@app.post("/api/run-current-workload")
async def run_current_workload_locally():
    """Run current workload's stress job locally!
    """
    global current_state
    workload_name = current_state.get("current_workload", "General Web Server")
    if "training" in workload_name.lower() or "ml" in workload_name.lower():
        run_stress_gpu()
    elif "memory" in workload_name.lower():
        run_stress_memory()
    else:
        run_stress_cpu()
    return {"status": "ok", "message": "Workload stress running locally"}


@app.post("/api/refresh-telemetry")
async def refresh_local_telemetry():
    """Refresh local telemetry
    """
    global current_state
    snapshot = get_cluster_snapshot(current_state.get("last_decision", "None"), False)
    current_state["local_telemetry"] = snapshot
    current_state["simulated_cluster_snapshot"] = snapshot
    return SOWAState(**current_state)


@app.post("/api/reset")
async def reset_demo():
    """Reset the entire demo
    """
    global current_state
    current_state = initial_state_dict()
    stop_stress_jobs()
    return SOWAState(**current_state)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
