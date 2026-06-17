#!/usr/bin/env python3
"""Automated setup for the Linux-based AMD Developer Cloud demo environment."""

import os
import platform
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from pathlib import Path

# Configuration
PROJECT_ROOT = Path(__file__).resolve().parent


def default_base_dir() -> Path:
    env_dir = os.getenv("SOWA_BASE_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    if Path("/workspace/shared").exists():
        return Path("/workspace/shared")
    return PROJECT_ROOT / ".sowa_runtime"


BASE_DIR = default_base_dir()
IS_LINUX = platform.system() == "Linux"

NODE_VERSION = "20.15.0"
PROM_VERSION = "2.52.0"
NODE_EXPORTER_VERSION = "1.8.2"
GRAFANA_VERSION = "11.1.0"

# We'll find the actual directories after extraction, don't hardcode the full path yet
LOG_DIR = BASE_DIR / "sowa_prom_logs"
GRAFANA_PROVISIONING_DIR = BASE_DIR / "grafana-provisioning"
GRAFANA_DASHBOARDS_DIR = BASE_DIR / "grafana-dashboards"

# Process trackers
processes = []
process_metadata = {}


def kill_existing_processes():
    """Kill any existing processes that might be using our ports or are our services!"""
    if not IS_LINUX:
        print("Skipping process cleanup because automatic service management is only supported on Linux.")
        return

    current_pid = str(os.getpid())

    # First kill by process name (but NOT our own Python process!)
    service_names = ["prometheus", "node_exporter", "grafana-server"]
    for name in service_names:
        try:
            # Use pgrep first to get PIDs
            result = subprocess.run(["pgrep", "-f", name], capture_output=True, text=True, check=False)
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                if pid and pid != current_pid:
                    try:
                        subprocess.run(["kill", "-9", pid], capture_output=True, check=False)
                    except Exception:
                        pass
            time.sleep(0.5)
        except Exception:
            pass

    # Then kill by port
    ports = [9090, 9100, 3000, 8000]
    for port in ports:
        try:
            # Try lsof first to get PIDs so we can skip our own process
            try:
                result = subprocess.run(["lsof", "-t", f"-i:{port}"], capture_output=True, text=True, check=False)
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    if pid and pid != current_pid:
                        try:
                            subprocess.run(["kill", "-9", pid], capture_output=True, check=False)
                        except Exception:
                            pass
                time.sleep(0.5)
            except FileNotFoundError:
                # Try using fuser if lsof not found
                subprocess.run(["fuser", "-k", "-9", f"{port}/tcp"], capture_output=True, text=True, check=False)
                time.sleep(0.5)
        except Exception as e:
            print(f"Warning: Could not kill processes on port {port}: {e}")


def cleanup(signum, frame):
    """Cleanup all running processes on exit!"""
    print("\nShutting down all services...")
    for proc in processes:
        try:
            print(f"Stopping {proc.args[0]} (PID {proc.pid})")
            proc.terminate()
            proc.wait(timeout=5)
        except Exception as e:
            print(f"Error stopping process: {e}")
            try:
                proc.kill()
            except Exception:
                pass
        metadata = process_metadata.get(proc.pid, {})
        log_handle = metadata.get("log_handle")
        if log_handle:
            try:
                log_handle.close()
            except Exception:
                pass
    print("All services stopped!")
    sys.exit(0)


def register_process(proc, service_name: str, log_path: Path, log_handle=None, stream_thread=None) -> None:
    processes.append(proc)
    process_metadata[proc.pid] = {
        "name": service_name,
        "log_path": log_path,
        "log_handle": log_handle,
        "stream_thread": stream_thread,
    }


def print_log_tail(service_name: str, log_path: Path, tail_lines: int = 80) -> None:
    print(f"\n----- {service_name} log: {log_path} -----")
    try:
        if not log_path.exists():
            print("Log file does not exist yet.")
            return

        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            print("Log file is empty.")
            return

        for line in lines[-tail_lines:]:
            print(line)
    except Exception as exc:
        print(f"Could not read log file: {exc}")
    finally:
        print(f"----- end {service_name} log -----\n")


def _stream_process_output(pipe, log_handle, service_name: str) -> None:
    """Mirror a subprocess stream to both the terminal and the service log file."""
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            log_handle.write(line)
            log_handle.flush()
            print(f"[{service_name}] {line}", end="")
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def launch_service(
    command,
    cwd: Path,
    service_name: str,
    log_path: Path,
    env: dict | None = None,
    stream_to_console: bool = False,
):
    """Start a service, always persist logs, and optionally mirror them to stdout."""
    if stream_to_console:
        log_handle = open(log_path, "w", encoding="utf-8", buffering=1)
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        stream_thread = threading.Thread(
            target=_stream_process_output,
            args=(proc.stdout, log_handle, service_name),
            daemon=True,
        )
        stream_thread.start()
        return proc, log_handle, stream_thread

    with open(log_path, "w") as log_handle:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=log_handle,
            stderr=log_handle,
        )
    return proc, None, None


