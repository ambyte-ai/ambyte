# Use the official uv image based on Python 3.11
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ------------------------------------------------------------------------------
# 1. Dependency Resolution Layer
# ------------------------------------------------------------------------------
# Copy lockfile and root config
COPY pyproject.toml uv.lock ./

# Copy shared libraries (schemas is critical for Pydantic models)
COPY schemas/ ./schemas/
# Copy other packages to satisfy workspace checks (though audit only needs schemas)
COPY packages/ ./packages/
COPY connectors/ ./connectors/

# Copy all apps to satisfy workspace topology
COPY apps/ ./apps/

# Install dependencies for the audit worker specifically
# --frozen: Use strict versions from uv.lock
# --no-dev: Production only
# --package ambyte-audit: Only install this package's tree
RUN uv sync --frozen --no-dev --no-install-project --package ambyte-audit

# ------------------------------------------------------------------------------
# 2. Application Code Layer
# ------------------------------------------------------------------------------
# Install the app code itself
RUN uv sync --frozen --no-dev --package ambyte-audit

# ------------------------------------------------------------------------------
# 3. Runtime Configuration
# ------------------------------------------------------------------------------
WORKDIR /app/apps/audit-log

# Expose health check port
EXPOSE 8002

# Run the worker process
CMD ["uv", "run", "python", "src/main.py"]