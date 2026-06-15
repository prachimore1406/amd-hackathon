import random
import subprocess
from typing import Dict

import psutil

from sowa.workloads import (
    get_active_workload_count,
    get_active_workloads_text,
    get_recent_accelerator_event_text,
)


WORKLOADS = [
    "Name: User-Auth-API | Type: Web Serving",
    "Name: Fraud-Detection-Training | Type: ML Training",
    "Name: Recommendation-Batch-Job | Type: Data Processing",
    "Name: Image-Classifier-Finetune | Type: ML Training",
    "Name: Checkout-Service | Type: Web Serving",
]

_SIM_NODES = {
    "AMD-EPYC-CPU": 35,
    "AMD-Instinct-GPU": 20,
    "General-VM": 55,
}
LOCAL_NODE_NAME = "Local-Notebook-Node"


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _read_rocm_smi() -> Dict[str, str]:
    try:
        result = subprocess.run(
            ["rocm-smi", "--showuse", "--showmemuse", "--showtemp", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"available": "false", "details": "rocm-smi unavailable"}
        return {"available": "true", "details": result.stdout.strip()[:1200]}
    except FileNotFoundError:
        return {"available": "false", "details": "rocm-smi not installed"}


def _read_local_telemetry() -> Dict[str, str]:
    cpu = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory().percent
    gpu = _read_rocm_smi()
    active_jobs = get_active_workloads_text()
    accelerator_event = get_recent_accelerator_event_text()

    if gpu["available"] == "true":
        source = "local-cpu-memory+rocm-smi"
        telemetry = (
            f"Local Notebook Node | CPU: {cpu:.1f}% | Memory: {memory:.1f}%\n"
            f"Active Local Workloads:\n{active_jobs}\n"
            f"Recent Accelerator Event: {accelerator_event}\n"
            f"AMD GPU Telemetry:\n{gpu['details']}"
        )
    else:
        source = "local-cpu-memory"
        telemetry = (
            f"Local Notebook Node | CPU: {cpu:.1f}% | Memory: {memory:.1f}%\n"
            f"Active Local Workloads:\n{active_jobs}\n"
            f"Recent Accelerator Event: {accelerator_event}\n"
            f"AMD GPU Telemetry: {gpu['details']}"
        )

    return {
        "cpu_percent": f"{cpu:.1f}",
        "memory_percent": f"{memory:.1f}",
        "telemetry_source": source,
        "local_telemetry_text": telemetry,
        "active_workload_count": str(get_active_workload_count()),
        "accelerator_event": accelerator_event,
    }


def _current_node_loads(local: Dict[str, str]) -> Dict[str, int]:
    active_jobs = int(local["active_workload_count"])
    event_bonus = 30 if "active" in local["accelerator_event"].lower() else 12 if "recent real gpu spike" in local["accelerator_event"].lower() else 0
    local_node_load = _clamp(max(float(local["cpu_percent"]), float(local["memory_percent"])) + (active_jobs * 8) + event_bonus)
    return {
        LOCAL_NODE_NAME: int(local_node_load),
        **_SIM_NODES,
    }


def _update_simulated_nodes(last_decision: str) -> str:
    for node in list(_SIM_NODES.keys()):
        _SIM_NODES[node] = _clamp(_SIM_NODES[node] - random.randint(0, 8))

    if last_decision in _SIM_NODES:
        _SIM_NODES[last_decision] = _clamp(_SIM_NODES[last_decision] + random.randint(12, 28))

    return ", ".join(f"{name} (Node Load: {load}%)" for name, load in _SIM_NODES.items())


def _simulated_node_text() -> str:
    return ", ".join(f"{name} (Node Load: {load}%)" for name, load in _SIM_NODES.items())


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


def get_next_workload(previous_workload: str) -> str:
    choices = [w for w in WORKLOADS if w != previous_workload] or WORKLOADS
    return random.choice(choices)
