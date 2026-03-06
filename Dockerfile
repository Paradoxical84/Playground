FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# ---------- train stage (optional, produces /app/model) ----------
FROM base AS train
RUN python -m app.train --output-dir /app/model --epochs 5

# ---------- serve stage ----------
FROM base AS serve

COPY --from=train /app/model /app/model

ENV MODEL_DIR=/app/model \
    PORT=8080 \
    STARTUP_DELAY=0 \
    LOG_LEVEL=INFO

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

ENTRYPOINT ["python", "-m", "app.server"]