def find_extracted_dir(base_name: str):
    """Find the extracted directory by looking for directories that start with the base name"""
    for item in BASE_DIR.iterdir():
        if item.is_dir() and item.name.startswith(base_name):
            return item
    return None


def download_and_extract(url: str, base_name: str, tar_name: str):
    """Download and extract a tar.gz/tar.xz file, and find the correct directory name"""
    tar_path = BASE_DIR / tar_name
    if not tar_path.exists():
        print(f"Downloading: {url}")
        try:
            urllib.request.urlretrieve(url, str(tar_path))
        except Exception as e:
            print(f"Download failed: {e}")
            sys.exit(1)
    
    # Check if we already have a valid extracted directory
    extracted_dir = find_extracted_dir(base_name)
    if not extracted_dir:
        print(f"Extracting: {tar_path.name}")
        try:
            mode = "r:xz" if tar_name.endswith(".xz") else "r:gz"
            with tarfile.open(tar_path, mode) as tar:
                try:
                    tar.extractall(path=BASE_DIR, filter="data")
                except TypeError:
                    tar.extractall(path=BASE_DIR)
            extracted_dir = find_extracted_dir(base_name)
            if not extracted_dir:
                print(f"Error: Could not find extracted directory for {base_name}")
                sys.exit(1)
        except Exception as e:
            print(f"Extract failed: {e}")
            sys.exit(1)
    
    print(f"Found directory: {extracted_dir.name}")
    return extracted_dir


def latest_mtime(paths) -> float:
    latest = 0.0
    for path in paths:
        if path.exists():
            latest = max(latest, path.stat().st_mtime)
    return latest


def frontend_build_needs_refresh(frontend_dir: Path, frontend_dist: Path) -> bool:
    """Rebuild when the output is missing or older than source/config inputs."""
    dist_index = frontend_dist / "index.html"
    dist_assets = frontend_dist / "assets"
    if not frontend_dist.exists() or not dist_index.exists() or not dist_assets.exists():
        return True

    source_paths = [
        frontend_dir / "package.json",
        frontend_dir / "vite.config.ts",
        frontend_dir / "index.html",
        *frontend_dir.glob("src/**/*"),
    ]
    return latest_mtime(source_paths) > dist_index.stat().st_mtime


