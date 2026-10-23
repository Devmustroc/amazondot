#!/usr/bin/env bash
# ==============================================================================
# TAD Core Assistant Launcher
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment not found in .venv"
    exit 1
fi

echo "=================================================="
echo "    TAD Core Assistant - Launching System"
echo "=================================================="
echo "Connecting to Echo Dot at IP: \${DOT_HOST:-192.168.1.23}..."

export PYTHONPATH="${SCRIPT_DIR}"
exec .venv/bin/python core_server/main.py "$@"
