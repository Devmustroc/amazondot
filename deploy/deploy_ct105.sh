#!/usr/bin/env bash
# ==============================================================================
# TAD Core — Automated Zero-Downtime Deployment to Proxmox CT 105
# ==============================================================================
set -euo pipefail

PVE_HOST="${PVE_HOST:-192.168.1.200}"
PVE_USER="${PVE_USER:-root}"
CT_ID="105"
REMOTE_TARGET_DIR="/opt/tad"

echo "=========================================================="
echo "🚀 [TAD Deploy] Starting deployment to Proxmox CT $CT_ID"
echo "=========================================================="

# 1. Check SSH connectivity to Proxmox VE
echo "📡 Checking SSH connection to Proxmox VE ($PVE_HOST)..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=4 "$PVE_USER@$PVE_HOST" "pveversion" >/dev/null 2>&1; then
    echo "❌ Error: Cannot connect via SSH to $PVE_USER@$PVE_HOST."
    exit 1
fi
echo "✅ Proxmox VE host reachable."

# 2. Check CT 105 status
echo "🔍 Checking status of CT $CT_ID..."
CT_STATUS=$(ssh "$PVE_USER@$PVE_HOST" "pct status $CT_ID" | awk '{print $2}')
if [ "$CT_STATUS" != "running" ]; then
    echo "❌ Error: CT $CT_ID is not running (status: $CT_STATUS)."
    exit 1
fi
echo "✅ CT $CT_ID is running."

# 3. Prepare target directory inside CT 105
echo "📁 Ensuring target directory $REMOTE_TARGET_DIR on CT $CT_ID..."
ssh "$PVE_USER@$PVE_HOST" "pct exec $CT_ID -- mkdir -p $REMOTE_TARGET_DIR"

# 4. Create and push synchronized tarball
echo "📦 Packaging clean repository payload..."
TMP_ARCHIVE=$(mktemp /tmp/tad-deploy-XXXXXX.tar.gz)
tar --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='core_server/tts_cache' \
    --exclude='firmware' \
    --exclude='tools/amonet-biscuit' \
    --exclude='tools/mtkclient' \
    -czf "$TMP_ARCHIVE" .

echo "📤 Uploading package to Proxmox host..."
scp "$TMP_ARCHIVE" "$PVE_USER@$PVE_HOST:/tmp/tad-payload.tar.gz"
rm -f "$TMP_ARCHIVE"

echo "📥 Extracting payload inside CT $CT_ID..."
ssh "$PVE_USER@$PVE_HOST" "
    pct exec $CT_ID -- mkdir -p $REMOTE_TARGET_DIR && \
    pct push $CT_ID /tmp/tad-payload.tar.gz /tmp/tad-payload.tar.gz && \
    pct exec $CT_ID -- tar -xzf /tmp/tad-payload.tar.gz -C $REMOTE_TARGET_DIR && \
    pct exec $CT_ID -- rm -f /tmp/tad-payload.tar.gz && \
    rm -f /tmp/tad-payload.tar.gz
"

# 5. Build and reload Docker container inside CT 105
echo "🐳 Building Docker image and restarting service on CT $CT_ID..."
ssh "$PVE_USER@$PVE_HOST" "pct exec $CT_ID -- bash -c '
    cd $REMOTE_TARGET_DIR/deploy && \
    docker compose build && \
    docker compose up -d --remove-orphans
'"

# 6. Install & Enable Systemd Service
echo "⚙️ Configuring systemd service inside CT $CT_ID..."
ssh "$PVE_USER@$PVE_HOST" "pct exec $CT_ID -- bash -c '
    cp $REMOTE_TARGET_DIR/deploy/tad-core.service /etc/systemd/system/tad-core.service && \
    systemctl daemon-reload && \
    systemctl enable tad-core.service
'"

# 7. Execute Healthcheck Probe
echo "🩺 Running live container healthcheck probe..."
sleep 3
if ssh "$PVE_USER@$PVE_HOST" "pct exec $CT_ID -- docker exec tad-core python -m core_server.healthcheck"; then
    echo "=========================================================="
    echo "🎉 [TAD Deploy] Deployment SUCCEEDED and Healthcheck PASSED!"
    echo "=========================================================="
else
    echo "⚠️ Warning: Healthcheck probe failed or timed out. Checking container logs:"
    ssh "$PVE_USER@$PVE_HOST" "pct exec $CT_ID -- docker logs --tail 20 tad-core"
    exit 1
fi
