# syntax=docker/dockerfile:1

# --- Builder stage -----------------------------------------------------------
# Installs dependencies into an isolated venv so the runtime stage never needs
# build tooling (compilers, headers) -- keeps the final image smaller and its
# attack surface lower.
FROM python:3.14-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.lock.txt requirements.txt ./
# The lock file pins exact versions verified against this project; fall back
# to the loosely-pinned requirements.txt only if it's ever absent.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.lock.txt

# --- Runtime stage -------------------------------------------------------------
FROM python:3.14-slim AS runtime

# Runs as a dedicated non-root user -- never run an internet-facing service as
# root inside a container.
RUN groupadd --system incident_agent && useradd --system --gid incident_agent --create-home incident_agent

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
COPY incident_agent ./incident_agent
COPY ui ./ui
COPY run_api.py ./
COPY data/filesystem_sandbox ./data/filesystem_sandbox

# Data directories the app writes to at runtime (SQLite checkpoints/memory,
# Chroma persistence) -- created here so they're owned by the non-root user
# rather than being auto-created as root on first write.
RUN mkdir -p data/chroma data/checkpoints data/sqlite \
    && chown -R incident_agent:incident_agent /app

USER incident_agent

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "incident_agent.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
