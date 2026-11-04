FROM mcr.microsoft.com/devcontainers/javascript-node:1-22-bookworm

# Install Python 3, build essentials (for C/tad_dotd), audio libraries and utilities
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        build-essential \
        gcc \
        make \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        libasound2-dev \
        portaudio19-dev \
        alsa-utils \
        curl \
        git \
        ripgrep \
        fd-find \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Set working directory permissions
RUN mkdir -p /home/node/.claude /home/node/.anthropic \
    && chown -R node:node /home/node/.claude /home/node/.anthropic

USER node
