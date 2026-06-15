import random
import subprocess
import time
from typing import Dict

import psutil

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from sowa.workloads import (
    get_active_workload_count,
    get_active_workloads_text,
    get_recent_accelerator_event_text,
)

# Prometheus configuration
PROMETHEUS_URL = "http://localhost:9090"  # Default to localhost for single pod demo
USE_PROMETHEUS = False  # Can be toggled later


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
_GPU_SPIKE_WINDOW_SEC = 20


def get_recent_gpu_event() -> str:
    return get_recent_accelerator_event_text()


def get_live_telemetry(last_decision: str = "None", advance_simulation: bool = False) -> Dict[str, str]:
    return get_cluster_snapshot(last_decision, advance_simulation=advance_simulation)


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
    # Try Prometheus first if enabled
    if USE_PROMETHEUS:
        prom_telemetry = _read_prometheus_telemetry()
        # Check if Prometheus actually worked (CPU > 0 or valid source)
        if "prometheus" in prom_telemetry["telemetry_source"] and float(prom_telemetry["cpu_percent"]) >= 0:
            return prom_telemetry

    # Fallback to original local telemetry
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


def _query_prometheus(query: str, timeout: float = 5.0) -> Dict:
    """Execute a PromQL query against Prometheus."""
    if not REQUESTS_AVAILABLE:
        return {"status": "error", "data": {"result": []}}
    params = {"query": query, "time": time.time()}
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Prometheus query failed: {e}")
        return {"status": "error", "data": {"result": []}}


def _read_prometheus_telemetry() -> Dict[str, str]:
    """Read telemetry from Prometheus (fallback to local if failed)."""
    # Query node CPU utilization from node_exporter
    cpu_query = '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
    cpu_results = _query_prometheus(cpu_query)

    # Query node memory utilization
    memory_query = '100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100)'
    memory_results = _query_prometheus(memory_query)

    # Parse results
    telemetry_lines = []
    cpu_util = 0.0
    mem_util = 0.0

    if cpu_results.get("status") == "success" and len(cpu_results["data"]["result"]) > 0:
        cpu_util = float(cpu_results["data"]["result"][0]["value"][1])
        telemetry_lines.append(f"Local Pod | CPU: {cpu_util:.1f}%")

    if memory_results.get("status") == "success" and len(memory_results["data"]["result"]) > 0:
        mem_util = float(memory_results["data"]["result"][0]["value"][1])
        telemetry_lines.append(f"Local Pod | Memory: {mem_util:.1f}%")

    active_jobs = get_active_workloads_text()
    accelerator_event = get_recent_accelerator_event_text()
    gpu = _read_rocm_smi()

    if gpu["available"] == "true":
        telemetry_lines.append(f"Recent Accelerator Event: {accelerator_event}")
        telemetry_lines.append(f"AMD GPU Telemetry:\n{gpu['details']}")
        source = "prometheus+rocm-smi"
    else:
        telemetry_lines.append(f"Recent Accelerator Event: {accelerator_event}")
        source = "prometheus"

    return {
        "cpu_percent": f"{cpu_util:.1f}",
        "memory_percent": f"{mem_util:.1f}",
        "telemetry_source": source,
        "local_telemetry_text": "\n".join(telemetry_lines),
        "active_workload_count": str(get_active_workload_count()),
        "accelerator_event": accelerator_event,
    }


def get_next_workload(previous_workload: str) -> str:
    choices = [w for w in WORKLOADS if w != previous_workload] or WORKLOADS
    return random.choice(choices)
