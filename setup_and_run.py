#!/usr/bin/env python3
"""One single script to do EVERYTHING: install Node/npm, Prometheus, Node Exporter, Grafana, build frontend, install Python dependencies, and start all services!
"""
import subprocess
import sys
import time
import signal
from pathlib import Path
import urllib.request
import tarfile
import os

# Configuration
BASE_DIR = Path("/workspace/shared")
PROJECT_ROOT = Path(__file__).parent

NODE_VERSION = "20.15.0"
PROM_VERSION = "2.52.0"
NODE_EXPORTER_VERSION = "1.8.2"
GRAFANA_VERSION = "11.1.0"

NODE_DIR = BASE_DIR / f"node-v{NODE_VERSION}-linux-x64"
PROM_DIR = BASE_DIR / f"prometheus-{PROM_VERSION}.linux-amd64"
NODE_EXPORTER_DIR = BASE_DIR / f"node_exporter-{NODE_EXPORTER_VERSION}.linux-amd64"
GRAFANA_DIR = BASE_DIR / f"grafana-{GRAFANA_VERSION}.linux-amd64"
LOG_DIR = BASE_DIR / "sowa_prom_logs"

# Process trackers
processes = []


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
            except:
                pass
    print("All services stopped!")
    sys.exit(0)


def download_and_extract(url: str, dest_dir: Path, tar_name: str):
    """Download and extract a tar.gz/tar.xz file"""
    tar_path = BASE_DIR / tar_name
    if not tar_path.exists():
        print(f"Downloading: {url}")
        try:
            urllib.request.urlretrieve(url, str(tar_path))
        except Exception as e:
            print(f"Download failed: {e}")
            sys.exit(1)
    # Check if extracted dir exists and has the binary we expect
    expected_bin_suffix = {
        "node": "bin/node",
        "prometheus": "prometheus",
        "node_exporter": "node_exporter",
        "grafana": "bin/grafana-server"
    }
    expected_bin = None
    for key, suffix in expected_bin_suffix.items():
        if key in dest_dir.name:
            expected_bin = dest_dir / suffix
            break
    if not dest_dir.exists() or not expected_bin.exists():
        print(f"Extracting: {tar_path.name}")
        try:
            mode = "r:xz" if tar_name.endswith(".xz") else "r:gz"
            with tarfile.open(tar_path, mode) as tar:
                tar.extractall(path=BASE_DIR)
        except Exception as e:
            print(f"Extract failed: {e}")
            sys.exit(1)


def get_node_npm_paths():
    """Get paths to node and npm, installing if necessary"""
    # Check if node/npm are already in PATH and work
    try:
        node_ver = subprocess.check_output(["node", "-v"], text=True, stderr=subprocess.STDOUT).strip()
        npm_ver = subprocess.check_output(["npm", "-v"], text=True, stderr=subprocess.STDOUT).strip()
        print(f"Found system Node.js: {node_ver}, npm: {npm_ver}")
        return "node", "npm"
    except:
        pass

    # Check our local installation
    node_cmd = NODE_DIR / "bin" / "node"
    npm_cmd = NODE_DIR / "bin" / "npm"
    if node_cmd.exists() and npm_cmd.exists():
        print("Found local Node.js installation!")
        return str(node_cmd), str(npm_cmd)

    # Install Node.js
    print("\nNode.js/npm not found! Installing now...")
    node_url = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz"
    download_and_extract(node_url, NODE_DIR, f"node-v{NODE_VERSION}-linux-x64.tar.xz")
    print(f"Node.js installed to {NODE_DIR}!")
    return str(node_cmd), str(npm_cmd)


def install_python_deps():
    """Install Python dependencies from requirements.txt"""
    print("\n--- Installing Python Dependencies ---")
    req_file = PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        print("Warning: requirements.txt not found!")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file)], check=True)


