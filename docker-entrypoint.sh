#!/bin/bash
# ==========================================
# NEXUS IoT - Docker Entrypoint
# Handle permission & drop privilege dari root ke nexus
# ==========================================

set -e

# Fungsi logging
log() {
    echo "[entrypoint] $*"
}

# Pastikan folder ada
mkdir -p /app/database /app/logs /app/backup

# Kalau dijalankan sebagai root, chown folder ke nexus lalu drop privilege
if [ "$(id -u)" = "0" ]; then
    log "Running as root, fixing permissions..."

    # Chown folder yang di-mount dari host
    chown -R nexus:nexus /app/database /app/logs /app/backup 2>/dev/null || true

    # Test apakah nexus user bisa write
    if ! gosu nexus touch /app/logs/.write_test 2>/dev/null; then
        log "WARNING: nexus user cannot write to /app/logs"
    else
        rm -f /app/logs/.write_test
        log "Permissions OK"
    fi

    # Drop privilege ke nexus dan jalankan command
    log "Dropping privileges to nexus user..."
    exec gosu nexus "$@"
else
    # Sudah bukan root, langsung jalankan
    log "Running as $(id -un) (uid=$(id -u))"
    exec "$@"
fi