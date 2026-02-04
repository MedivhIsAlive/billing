# ============ BUILD STAGE ============
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies and Just
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ============ RUNTIME STAGE ============
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:/usr/local/bin:$PATH

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Just from builder
COPY --from=builder /usr/local/bin/just /usr/local/bin/just

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local


RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

CMD ["just", "serve"]
