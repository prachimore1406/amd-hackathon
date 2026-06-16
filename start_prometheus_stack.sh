#!/bin/bash
set -e

# Configuration
PROM_VERSION="2.52.0"
NODE_EXPORTER_VERSION="1.8.2"
BASE_DIR="/workspace/shared"
LOG_DIR="$BASE_DIR/sowa_prom_logs"

# Architecture detection
ARCH="linux-amd64"

# Create log directory
mkdir -p "$LOG_DIR"

echo "================================================"
echo "SOWA Prometheus Stack Setup (Bash)"
echo "================================================"

# Step 1: Setup Prometheus
PROM_DIR="$BASE_DIR/prometheus-${PROM_VERSION}.${ARCH}"
PROM_URL="https://github.com/prometheus/prometheus/releases/download/v${PROM_VERSION}/prometheus-${PROM_VERSION}.${ARCH}.tar.gz"

# Download and extract
if [ ! -f "$BASE_DIR/prometheus-${PROM_VERSION}.${ARCH}.tar.gz" ]; then
    echo "Downloading Prometheus..."
    wget -q -O "$BASE_DIR/prometheus-${PROM_VERSION}.${ARCH}.tar.gz" "$PROM_URL"
fi

if [ ! -f "$PROM_DIR/prometheus" ]; then
    echo "Extracting Prometheus..."
    cd "$BASE_DIR"
    tar -xzf "prometheus-${PROM_VERSION}.${ARCH}.tar.gz"
fi

# Write prometheus.yml ALWAYS, perfectly formatted!
echo "Writing prometheus.yml..."
cat > "$PROM_DIR/prometheus.yml" << 'EOF'
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['127.0.0.1:9090']
  - job_name: 'node'
    static_configs:
      - targets: ['127.0.0.1:9100']
    metrics_path: /metrics
EOF
# Verify
echo "  prometheus.yml contents:"
cat "$PROM_DIR/prometheus.yml" | sed 's/^/  /'

# Kill existing prometheus
echo ""
echo "Starting Prometheus..."
pkill -f "./prometheus" || true
cd "$PROM_DIR"
nohup ./prometheus --config.file="$PROM_DIR/prometheus.yml" --web.listen-address=:9090 > "$LOG_DIR/prometheus.log" 2>&1 &
PROM_PID=$!
echo "Prometheus started (PID: $PROM_PID) at http://localhost:9090"

# Step 2: Setup Node Exporter
NODE_EXPORTER_DIR="$BASE_DIR/node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}"
NODE_EXPORTER_URL="https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}.tar.gz"

# Download and extract
if [ ! -f "$BASE_DIR/node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}.tar.gz" ]; then
    echo ""
    echo "Downloading Node Exporter..."
    wget -q -O "$BASE_DIR/node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}.tar.gz" "$NODE_EXPORTER_URL"
fi

if [ ! -f "$NODE_EXPORTER_DIR/node_exporter" ]; then
    echo "Extracting Node Exporter..."
    cd "$BASE_DIR"
    tar -xzf "node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}.tar.gz"
fi

# Create textfile collector directory
echo ""
echo "Starting Node Exporter..."
mkdir -p "$NODE_EXPORTER_DIR/textfile_collector"
# Kill existing node exporter
pkill -f "./node_exporter" || true
cd "$NODE_EXPORTER_DIR"
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
echo "Logs are in: $LOG_DIR"
echo "Base Directory: $BASE_DIR"
echo "To stop the stack later:"
echo "  pkill -f './prometheus' && pkill -f './node_exporter'"
echo "================================================"
