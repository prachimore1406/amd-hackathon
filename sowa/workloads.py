import os
import threading
import time
from pathlib import Path
from typing import List

try:
    import torch
except ImportError:  # pragma: no cover - handled at runtime when ML deps are absent
    torch = None


_ACTIVE_WORKLOADS: List[str] = []
_ACTIVE_GPU_ACTIVITIES: List[str] = []
_LOCK = threading.Lock()
_LAST_GPU_SPIKE_AT = 0.0
_LAST_GPU_ACTIVITY_AT = 0.0
_GPU_UTILIZATION_PERCENT = 0.0
_GPU_UTILIZATION_AVAILABLE = 0
_GPU_SPIKE_WINDOW_SEC = 20
_GPU_ACTIVITY_WINDOW_SEC = 45
_GPU_ACTIVITY_THRESHOLD_PERCENT = 5.0
_GPU_SPIKE_THRESHOLD_PERCENT = 70.0


def _default_textfile_dir() -> Path:
    env_dir = os.getenv("SOWA_TEXTFILE_DIR")
    if env_dir:
        return Path(env_dir).expanduser()

    project_root = Path(__file__).resolve().parent.parent
    bundled_exporters = sorted(project_root.glob("node_exporter-*/textfile_collector"))
    if bundled_exporters:
        return bundled_exporters[0]

    return project_root / ".sowa_metrics"


# Textfile collector directory for node_exporter. Falls back to a local project dir
# so the backend can still import and run without the optional monitoring stack.
TEXTFILE_DIR = _default_textfile_dir()
TEXTFILE_DIR.mkdir(parents=True, exist_ok=True)
TEXTFILE_PATH = TEXTFILE_DIR / "sowa_gpu_spike.prom"


def _is_gpu_workload(name: str) -> bool:
    return "[GPU]" in name or "[GPU-SPIKE]" in name


def _update_gpu_metrics():
    """Write GPU spike and general GPU activity status to the Prometheus textfile collector."""
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
        seconds_since_spike = time.time() - _LAST_GPU_SPIKE_AT
        seconds_since_activity = time.time() - _LAST_GPU_ACTIVITY_AT
        gpu_utilization_percent = _GPU_UTILIZATION_PERCENT
        gpu_utilization_available = _GPU_UTILIZATION_AVAILABLE
        recent_spike = 0 < seconds_since_spike <= _GPU_SPIKE_WINDOW_SEC
        recent_activity = 0 < seconds_since_activity <= _GPU_ACTIVITY_WINDOW_SEC

    # Write metric in prometheus format
    with open(TEXTFILE_PATH, "w") as f:
        f.write(f"# HELP sowa_gpu_spike_active Indicates if a SOWA demo GPU spike is currently active\n")
        f.write(f"# TYPE sowa_gpu_spike_active gauge\n")
        f.write(f"sowa_gpu_spike_active {1 if active_spike else 0}\n")
        f.write(f"# HELP sowa_gpu_spike_recent Seconds since last SOWA demo GPU spike (0 if > {_GPU_SPIKE_WINDOW_SEC}s)\n")
        f.write(f"# TYPE sowa_gpu_spike_recent gauge\n")
        f.write(f"sowa_gpu_spike_recent {seconds_since_spike if recent_spike else 0}\n")
        f.write("# HELP sowa_gpu_activity_active Indicates if general GPU activity is currently active\n")
        f.write("# TYPE sowa_gpu_activity_active gauge\n")
        f.write(f"sowa_gpu_activity_active {1 if active_gpu_activity else 0}\n")
        f.write(f"# HELP sowa_gpu_activity_recent Seconds since last observed GPU activity (0 if > {_GPU_ACTIVITY_WINDOW_SEC}s)\n")
        f.write("# TYPE sowa_gpu_activity_recent gauge\n")
        f.write(f"sowa_gpu_activity_recent {seconds_since_activity if recent_activity else 0}\n")
        f.write("# HELP sowa_gpu_activity_count Number of active SOWA GPU activities currently tracked\n")
        f.write("# TYPE sowa_gpu_activity_count gauge\n")
        f.write(f"sowa_gpu_activity_count {int(active_gpu_work) + len(_ACTIVE_GPU_ACTIVITIES)}\n")
        f.write("# HELP sowa_gpu_utilization_percent Current GPU utilization percentage from rocm-smi\n")
        f.write("# TYPE sowa_gpu_utilization_percent gauge\n")
        f.write(f"sowa_gpu_utilization_percent {gpu_utilization_percent:.2f}\n")
        f.write("# HELP sowa_gpu_utilization_available Indicates whether GPU utilization telemetry is currently available\n")
        f.write("# TYPE sowa_gpu_utilization_available gauge\n")
        f.write(f"sowa_gpu_utilization_available {gpu_utilization_available}\n")


_update_gpu_metrics()


def _add_job(name: str) -> None:
    with _LOCK:
        _ACTIVE_WORKLOADS.append(name)
        if _is_gpu_workload(name):
            _mark_gpu_activity_event_locked()
    _update_gpu_metrics()


def _remove_job(name: str) -> None:
    with _LOCK:
        if name in _ACTIVE_WORKLOADS:
            _ACTIVE_WORKLOADS.remove(name)
        if _is_gpu_workload(name):
            _mark_gpu_activity_event_locked()
    _update_gpu_metrics()


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
    _update_gpu_metrics()


def _mark_gpu_activity_event_locked() -> None:
    global _LAST_GPU_ACTIVITY_AT
    _LAST_GPU_ACTIVITY_AT = time.time()


def mark_gpu_activity_event() -> None:
    with _LOCK:
        _mark_gpu_activity_event_locked()
    _update_gpu_metrics()


def begin_gpu_activity(name: str) -> None:
    with _LOCK:
        if name not in _ACTIVE_GPU_ACTIVITIES:
            _ACTIVE_GPU_ACTIVITIES.append(name)
        _mark_gpu_activity_event_locked()
    _update_gpu_metrics()


def end_gpu_activity(name: str) -> None:
    with _LOCK:
        if name in _ACTIVE_GPU_ACTIVITIES:
            _ACTIVE_GPU_ACTIVITIES.remove(name)
        _mark_gpu_activity_event_locked()
    _update_gpu_metrics()


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
    if 0 < seconds_since_spike <= _GPU_SPIKE_WINDOW_SEC:
        return f"Recent GPU contention detected on the local notebook node ({int(seconds_since_spike)}s ago)."
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
    if torch is None:
        return "PyTorch is not installed in this environment, so the real GPU spike could not start."
    if not torch.cuda.is_available():
        return "CUDA/ROCm device is not available in this session, so the real GPU spike could not start."

    with _LOCK:
        spike_running = any("[GPU-SPIKE]" in job for job in _ACTIVE_WORKLOADS)

    if spike_running:
        return "A real GPU spike is already running. Refresh telemetry to observe the current contention event."

    thread = threading.Thread(target=_gpu_spike_job, daemon=True)
    thread.start()
    return "Started a bounded real GPU spike on the notebook GPU for demo purposes. Refresh telemetry in a few seconds to observe the contention signal."
