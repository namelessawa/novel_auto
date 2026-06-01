#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/backend/.venv"
CONFIG="$ROOT/config.json"

echo "============================================"
echo "  AI Novel Agent - Unified Launcher"
echo "============================================"
echo

# ---- Check config.json ----
if [ ! -f "$CONFIG" ]; then
    if [ -f "$ROOT/config.example.json" ]; then
        echo "[INFO] config.json not found, copying from config.example.json ..."
        cp "$ROOT/config.example.json" "$CONFIG"
        echo "       Done. Please edit config.json to fill in your API key, then re-run."
    else
        echo "[ERROR] config.json not found. Please create it manually."
    fi
    exit 1
fi

# ---- Parse ports from config.json ----
BACKEND_PORT=$(python3 -c "import json;c=json.load(open('$CONFIG'));print(c.get('server',{}).get('backend_port',8000))")
FRONTEND_PORT=$(python3 -c "import json;c=json.load(open('$CONFIG'));print(c.get('server',{}).get('frontend_port',3000))")

echo "[Config] Backend port : $BACKEND_PORT"
echo "[Config] Frontend port: $FRONTEND_PORT"
echo

# ---- Setup Python venv ----
if [ ! -f "$VENV/bin/activate" ]; then
    echo "[Step 1/4] Creating Python virtual environment ..."
    python3 -m venv "$VENV"
    echo "           venv created at $VENV"
else
    echo "[Step 1/4] Python venv already exists."
fi

# ---- Install Python dependencies ----
echo "[Step 2/4] Installing Python dependencies ..."
source "$VENV/bin/activate"
pip install -r "$ROOT/backend/requirements.txt" -q
echo "           Dependencies installed."
echo

# ---- Install Node.js dependencies ----
echo "[Step 3/4] Installing Node.js dependencies ..."
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
    npm install
else
    echo "           node_modules already exists, skipping."
fi
echo

# ---- Launch both services ----
echo "[Step 4/4] Starting services ..."
echo
echo "  Backend  : http://localhost:$BACKEND_PORT"
echo "  Frontend : http://localhost:$FRONTEND_PORT"
echo
echo "  Press Ctrl+C to stop all services."
echo "============================================"

# Cleanup function to kill both processes on exit
cleanup() {
    echo
    echo "Shutting down ..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    wait 2>/dev/null
    echo "All services stopped."
}
trap cleanup EXIT INT TERM

# Start backend in background
cd "$ROOT/backend"
source "$VENV/bin/activate"
python main.py &
BACKEND_PID=$!

# Start frontend in background
cd "$ROOT/frontend"
BACKEND_PORT=$BACKEND_PORT FRONTEND_PORT=$FRONTEND_PORT npx vite --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

# Wait briefly then open browser
sleep 3
if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:$FRONTEND_PORT"
elif command -v open &>/dev/null; then
    open "http://localhost:$FRONTEND_PORT"
fi

# Wait for either to exit
wait
