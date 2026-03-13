# backend/Dockerfile
# Multi-stage build to keep the final image lean.
# Stage 1 installs all Python deps into a venv.
# Stage 2 copies only the venv + app code into the slim runtime image.

# ── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# System deps needed to compile some Python packages (e.g. faiss-cpu)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer cache
COPY ../requirements.txt .

# Create a venv and install deps into it
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only torch must be installed before the rest (avoids downloading GPU variant)
RUN pip install --no-cache-dir \
        torch==2.6.0 \
        --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY backend/app/ ./app/
COPY backend/scripts/ ./scripts/
COPY backend/tests/ ./tests/
COPY pytest.ini ./pytest.ini

# Data directories — volumes are mounted here at runtime by docker-compose.
# Creating the dirs ensures they exist even without a volume mount.
RUN mkdir -p \
        /data/indexes/bm25 \
        /data/indexes/vector \
        /data/processed \
        /data/raw \
        /data/metrics

# Expose the API port
EXPOSE 8000

# Health check so docker-compose and orchestrators know when the API is ready
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run uvicorn directly — no shell wrapper needed in a container
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--log-level", "info"]
