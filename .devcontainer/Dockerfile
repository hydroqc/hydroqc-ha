FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm

# Install system dependencies
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        fish \
        curl \
        git \
        build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx

# Install just
RUN curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Set fish as default shell for vscode user
RUN usermod -s /usr/bin/fish vscode

# Switch to vscode user
USER vscode

# Configure fish for vscode user
RUN mkdir -p /home/vscode/.config/fish \
    && echo "# Fish shell configuration" > /home/vscode/.config/fish/config.fish \
    && echo "fish_add_path /home/vscode/.local/bin" >> /home/vscode/.config/fish/config.fish

# Set working directory
WORKDIR /workspaces/hydroqc-ha
