#!/bin/bash

# SOWA Prometheus Stack Startup Script
# This script downloads, configures, and runs Prometheus and Node Exporter in a single GPU pod

set -e  # Exit on error

# Configuration
PROM_VERSION="2.52.0"
NODE_EXPORTER_VERSION="1.8.2"
BASE_DIR="/workspace/shared"
PROM_DIR="$BASE_DIR/prometheus-$PROM_VERSION.linux-amd64"
NODE_EXPORTER_DIR="$BASE_DIR/node_exporter-$NODE_EXPORTER_VERSION.linux-amd64"
LOG_DIR="$BASE_DIR/sowa_prom_logs"

# Create log directory
mkdir -p "$LOG_DIR"

echo "================================================"
echo "SOWA Prometheus Stack Setup"
echo "================================================"

# Step 1: Download and start Prometheus
if [ ! -d "$PROM_DIR" ]; then
    echo ""
    echo "1. Downloading Prometheus v$PROM_VERSION..."
    mkdir -p "$BASE_DIR"
    cd "$BASE_DIR"
    wget -q "https://github.com/prometheus/prometheus/releases/download/v$PROM_VERSION/prometheus-$PROM_VERSION.linux-amd64.tar.gz"
    tar xzf "prometheus-$PROM_VERSION.linux-amd64.tar.gz"
    rm "prometheus-$PROM_VERSION.linux-amd64.tar.gz"

    # Create config file
    cat > "$PROM_DIR/prometheus.yml" << 'EOF'
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
EOF
fi

echo ""
echo "2. Starting Prometheus..."
cd "$PROM_DIR"
# Kill existing Prometheus if running
pkill -f "./prometheus --config.file=prometheus.yml" 2>/dev/null || true
nohup ./prometheus --config.file=prometheus.yml --web.listen-address=:9090 > "$LOG_DIR/prometheus.log" 2>&1 &
PROM_PID=$!
echo "Prometheus started (PID: $PROM_PID) at http://localhost:9090"

# Step 2: Download and start Node Exporter
if [ ! -d "$NODE_EXPORTER_DIR" ]; then
    echo ""
    echo "3. Downloading Node Exporter v$NODE_EXPORTER_VERSION..."
    cd "$BASE_DIR"
    wget -q "https://github.com/prometheus/node_exporter/releases/download/v$NODE_EXPORTER_VERSION/node_exporter-$NODE_EXPORTER_VERSION.linux-amd64.tar.gz"
    tar xzf "node_exporter-$NODE_EXPORTER_VERSION.linux-amd64.tar.gz"
    rm "node_exporter-$NODE_EXPORTER_VERSION.linux-amd64.tar.gz"
fi

echo ""
echo "4. Starting Node Exporter..."
cd "$NODE_EXPORTER_DIR"
# Create textfile collector directory for SOWA metrics
mkdir -p "textfile_collector"
# Kill existing Node Exporter if running
pkill -f "./node_exporter" 2>/dev/null || true
nohup ./node_exporter --collector.textfile.directory="textfile_collector" > "$LOG_DIR/node_exporter.log" 2>&1 &
NODE_PID=$!
echo "Node Exporter started (PID: $NODE_PID) at http://localhost:9100"

# Step 3: Remind user to enable Prometheus in SOWA
echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "To use Prometheus with SOWA:"
echo "Edit 'sowa/metrics.py' and set:"
echo "  USE_PROMETHEUS = True"
echo ""
echo "Logs are in: $LOG_DIR/"
echo "To stop the stack later:"
echo "  pkill -f './prometheus' && pkill -f './node_exporter'"
echo "================================================"