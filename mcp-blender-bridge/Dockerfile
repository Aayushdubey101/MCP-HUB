FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Install production deps only, no editable install yet
RUN uv sync --frozen --no-dev --no-install-project

# Copy source
COPY src/ ./src/

# Install the project itself
RUN uv sync --frozen --no-dev

ENV BLENDER_BRIDGE_HOST=host.docker.internal \
    BLENDER_BRIDGE_PORT=9876 \
    BLENDER_BRIDGE_LOG_FORMAT=json \
    BLENDER_BRIDGE_LOG_LEVEL=INFO \
    BLENDER_BRIDGE_READ_ONLY=false

ENTRYPOINT ["uv", "run", "mcp-blender-bridge"]
