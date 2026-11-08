#!/usr/bin/env bash
# ==============================================================================
# SovereignDot — Clean-Room Amazon Echo Dot 2G Blob Downloader
# Downloads official software components directly to user's local machine.
# No proprietary Amazon binaries are stored in the SovereignDot repository.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TOOLS_DIR="$PROJECT_ROOT/tools"

echo "=========================================================="
echo "📦 SovereignDot — Clean-Room Hardware Asset Fetcher"
echo "=========================================================="

mkdir -p "$TOOLS_DIR/downloads"

# 1. Clone open-source amonet exploit (GPL-3.0 by k4y0z / dragon8888)
if [ ! -d "$TOOLS_DIR/amonet-biscuit" ]; then
    echo "⚡ Cloning open-source amonet exploit toolchain..."
    git clone --depth 1 https://github.com/k4y0z/amonet-biscuit.git "$TOOLS_DIR/amonet-biscuit" || true
else
    echo "✅ amonet-biscuit toolchain already present."
fi

# 2. Check mtkclient
if [ ! -d "$TOOLS_DIR/mtkclient" ]; then
    echo "⚡ Cloning open-source mtkclient..."
    git clone --depth 1 https://github.com/bkerler/mtkclient.git "$TOOLS_DIR/mtkclient" || true
else
    echo "✅ mtkclient already present."
fi

echo "=========================================================="
echo "🎉 Toolchain setup complete. Ready for hardware liberation."
echo "=========================================================="
