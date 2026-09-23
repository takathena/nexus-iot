# ==========================================
# NEXUS IoT - Multi-stage Dockerfile
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1000 -s /bin/false -m -d /home/nexus nexus

# Copy Python packages dari builder
COPY --from=builder /root/.local /home/nexus/.local

# Copy aplikasi
COPY --chown=nexus:nexus . /app

# Setup PATH dan PYTHONPATH
ENV PATH=/home/nexus/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_ENV=production \
    PORT=5000

# Buat folder yang dibutuhkan
RUN mkdir -p /app/database /app/logs /app/backup \
    && chown -R nexus:nexus /app

# Entrypoint handle permission & drop privilege
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# ✅ Command default: Gunicorn via run:app
CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "-b", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-", "run:app"]