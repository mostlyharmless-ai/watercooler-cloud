#!/bin/bash
# Start services required for memory graph pipeline
#
# Usage:
#   ./scripts/start_services.sh           # Start all services
#   ./scripts/start_services.sh embedding # Start embedding server only
#   ./scripts/start_services.sh stop      # Stop all services
#
# Configuration is read from ~/.watercooler/config.toml [memory_graph.embedding]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${HOME}/.watercooler/config.toml"
PID_DIR="${HOME}/.watercooler/run"

# Default settings (overridden by config.toml)
EMBEDDING_PORT=8081
EMBEDDING_MODEL="KimChen/bge-m3-GGUF:Q8_0"

# Parse config.toml if it exists
if [ -f "$CONFIG_FILE" ]; then
    # Extract port from api_base URL
    port=$(grep -A5 '\[memory_graph\.embedding\]' "$CONFIG_FILE" | grep api_base | grep -oP ':\K[0-9]+(?=/)')
    if [ -n "$port" ]; then
        EMBEDDING_PORT="$port"
    fi
fi

mkdir -p "$PID_DIR"

start_embedding() {
    echo "Starting embedding server on port $EMBEDDING_PORT..."

    # Check if already running
    if [ -f "$PID_DIR/llama-server.pid" ]; then
        pid=$(cat "$PID_DIR/llama-server.pid")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Embedding server already running (PID: $pid)"
            return 0
        fi
    fi

    # Try llama-server first, then fall back to Python llama-cpp-python server
    if command -v llama-server &> /dev/null; then
        echo "Using llama-server binary..."
        llama-server \
            --port "$EMBEDDING_PORT" \
            -hf "$EMBEDDING_MODEL" \
            --embedding \
            > "$PID_DIR/llama-server.log" 2>&1 &
    elif python3 -c "import llama_cpp.server" 2>/dev/null; then
        echo "Using llama-cpp-python server..."
        python3 -m llama_cpp.server \
            --port "$EMBEDDING_PORT" \
            --hf_model_repo_id "KimChen/bge-m3-GGUF" \
            --model "bge-m3-q8_0.gguf" \
            --embedding True \
            --n_ctx 8192 \
            > "$PID_DIR/llama-server.log" 2>&1 &
    else
        echo "Error: No embedding server found"
        echo ""
        echo "Install one of these options:"
        echo "  1. pip install 'llama-cpp-python[server]'"
        echo "  2. Build llama.cpp from source: https://github.com/ggerganov/llama.cpp"
        echo "  3. Download pre-built binaries from llama.cpp releases"
        exit 1
    fi

    echo $! > "$PID_DIR/llama-server.pid"
    echo "Started embedding server (PID: $!)"
    echo "Log: $PID_DIR/llama-server.log"

    # Wait for server to be ready
    echo -n "Waiting for server to be ready"
    for i in {1..30}; do
        if curl -s "http://localhost:$EMBEDDING_PORT/" > /dev/null 2>&1; then
            echo " ready!"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    echo " timeout (server may still be loading model)"
}

stop_services() {
    echo "Stopping services..."

    if [ -f "$PID_DIR/llama-server.pid" ]; then
        pid=$(cat "$PID_DIR/llama-server.pid")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            echo "Stopped embedding server (PID: $pid)"
        fi
        rm -f "$PID_DIR/llama-server.pid"
    fi
}

status_services() {
    echo "Service Status:"
    echo "==============="

    if [ -f "$PID_DIR/llama-server.pid" ]; then
        pid=$(cat "$PID_DIR/llama-server.pid")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Embedding server: RUNNING (PID: $pid, port: $EMBEDDING_PORT)"
        else
            echo "Embedding server: STOPPED (stale PID file)"
        fi
    else
        echo "Embedding server: STOPPED"
    fi
}

case "${1:-all}" in
    embedding)
        start_embedding
        ;;
    stop)
        stop_services
        ;;
    status)
        status_services
        ;;
    all)
        start_embedding
        echo ""
        echo "All services started. Run '$0 status' to check."
        ;;
    *)
        echo "Usage: $0 {embedding|stop|status|all}"
        exit 1
        ;;
esac
