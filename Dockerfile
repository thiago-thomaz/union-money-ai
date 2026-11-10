FROM python:3.11-slim

ARG SOURCE_COMMIT=production-cloud

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsqlite3-dev \
    libpng-dev \
    libjpeg-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/storage /app/backups /app/data /app/logs

ENV PYTHONUNBUFFERED=1
ENV GIT_COMMIT_SHA=${SOURCE_COMMIT}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "-m", "scripts.cloud_entrypoint"]
