#!/usr/bin/env bash
# down.sh — stop all running services cleanly

set -euo pipefail

GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RESET="\033[0m"

info() { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${RESET}  $*"; }

UVICORN_PORT=8000
STREAMLIT_PORT=8501

kill_port() {
    local port="$1"
    local name="$2"
    local pids
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        info "Stopping $name on port $port (PID $pids)…"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        info "$name stopped."
    else
        warn "$name not running on port $port."
    fi
}

kill_port "$UVICORN_PORT"  "API server"
kill_port "$STREAMLIT_PORT" "Dashboard"

info "All services stopped."
