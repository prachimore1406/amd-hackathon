#!/usr/bin/env python3
"""
SOWA Prometheus Stack Startup Script (Python Version)
Downloads, configures, and runs Prometheus and Node Exporter in a single GPU pod
"""

import os
import sys
import subprocess
import platform
import urllib.request
import tarfile
from pathlib import Path

# Configuration
PROM_VERSION = "2.52.0"
NODE_EXPORTER_VERSION = "1.8.2"
BASE_DIR = Path("/workspace/shared")
LOG_DIR = BASE_DIR / "sowa_prom_logs"

# Determine OS/Arch
system = platform.system()
machine = platform.machine()
if system == "Linux" and machine == "x86_64":
    arch = "linux-amd64"
else:
    print(f"Unsupported platform: {system} {machine}")
    print("This script currently only supports Linux x86_64")
    sys.exit(1)


def download_and_extract(url: str, dest_dir: Path):
    """Download and extract a tar.gz file"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Store tar file directly in BASE_DIR instead of dest_dir's parent
    tar_filename = dest_dir.name + ".tar.gz"
    tar_path = BASE_DIR / tar_filename

    if not tar_path.exists():
        print(f"Downloading: {url}")
        try:
            urllib.request.urlretrieve(url, str(tar_path))
        except Exception as e:
            print(f"Download failed: {e}")
            sys.exit(1)

    # Check if the dest_dir exists and contains the expected binary
    expected_bin = dest_dir / ("prometheus" if "prometheus" in dest_dir.name else "node_exporter")
    if not dest_dir.exists() or not expected_bin.exists():
        print(f"Extracting: {tar_path.name}")
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=BASE_DIR)
        except Exception as e:
            print(f"Extract failed: {e}")
            sys.exit(1)
    else:
        print(f"Already extracted and verified: {dest_dir.name}")


def kill_existing_process(pattern: str):
    """Kill existing process matching the pattern"""
    try:
        if system == "Linux":
            subprocess.run(["pkill", "-f", pattern], capture_output=True, check=False)
    except Exception:
        pass


def main():
    print("================================================")
    print("SOWA Prometheus Stack Setup (Python)")
    print("================================================")

    # Create log directory
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Prometheus setup
    prom_dir = BASE_DIR / f"prometheus-{PROM_VERSION}.{arch}"
    prom_url = f"https://github.com/prometheus/prometheus/releases/download/v{PROM_VERSION}/prometheus-{PROM_VERSION}.{arch}.tar.gz"
    download_and_extract(prom_url, prom_dir)

    # Write prometheus.yml (ALWAYS OVERWRITE, PERFECTLY FORMATTED!)
    prom_config = prom_dir / "prometheus.yml"
    print("Writing prometheus.yml...")
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
    # Verify file was written correctly
    print("  prometheus.yml contents:")
    print("  " + prom_config.read_text().replace("\n", "\n  "))

    # Start Prometheus
    print()
    print("Starting Prometheus...")
    kill_existing_process("./prometheus")
    prom_log = LOG_DIR / "prometheus.log"
    prom_binary = prom_dir / "prometheus"
    if not prom_binary.exists():
        print(f"ERROR: Prometheus binary not found at {prom_binary}!")
        sys.exit(1)
    with open(prom_log, "w") as f:
        prom_proc = subprocess.Popen(
            [str(prom_binary), "--config.file", str(prom_config), "--web.listen-address", ":9090"],
            cwd=str(prom_dir),
            stdout=f,
            stderr=f
        )
    print(f"Prometheus started (PID: {prom_proc.pid}) at http://localhost:9090")

    # Node Exporter setup
    node_dir = BASE_DIR / f"node_exporter-{NODE_EXPORTER_VERSION}.{arch}"
    node_url = f"https://github.com/prometheus/node_exporter/releases/download/v{NODE_EXPORTER_VERSION}/node_exporter-{NODE_EXPORTER_VERSION}.{arch}.tar.gz"
    download_and_extract(node_url, node_dir)

    # Create textfile collector directory for SOWA metrics
    textfile_dir = node_dir / "textfile_collector"
    textfile_dir.mkdir(parents=True, exist_ok=True)
    
    # Start Node Exporter
    print()
    print("Starting Node Exporter...")
    kill_existing_process("./node_exporter")
    node_log = LOG_DIR / "node_exporter.log"
    node_binary = node_dir / "node_exporter"
    if not node_binary.exists():
        print(f"ERROR: Node Exporter binary not found at {node_binary}!")
        sys.exit(1)
    with open(node_log, "w") as f:
        node_proc = subprocess.Popen(
            [str(node_binary), f"--collector.textfile.directory={textfile_dir}"],
            cwd=str(node_dir),
            stdout=f,
            stderr=f
        )
    print(f"Node Exporter started (PID: {node_proc.pid}) at http://localhost:9100")

    # Done
    print()
    print("================================================")
    print("Setup Complete!")
    print("================================================")
    print()
    print("To use Prometheus with SOWA:")
    print("Edit 'sowa/metrics.py' and set:")
    print("  USE_PROMETHEUS = True")
    print()
    print(f"Logs are in: {LOG_DIR}")
    print(f"Base Directory: {BASE_DIR}")
    print("To stop the stack later (Linux):")
    print("  pkill -f './prometheus' && pkill -f './node_exporter'")
    print("================================================")


if __name__ == "__main__":
    main()
