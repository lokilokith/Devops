# ==========================================
# Stage 1: Builder
# ==========================================
FROM python:3.12-slim AS builder

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system build dependencies required for compiling Python packages (e.g. psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies into a virtual environment to copy later
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# Stage 2: Runtime
# ==========================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app

# Install only the runtime dependencies (e.g. postgresql-client for pg_isready)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 postgresql-client && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and group
RUN groupadd -g 1000 opsforge && \
    useradd -u 1000 -g opsforge -s /bin/bash -m opsforge

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x /app/scripts/entrypoint.sh && \
    chown -R opsforge:opsforge /app

# Switch to non-root user
USER opsforge

EXPOSE 8000

# Healthcheck leveraging the /health/ready endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health/ready || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