def main():
    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("="*70)
    print("SOWA: ONE-CLICK COMPLETE SETUP & RUN!")
    print("(Everything is included — no manual steps needed!)")
    print("="*70)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Install Python dependencies first
    install_python_deps()

    # 2. Set up Node.js/npm
    node_cmd, npm_cmd = get_node_npm_paths()

    # 3. Set up Prometheus
    print("\n--- Setting up Prometheus ---")
    prom_url = f"https://github.com/prometheus/prometheus/releases/download/v{PROM_VERSION}/prometheus-{PROM_VERSION}.linux-amd64.tar.gz"
    download_and_extract(prom_url, PROM_DIR, f"prometheus-{PROM_VERSION}.linux-amd64.tar.gz")
    # Write prometheus config
    prom_config = PROM_DIR / "prometheus.yml"
    print(f"Writing Prometheus config to {prom_config}")
    yaml_content = (
        "global:\n"
        "  scrape_interval: 15s\n"
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
    ne_url = f"https://github.com/prometheus/node_exporter/releases/download/v{NODE_EXPORTER_VERSION}/node_exporter-{NODE_EXPORTER_VERSION}.linux-amd64.tar.gz"
    download_and_extract(ne_url, NODE_EXPORTER_DIR, f"node_exporter-{NODE_EXPORTER_VERSION}.linux-amd64.tar.gz")
    # Create textfile collector dir
    textfile_dir = NODE_EXPORTER_DIR / "textfile_collector"
    textfile_dir.mkdir(parents=True, exist_ok=True)

    # 5. Set up Grafana (MANDATORY!)
    print("\n--- Setting up Grafana ---")
    grafana_url = f"https://dl.grafana.com/oss/release/grafana-{GRAFANA_VERSION}.linux-amd64.tar.gz"
    download_and_extract(grafana_url, GRAFANA_DIR, f"grafana-{GRAFANA_VERSION}.linux-amd64.tar.gz")

    # 6. Build frontend
    print("\n--- Building React Frontend ---")
    frontend_dir = PROJECT_ROOT / "frontend"
    frontend_dist = frontend_dir / "dist"
    if not frontend_dist.exists() or not (frontend_dist / "index.html").exists():
        print("Frontend not built yet — installing deps and building...")
        # Install frontend dependencies
        subprocess.run([npm_cmd, "install"], cwd=str(frontend_dir), check=True)
        # Build frontend
        subprocess.run([npm_cmd, "run", "build"], cwd=str(frontend_dir), check=True)
    else:
        print("Frontend already built!")

    # 7. Start ALL services!
    print("\n--- Starting ALL Services ---")
    # Start Prometheus
    print("\nStarting Prometheus...")
    prom_log = LOG_DIR / "prometheus.log"
    with open(prom_log, "w") as f:
        proc_prom = subprocess.Popen(
            [str(PROM_DIR / "prometheus"), "--config.file", str(prom_config), "--web.listen-address", ":9090"],
            cwd=str(PROM_DIR),
            stdout=f,
            stderr=f
        )
    processes.append(proc_prom)
    print(f"Prometheus started (PID {proc_prom.pid}) at http://localhost:9090")

    # Start Node Exporter
    print("\nStarting Node Exporter...")
    ne_log = LOG_DIR / "node_exporter.log"
    with open(ne_log, "w") as f:
        proc_ne = subprocess.Popen(
            [str(NODE_EXPORTER_DIR / "node_exporter"), f"--collector.textfile.directory={textfile_dir}"],
            cwd=str(NODE_EXPORTER_DIR),
            stdout=f,
            stderr=f
        )
    processes.append(proc_ne)
    print(f"Node Exporter started (PID {proc_ne.pid}) at http://localhost:9100")

    # Start Grafana
    print("\nStarting Grafana...")
    grafana_log = LOG_DIR / "grafana.log"
    with open(grafana_log, "w") as f:
        proc_grafana = subprocess.Popen(
            [str(GRAFANA_DIR / "bin" / "grafana-server"), "web"],
            cwd=str(GRAFANA_DIR),
            stdout=f,
            stderr=f
        )
    processes.append(proc_grafana)
    print(f"Grafana started (PID {proc_grafana.pid}) at http://localhost:3000")
    print("  Grafana login: admin/admin")
    print("  Import dashboard: use grafana_sowa_dashboard.json!")

    # Start FastAPI backend
    print("\nStarting FastAPI Backend...")
    api_log = LOG_DIR / "backend.log"
    with open(api_log, "w") as f:
        proc_api = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "api.py")],
            cwd=str(PROJECT_ROOT),
            stdout=f,
            stderr=f
        )
    processes.append(proc_api)
    print(f"Backend started (PID {proc_api.pid}) at http://localhost:8000")

    print("\n" + "="*70)
    print("🎉 ALL SERVICES STARTED SUCCESSFULLY! 🎉")
    print("="*70)
    print("  - SOWA UI:         http://localhost:8000")
    print("  - Prometheus:      http://localhost:9090")
    print("  - Node Exporter:   http://localhost:9100")
    print("  - Grafana:         http://localhost:3000")
    print("\nPress Ctrl+C to stop everything gracefully!")
    print("="*70)

    # Keep script running and monitor processes
    while True:
        time.sleep(1)
        # Check if any process died
        for proc in processes:
            if proc.poll() is not None:
                print(f"ERROR: Process {proc.args[0]} (PID {proc.pid}) died unexpectedly!")
                cleanup(None, None)


if __name__ == "__main__":
    main()
