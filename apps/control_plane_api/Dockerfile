# Use the official uv image which includes Python and the uv package manager
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Configuration for Python and UV
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Ensure the virtualenv created by uv is in the path
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ------------------------------------------------------------------------------
# 1. Dependency Resolution Layer
# ------------------------------------------------------------------------------
# Copy the lockfile and root config first to leverage caching
COPY pyproject.toml uv.lock ./

# Copy shared libraries
COPY schemas/ ./schemas/
COPY packages/ ./packages/
COPY connectors/ ./connectors/

# Copy all apps to satisfy workspace topology (cli, ingest, etc.)
# We will use .dockerignore to ensure we don't copy local .venvs
COPY apps/ ./apps/

# Install dependencies without the app code first.
# This creates the virtualenv at /app/.venv
# --no-install-project: Skips installing the project itself (just deps)
RUN uv sync --frozen --no-dev --no-install-project --package ambyte-control-plane-api

# ------------------------------------------------------------------------------
# 2. Application Code Layer
# ------------------------------------------------------------------------------

# Sync again to install the 'ambyte-control-plane-api' package itself into the venv
RUN uv sync --frozen --no-dev --package ambyte-control-plane-api

# ------------------------------------------------------------------------------
# 3. Runtime Configuration
# ------------------------------------------------------------------------------
# Change directory into the app folder so Alembic and relative imports work naturally
WORKDIR /app/apps/control_plane_api

EXPOSE 8000

# We use 'uv run' to ensure execution happens within the managed virtualenv context.
# Default command runs the API server.
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]