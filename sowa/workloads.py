import threading
import time
from pathlib import Path
from typing import List

import torch


_ACTIVE_WORKLOADS: List[str] = []
_LOCK = threading.Lock()
_LAST_GPU_SPIKE_AT = 0.0
_GPU_SPIKE_WINDOW_SEC = 20
# Textfile collector directory for node_exporter
TEXTFILE_DIR = Path.home() / "node_exporter-1.8.2.linux-amd64" / "textfile_collector"
TEXTFILE_DIR.mkdir(parents=True, exist_ok=True)
TEXTFILE_PATH = TEXTFILE_DIR / "sowa_gpu_spike.prom"


def _update_gpu_spike_metric():
    """Write GPU spike status to prometheus textfile collector"""
    with _LOCK:
        active_spike = any("[GPU-SPIKE]" in job for job in _ACTIVE_WORKLOADS)
        seconds_since_spike = time.time() - _LAST_GPU_SPIKE_AT
        recent_spike = 0 < seconds_since_spike <= _GPU_SPIKE_WINDOW_SEC

    # Write metric in prometheus format
    with open(TEXTFILE_PATH, "w") as f:
        f.write(f"# HELP sowa_gpu_spike_active Indicates if a SOWA demo GPU spike is currently active\n")
        f.write(f"# TYPE sowa_gpu_spike_active gauge\n")
        f.write(f"sowa_gpu_spike_active {1 if active_spike else 0}\n")
        f.write(f"# HELP sowa_gpu_spike_recent Seconds since last SOWA demo GPU spike (0 if > {_GPU_SPIKE_WINDOW_SEC}s)\n")
        f.write(f"# TYPE sowa_gpu_spike_recent gauge\n")
        f.write(f"sowa_gpu_spike_recent {seconds_since_spike if recent_spike else 0}\n")


def _add_job(name: str) -> None:
    with _LOCK:
        _ACTIVE_WORKLOADS.append(name)
    _update_gpu_spike_metric()


def _remove_job(name: str) -> None:
    with _LOCK:
        if name in _ACTIVE_WORKLOADS:
            _ACTIVE_WORKLOADS.remove(name)
    _update_gpu_spike_metric()


def get_active_workloads_text() -> str:
    with _LOCK:
        return "\n".join(_ACTIVE_WORKLOADS) if _ACTIVE_WORKLOADS else "No active local workloads"


def get_active_workload_count() -> int:
    with _LOCK:
        return len(_ACTIVE_WORKLOADS)


def _mark_gpu_spike_event() -> None:
    global _LAST_GPU_SPIKE_AT
    with _LOCK:
        _LAST_GPU_SPIKE_AT = time.time()
    _update_gpu_spike_metric()


def get_recent_accelerator_event_text() -> str:
    with _LOCK:
        active_spike = any("[GPU-SPIKE]" in job for job in _ACTIVE_WORKLOADS)
        seconds_since_spike = time.time() - _LAST_GPU_SPIKE_AT

    if active_spike:
        return "Real GPU spike is active on the local notebook node."
    if 0 < seconds_since_spike <= _GPU_SPIKE_WINDOW_SEC:
        return f"Recent real GPU spike detected on the local notebook node ({int(seconds_since_spike)}s ago)."
    return "No recent local accelerator contention event."


def _cpu_job(name: str, duration_sec: int = 12) -> None:
    _add_job(f"{name} [CPU]")
    try:
        end_time = time.time() + duration_sec
        value = 0.0
        while time.time() < end_time:
            for i in range(200000):
                value += ((i % 97) * 1.0001) / (i + 1)
    finally:
        _remove_job(f"{name} [CPU]")


def _gpu_job(name: str, duration_sec: int = 12) -> None:
    label = f"{name} [GPU]"
    _add_job(label)
    try:
        if not torch.cuda.is_available():
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


def _gpu_spike_job(duration_sec: int = 4, matrix_size: int = 4096, warmup_iterations: int = 6) -> None:
    label = "Demo-GPU-Spike [GPU-SPIKE]"
    _add_job(label)
    try:
        if not torch.cuda.is_available():
            time.sleep(1)
            return

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
        _mark_gpu_spike_event()
    finally:
        _remove_job(label)


def _memory_job(name: str, duration_sec: int = 10) -> None:
    label = f"{name} [MEMORY]"
    _add_job(label)
    try:
        blocks = []
        end_time = time.time() + duration_sec
        while time.time() < end_time:
            blocks.append(bytearray(10 * 1024 * 1024))
            if len(blocks) > 8:
                blocks.pop(0)
            time.sleep(0.5)
    finally:
        _remove_job(label)


def launch_workload_for_request(workload_request: str) -> str:
    if not workload_request:
        return "No workload selected yet. Click 'Run Next Simulation Turn' first."

    workload_name = workload_request.split("|")[0].replace("Name:", "").strip()
    workload_type = workload_request.split("|")[1].replace("Type:", "").strip().lower()

    if "ml training" in workload_type:
        target = _gpu_job
        job_type = "GPU"
    elif "data processing" in workload_type:
        target = _memory_job
        job_type = "MEMORY"
    else:
        target = _cpu_job
        job_type = "CPU"

    thread = threading.Thread(target=target, args=(workload_name,), daemon=True)
    thread.start()
    return f"Started local {job_type} workload for '{workload_name}'. Refresh telemetry to observe impact."


def trigger_real_gpu_spike() -> str:
    with _LOCK:
        spike_running = any("[GPU-SPIKE]" in job for job in _ACTIVE_WORKLOADS)

    if spike_running:
        return "A real GPU spike is already running. Refresh telemetry to observe the current contention event."

    thread = threading.Thread(target=_gpu_spike_job, daemon=True)
    thread.start()
    if torch.cuda.is_available():
        return "Started a bounded real GPU spike on the notebook GPU for demo purposes. Refresh telemetry in a few seconds to observe the contention signal."
    return "CUDA/ROCm device is not available in this session, so the real GPU spike could not start."
