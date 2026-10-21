#!/usr/bin/env bash
# ==============================================================================
# PosiPulse — Local Development Runner Script
# Bootstraps environment and launches FastAPI server on http://localhost:8000
# ==============================================================================

set -e

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"

# Resolve script directory (repository root)
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================================="
echo "🌱 Starting PosiPulse Constructive News Platform..."
echo "=================================================================="

# Check for virtual environment
if [ -d ".venv" ]; then
    echo "✔ Found virtual environment in .venv"
    source .venv/bin/activate
elif command -v python3 &>/dev/null; then
    echo "⚡ Setting up local virtual environment in .venv..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "❌ Error: Python 3 not found. Please install Python 3.12+."
    exit 1
fi

echo ""
echo "------------------------------------------------------------------"
echo "🚀 PosiPulse Web Reader is live at:"
echo "   👉 http://${HOST}:${PORT}/"
echo ""
echo "📖 OpenAPI Documentation at:"
echo "   👉 http://${HOST}:${PORT}/docs"
echo ""
echo "📊 Prometheus Metrics at:"
echo "   👉 http://${HOST}:${PORT}/metrics?format=prometheus"
echo "------------------------------------------------------------------"
echo "Press Ctrl+C to stop the server."
echo ""

exec uvicorn src.api.app:app --host "$HOST" --port "$PORT" --reload
