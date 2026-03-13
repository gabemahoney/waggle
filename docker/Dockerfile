FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3-pip \
    python3-full \
    curl \
    git \
    tmux \
    ca-certificates \
    gnupg \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js LTS via NodeSource
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Install Poetry via official installer
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Install pipx via pip (use --break-system-packages for Ubuntu 24.04)
RUN pip install --break-system-packages pipx
ENV PATH="/root/.local/bin:/home/waggle/.local/bin:$PATH"

# Install bees CLI via pipx as root first, then we'll set up user
RUN PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install 'bees-md[serve]'

# Create non-root waggle user (UID 1000)
RUN useradd -m -u 1000 -s /bin/bash waggle

# Copy waggle source (from rsync-staged build context)
COPY --chown=waggle:waggle . /opt/waggle

# Install Poetry for waggle user and set PATH
RUN curl -sSL https://install.python-poetry.org | su waggle -c "python3 -"
ENV PATH="/home/waggle/.local/bin:$PATH"

# Copy container scripts
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/phase1.sh /usr/local/bin/phase1.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/phase1.sh

USER waggle
WORKDIR /opt/waggle

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