def get_node_npm_paths():
    """Get paths to node and npm, installing if necessary"""
    # Check if node/npm are already in PATH and work
    try:
        node_ver = subprocess.check_output(["node", "-v"], text=True, stderr=subprocess.STDOUT).strip()
        npm_ver = subprocess.check_output(["npm", "-v"], text=True, stderr=subprocess.STDOUT).strip()
        print(f"Found system Node.js: {node_ver}, npm: {npm_ver}")
        return "node", "npm"
    except Exception:
        pass

    # Check our local installation
    node_dir = find_extracted_dir("node-")
    if node_dir:
        node_cmd = node_dir / "bin" / "node"
        npm_cmd = node_dir / "bin" / "npm"
        if node_cmd.exists() and npm_cmd.exists():
            node_ver = subprocess.check_output(
                [str(node_cmd), "-v"],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
            npm_ver = subprocess.check_output(
                [str(npm_cmd), "-v"],
                text=True,
                stderr=subprocess.STDOUT,
                env=build_node_env(str(node_cmd)),
            ).strip()
            print(f"Found local Node.js installation: {node_dir.name} ({node_ver}, npm {npm_ver})")
            return str(node_cmd), str(npm_cmd)

    if not IS_LINUX:
        raise RuntimeError(
            "Node.js/npm are not available and automatic installation is only supported on Linux. "
            "Install Node.js manually or run this script in the AMD Developer Cloud Linux environment."
        )

    # Install Node.js
    print("\nNode.js/npm not found! Installing now...")
    node_url = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz"
    node_dir = download_and_extract(node_url, "node-", f"node-v{NODE_VERSION}-linux-x64.tar.xz")
    node_cmd = node_dir / "bin" / "node"
    npm_cmd = node_dir / "bin" / "npm"
    node_ver = subprocess.check_output(
        [str(node_cmd), "-v"],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()
    npm_ver = subprocess.check_output(
        [str(npm_cmd), "-v"],
        text=True,
        stderr=subprocess.STDOUT,
        env=build_node_env(str(node_cmd)),
    ).strip()
    print(f"Installed local Node.js: {node_ver}, npm: {npm_ver}")
    return str(node_cmd), str(npm_cmd)


def build_node_env(node_cmd: str) -> dict:
    """Ensure npm can find the matching node binary even when Node is locally installed."""
    env = os.environ.copy()
    node_bin_dir = str(Path(node_cmd).resolve().parent) if node_cmd != "node" else ""
    if node_bin_dir:
        env["PATH"] = f"{node_bin_dir}{os.pathsep}{env.get('PATH', '')}"
    return env


def build_grafana_env() -> dict:
    """Configure Grafana to work behind Jupyter's proxied port forwarding."""
    env = os.environ.copy()
    public_base_url = get_public_base_url(env)
    grafana_public_url = build_public_service_url(public_base_url, 3000)
    # Jupyter's /proxy/<port>/ handler already rewrites requests to Grafana's
    # root path, so enabling Grafana's own subpath mode can create redirect
    # loops. We still set an external root URL so generated asset links point to
    # the browser-visible proxy URL.
    env["GF_SERVER_SERVE_FROM_SUB_PATH"] = "false"
    env["GF_SERVER_ENFORCE_DOMAIN"] = "false"
    env["GF_SERVER_ROOT_URL"] = grafana_public_url
    # Avoid Grafana's login redirect flow inside the notebook proxy. For this
    # demo stack, anonymous admin access is acceptable and keeps dashboards
    # reachable even when /login does not proxy cleanly.
    env["GF_AUTH_ANONYMOUS_ENABLED"] = "true"
    env["GF_AUTH_ANONYMOUS_ORG_ROLE"] = "Admin"
    env["GF_AUTH_DISABLE_LOGIN_FORM"] = "true"
    env["GF_PATHS_PROVISIONING"] = str(GRAFANA_PROVISIONING_DIR)
    return env


def write_grafana_provisioning() -> Path:
    """Provision the Prometheus datasource and the bundled SOWA dashboard."""
    dashboards_src = PROJECT_ROOT / "grafana_sowa_dashboard.json"
    if not dashboards_src.exists():
        raise FileNotFoundError(f"Bundled dashboard not found: {dashboards_src}")

    datasources_dir = GRAFANA_PROVISIONING_DIR / "datasources"
    dashboards_dir = GRAFANA_PROVISIONING_DIR / "dashboards"
    datasources_dir.mkdir(parents=True, exist_ok=True)
    dashboards_dir.mkdir(parents=True, exist_ok=True)
    GRAFANA_DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)

    provisioned_dashboard = GRAFANA_DASHBOARDS_DIR / "sowa_dashboard.json"
    provisioned_dashboard.write_text(
        dashboards_src.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    datasource_yaml = (
        "apiVersion: 1\n"
        "datasources:\n"
        "  - name: Prometheus\n"
        "    type: prometheus\n"
        "    uid: prometheus\n"
        "    access: proxy\n"
        "    url: http://127.0.0.1:9090\n"
        "    isDefault: true\n"
        "    editable: true\n"
    )
    (datasources_dir / "sowa-prometheus.yaml").write_text(datasource_yaml, encoding="utf-8")

    dashboards_yaml = (
        "apiVersion: 1\n"
        "providers:\n"
        "  - name: SOWA Dashboards\n"
        "    orgId: 1\n"
        "    folder: SOWA\n"
        "    type: file\n"
        "    disableDeletion: false\n"
        "    allowUiUpdates: true\n"
        "    updateIntervalSeconds: 10\n"
        "    options:\n"
        f"      path: {GRAFANA_DASHBOARDS_DIR}\n"
    )
    (dashboards_dir / "sowa-dashboards.yaml").write_text(dashboards_yaml, encoding="utf-8")
    return provisioned_dashboard


def clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip("`").strip("'").strip('"').strip()
    return cleaned or None


def get_public_base_url(env: dict | None = None) -> str | None:
    """Best-effort detection of the public Jupyter base URL for proxied services."""
    env = env or os.environ

    explicit_base = clean_env_value(env.get("SOWA_PUBLIC_BASE_URL")) or clean_env_value(env.get("JUPYTERHUB_PUBLIC_URL"))
    if explicit_base:
        return explicit_base.rstrip("/")

    host = clean_env_value(env.get("JUPYTERHUB_HOST"))
    prefix = clean_env_value(env.get("JUPYTERHUB_SERVICE_PREFIX")) or clean_env_value(env.get("NB_PREFIX"))
    if host and prefix:
        host = host.rstrip("/")
        if not host.startswith(("http://", "https://")):
            host = f"https://{host}"
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        return f"{host}{prefix.rstrip('/')}"

    # AMD notebook sessions expose a stable public host and a runtime-specific
    # session slug that matches the container hostname. This keeps the URL
    # dynamic across notebook restarts without hardcoding a full session URL.
    public_host = clean_env_value(env.get("SOWA_PUBLIC_HOST")) or "https://notebooks.amd.com"
    public_host = public_host.rstrip("/")
    session_slug = clean_env_value(env.get("HOSTNAME")) or socket.gethostname()
    if session_slug:
        return f"{public_host}/{session_slug}"

    return None


def build_public_service_url(public_base_url: str | None, port: int) -> str:
    if public_base_url:
        return f"{public_base_url.rstrip('/')}/proxy/{port}/"
    return f"http://localhost:{port}/"


def install_python_deps():
    """Install Python dependencies from requirements.txt"""
    print("\n--- Installing Python Dependencies ---")
    req_file = PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        print("Warning: requirements.txt not found!")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file)], check=True)


