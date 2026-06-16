#!/usr/bin/env python3
"""FastAPI backend for the SOWA demo."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sowa.metrics import get_cluster_snapshot
from sowa.workflow import agent_app
from sowa.workloads import launch_workload_for_request, trigger_real_gpu_spike

app = FastAPI(
    title="SOWA API",
    version="1.0",
    description="Self-Optimizing Workload Agent API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

workflow_graph = agent_app
current_state: dict = {}


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
    risk_details: str = ""
    simulated_cluster_snapshot: str
    telemetry_source: str = ""


def initial_state_dict() -> dict:
    """Build the internal workflow state for a fresh session."""
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


def refresh_snapshot() -> None:
    """Refresh telemetry-related fields without advancing the simulator."""
    global current_state
    snapshot = get_cluster_snapshot(
        current_state.get("last_decision", "None"),
        advance_simulation=False,
    )
    current_state.update(
        {
            "cluster_status_text": snapshot["cluster_status_text"],
            "local_telemetry_text": snapshot["local_telemetry_text"],
            "telemetry_source": snapshot["telemetry_source"],
            "node_loads": snapshot["node_loads"],
        }
    )


def serialize_state(state: dict) -> SOWAState:
    """Map internal workflow state to the React UI response shape."""
    return SOWAState(
        cluster_status=state.get("cluster_status_text", ""),
        current_workload=state.get("current_workload", ""),
        devops_reasoning=state.get("devops_reasoning", ""),
        last_decision=state.get("last_decision", "None"),
        performance_summary=state.get("performance_summary", ""),
        k8s_manifest=state.get("yaml_output", ""),
        local_telemetry=state.get("local_telemetry_text", ""),
        tool_trace=state.get("tool_trace", ""),
        risk_level=state.get("risk_level", "Low"),
        risk_details="",
        simulated_cluster_snapshot=state.get("cluster_status_text", ""),
        telemetry_source=state.get("telemetry_source", ""),
    )


@app.on_event("startup")
async def startup_event():
    global current_state
    current_state = initial_state_dict()


@app.get("/api/health")
async def healthcheck():
    return {"status": "ok"}


@app.get("/api/state")
async def get_current_state() -> SOWAState:
    return serialize_state(current_state)


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


@app.post("/api/run-current-workload")
async def run_current_workload_locally():
    global current_state
    message = launch_workload_for_request(current_state.get("current_workload", ""))
    refresh_snapshot()
    return {"status": "ok", "message": message, "state": serialize_state(current_state)}


@app.post("/api/refresh-telemetry")
async def refresh_local_telemetry() -> SOWAState:
    refresh_snapshot()
    return serialize_state(current_state)


@app.post("/api/reset")
async def reset_demo() -> SOWAState:
    global current_state
    current_state = initial_state_dict()
    return serialize_state(current_state)


frontend_dist_path = Path(__file__).parent / "frontend" / "dist"
if frontend_dist_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dist_path)), name="static")

    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        index_path = frontend_dist_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"detail": "Not Found"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
