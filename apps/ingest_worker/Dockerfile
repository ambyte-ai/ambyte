# Use the official uv image based on Debian Bookworm (needed for system deps)
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# ==============================================================================
# 1. System Dependencies (The "Heavy" Lifting)
# ==============================================================================
# We install these BEFORE copying python code to cache this layer aggressively.
# - libmagic-dev: Essential for 'unstructured' to detect file types (MIME).
# - poppler-utils: Required to render PDF pages into images/text.
# - tesseract-ocr: Required to extract text from scanned PDFs/Images.
# - libgl1: Required by OpenCV (cv2), which is often pulled by unstructured/layout models.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic-dev \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# ==============================================================================
# 2. Python & UV Configuration
# ==============================================================================
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Add the virtual environment to PATH immediately
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ==============================================================================
# 3. Dependency Resolution Layer
# ==============================================================================
# Copy lockfile and root config
COPY pyproject.toml uv.lock ./

# Copy ALL workspace members required by the root lockfile.
# Even if ingest-worker doesn't import 'ambyte-cli', the workspace 
# definition requires these paths to exist for resolution to pass.
COPY schemas/ ./schemas/
COPY packages/ ./packages/
COPY connectors/ ./connectors/

# Copy all apps. 
# We use .dockerignore to exclude local venvs/caches, keeping this relatively light.
COPY apps/ ./apps/

# Install dependencies.
# - --frozen: Adhere strictly to uv.lock
# - --no-dev: Exclude testing/linting tools
# - --no-install-project: Only install libraries (pandas, unstructured, torch, etc.), not the app code yet.
# - --package ambyte-ingest: Only install deps relevant to this specific workspace member.
RUN uv sync --frozen --no-dev --no-install-project --package ambyte-ingest

# ==============================================================================
# 4. Application Code Layer
# ==============================================================================

# Install the 'ambyte-ingest' package itself into the environment
RUN uv sync --frozen --no-dev --package ambyte-ingest

# ==============================================================================
# 5. Runtime Configuration
# ==============================================================================
# Set working directory to the app root so imports work naturally (src.main)
WORKDIR /app/apps/ingest_worker

# We expose 8000 internally. 
# Docker Compose will likely map this to 8001 or similar on the host.
EXPOSE 8000

# Use 'uv run' to ensure we execute within the virtual environment context.
CMD ["uv", "run", "uvicorn", "ingest_worker.main:app", "--host", "0.0.0.0", "--port", "8000"]