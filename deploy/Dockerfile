# ==============================================================================
# TAD Core — Production Multi-Stage Dockerfile (Target: Proxmox CT 105)
# Optimized for ultra-low latency audio processing & offline voice inference
# ==============================================================================

# --- Stage 1: Build & Dependency Resolution ---
FROM python:3.12-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    curl \
    git \
    libasound2-dev \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python production dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Pre-download Piper French neural model (63MB) into build cache
RUN mkdir -p /opt/models/piper && \
    curl -sSL "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx" -o /opt/models/piper/fr_FR-siwis-medium.onnx && \
    curl -sSL "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json" -o /opt/models/piper/fr_FR-siwis-medium.onnx.json


# --- Stage 2: Minimal Production Runtime ---
FROM python:3.12-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PIPER_MODEL_PATH="/app/core_server/models/piper/fr_FR-siwis-medium.onnx" \
    PIPER_CONFIG_PATH="/app/core_server/models/piper/fr_FR-siwis-medium.onnx.json"

WORKDIR /app

# Install only essential runtime C libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    libasound2 \
    ffmpeg \
    openssh-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built virtual environment and models from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/models/piper /app/core_server/models/piper

# Copy application source code
COPY core_server /app/core_server
COPY mcp_config.json /app/mcp_config.json

# Create persistent state and cache directories
RUN mkdir -p /app/core_server/data /app/core_server/tts_cache

# Define Volume mounts for persistence
VOLUME ["/app/core_server/data", "/app/core_server/tts_cache"]

# Healthcheck probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "core_server.healthcheck"]

# Entrypoint daemon
CMD ["python", "-m", "core_server.main"]