def require_linux_environment() -> None:
    if IS_LINUX:
        return

    print("=" * 70)
    print("SOWA automated setup is supported on Linux AMD/Jupyter environments only.")
    print(f"Detected platform: {platform.system()}")
    print("This script downloads Linux binaries for Prometheus, Node Exporter, Grafana, and Node.js.")
    print("Use manual setup or run only the backend/frontend pieces on non-Linux systems.")
    print("=" * 70)
    sys.exit(1)


def main():
    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    require_linux_environment()

    print("="*70)
    print("SOWA: ONE-CLICK COMPLETE SETUP & RUN!")
    print("(Everything is included — no manual steps needed!)")
    print("="*70)

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    GRAFANA_PROVISIONING_DIR.mkdir(parents=True, exist_ok=True)
    GRAFANA_DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Service logs directory: {LOG_DIR}")
    public_base_url = get_public_base_url()
    sowa_public_url = build_public_service_url(public_base_url, 8000)
    grafana_public_url = build_public_service_url(public_base_url, 3000)
    prometheus_public_url = build_public_service_url(public_base_url, 9090)

    # 0. Kill any existing processes using our ports first!
    print("\n--- Cleaning up existing processes ---")
    kill_existing_processes()

    # 1. Install Python dependencies first
    install_python_deps()

    # 2. Set up Node.js/npm
    node_cmd, npm_cmd = get_node_npm_paths()

    # 3. Set up Prometheus
    print("\n--- Setting up Prometheus ---")
    prom_dir = find_extracted_dir("prometheus-")
    if not prom_dir:
        prom_url = f"https://github.com/prometheus/prometheus/releases/download/v{PROM_VERSION}/prometheus-{PROM_VERSION}.linux-amd64.tar.gz"
        prom_dir = download_and_extract(prom_url, "prometheus-", f"prometheus-{PROM_VERSION}.linux-amd64.tar.gz")
    else:
        print(f"Found existing Prometheus directory: {prom_dir.name}")
    # Write prometheus config
    prom_config = prom_dir / "prometheus.yml"
    print(f"Writing Prometheus config to {prom_config}")
    yaml_content = (
        "global:\n"
        "  scrape_interval: 5s\n"
        "scrape_configs:\n"
        "  - job_name: 'prometheus'\n"
        "    static_configs:\n"
        "      - targets: ['127.0.0.1:9090']\n"
        "  - job_name: 'node'\n"
        "    static_configs:\n"
        "      - targets: ['127.0.0.1:9100']\n"
        "    metrics_path: /metrics\n"
    )
    prom_config.write_text(yaml_content)

    # 4. Set up Node Exporter
    print("\n--- Setting up Node Exporter ---")
    ne_dir = find_extracted_dir("node_exporter-")
    if not ne_dir:
        ne_url = f"https://github.com/prometheus/node_exporter/releases/download/v{NODE_EXPORTER_VERSION}/node_exporter-{NODE_EXPORTER_VERSION}.linux-amd64.tar.gz"
        ne_dir = download_and_extract(ne_url, "node_exporter-", f"node_exporter-{NODE_EXPORTER_VERSION}.linux-amd64.tar.gz")
    else:
        print(f"Found existing Node Exporter directory: {ne_dir.name}")
    # Create textfile collector directory
    textfile_dir = ne_dir / "textfile_collector"
    textfile_dir.mkdir(parents=True, exist_ok=True)

    # 5. Set up Grafana (MANDATORY!)
    print("\n--- Setting up Grafana ---")
    # Check for both possible prefixes (grafana-VERSION and grafana-vVERSION)
    grafana_dir = find_extracted_dir("grafana-")
    if not grafana_dir:
        grafana_url = f"https://dl.grafana.com/oss/release/grafana-{GRAFANA_VERSION}.linux-amd64.tar.gz"
        grafana_dir = download_and_extract(grafana_url, "grafana-", f"grafana-{GRAFANA_VERSION}.linux-amd64.tar.gz")
    else:
        print(f"Found existing Grafana directory: {grafana_dir.name}")
    provisioned_dashboard = write_grafana_provisioning()
    print(f"Provisioned Grafana dashboard: {provisioned_dashboard}")

    # 6. Build frontend
    print("\n--- Building React Frontend ---")
    frontend_dir = PROJECT_ROOT / "frontend"
    frontend_dist = frontend_dir / "dist"
    node_env = build_node_env(node_cmd)
    if frontend_build_needs_refresh(frontend_dir, frontend_dist):
        print("Frontend build is missing or stale — installing deps and rebuilding...")
        # Install frontend dependencies
        subprocess.run([npm_cmd, "install"], cwd=str(frontend_dir), env=node_env, check=True)
        # Build frontend
        subprocess.run([npm_cmd, "run", "build"], cwd=str(frontend_dir), env=node_env, check=True)
    else:
        print("Frontend already built!")

    # 7. Start ALL services!
    print("\n--- Starting ALL Services ---")
    # Start Prometheus
    print("\nStarting Prometheus...")
    prom_log = LOG_DIR / "prometheus.log"
    proc_prom, prom_handle, prom_thread = launch_service(
        [str(prom_dir / "prometheus"), "--config.file", str(prom_config), "--web.listen-address", ":9090"],
        cwd=prom_dir,
        service_name="Prometheus",
        log_path=prom_log,
    )
    register_process(proc_prom, "Prometheus", prom_log, prom_handle, prom_thread)
    print(f"Prometheus started (PID {proc_prom.pid}) at {prometheus_public_url}")

    # Start Node Exporter
    print("\nStarting Node Exporter...")
    ne_log = LOG_DIR / "node_exporter.log"
    proc_ne, ne_handle, ne_thread = launch_service(
        [str(ne_dir / "node_exporter"), f"--collector.textfile.directory={textfile_dir}"],
        cwd=ne_dir,
        service_name="Node Exporter",
        log_path=ne_log,
    )
    register_process(proc_ne, "Node Exporter", ne_log, ne_handle, ne_thread)
    print(f"Node Exporter started (PID {proc_ne.pid}) at http://localhost:9100")

    # Start Grafana
    print("\nStarting Grafana...")
    grafana_log = LOG_DIR / "grafana.log"
    grafana_env = build_grafana_env()
    proc_grafana, grafana_handle, grafana_thread = launch_service(
        [str(grafana_dir / "bin" / "grafana-server"), "web"],
        cwd=grafana_dir,
        service_name="Grafana",
        log_path=grafana_log,
        env=grafana_env,
    )
    register_process(proc_grafana, "Grafana", grafana_log, grafana_handle, grafana_thread)
    print(f"Grafana started (PID {proc_grafana.pid}) at {grafana_public_url}")
    print("  Grafana login: admin/admin")
    print("  Provisioned datasource: Prometheus")
    print("  Provisioned dashboard folder: SOWA")

    # Start FastAPI backend
    print("\nStarting FastAPI Backend...")
    api_log = LOG_DIR / "backend.log"
    api_env = os.environ.copy()
    api_env["SOWA_TEXTFILE_DIR"] = str(textfile_dir)
    api_env["PYTHONUNBUFFERED"] = "1"
    proc_api, api_handle, api_thread = launch_service(
        [sys.executable, "-u", str(PROJECT_ROOT / "api.py")],
        cwd=PROJECT_ROOT,
        service_name="FastAPI Backend",
        log_path=api_log,
        env=api_env,
        stream_to_console=True,
    )
    register_process(proc_api, "FastAPI Backend", api_log, api_handle, api_thread)
    print(f"Backend started (PID {proc_api.pid}) at {sowa_public_url}")
    print(f"  Backend log: {api_log}")
    print("  Backend logs are now mirrored live to this terminal and also written to backend.log.")
    print("  Note: the LLM loads lazily on the first simulation turn; model logs will appear after the first request.")

    print("\n" + "="*70)
    print("🎉 ALL SERVICES STARTED SUCCESSFULLY! 🎉")
    print("="*70)
    print(f"  - SOWA UI:         {sowa_public_url}")
    print(f"  - Prometheus:      {prometheus_public_url}")
    print("  - Node Exporter:   http://localhost:9100")
    print(f"  - Grafana:         {grafana_public_url}")
    print("\nPress Ctrl+C to stop everything gracefully!")
    print("="*70)

    # Keep script running and monitor processes
    while True:
        time.sleep(1)
        # Check if any process died
        for proc in processes:
            if proc.poll() is not None:
                metadata = process_metadata.get(proc.pid, {})
                service_name = metadata.get("name", proc.args[0])
                log_path = metadata.get("log_path")
                print(f"ERROR: Process {service_name} (PID {proc.pid}) died unexpectedly with exit code {proc.returncode}!")
                if log_path:
                    print_log_tail(service_name, log_path)
                cleanup(None, None)


if __name__ == "__main__":
    main()
