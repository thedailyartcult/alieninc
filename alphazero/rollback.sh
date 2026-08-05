#!/bin/bash
# Alpha Zero Rollback Script
# Usage: ./rollback.sh [backup_timestamp]
# Environment:
#   AZ_HEALTH_URL     Health endpoint to verify (default http://localhost:8080/api/health)
#   AZ_COMPOSE_FILES  Space-separated compose files (default "docker-compose.yml")

set -euo pipefail

BACKUP_DIR="/home/tablet/alpha_zero_backups"
HEALTH_URL="${AZ_HEALTH_URL:-http://localhost:8080/api/health}"
COMPOSE_FILES="${AZ_COMPOSE_FILES:-docker-compose.yml}"
TIMESTAMP="${1:-}"
COMPOSE_ARGS=()
for f in ${COMPOSE_FILES}; do COMPOSE_ARGS+=(-f "$f"); done

echo "=== Alpha Zero Rollback ==="

# Find backup to restore
if [[ -z "${TIMESTAMP}" ]]; then
    TIMESTAMP=$(find "${BACKUP_DIR}" -maxdepth 1 -type d -name 'analytics_*' -printf '%f\n' 2>/dev/null | sed 's/^analytics_//' | sort -r | head -1)
fi

if [[ -z "${TIMESTAMP}" || ! -d "${BACKUP_DIR}/analytics_${TIMESTAMP}" ]]; then
    echo "No backup found for timestamp: ${TIMESTAMP}"
    echo "Available backups:"
    find "${BACKUP_DIR}" -maxdepth 1 -type d -name 'analytics_*' -printf '%f\n' 2>/dev/null | sed 's/^analytics_//' || echo "  (none)"
    exit 1
fi

echo "Rolling back to backup: ${TIMESTAMP}"

# Stop web service
docker compose "${COMPOSE_ARGS[@]}" stop web

# Restore analytics data (replace the directory contents)
echo "Restoring analytics..."
docker exec alphazero-web sh -c 'rm -rf /app/alpha-zero-engine/analytics_data' 2>/dev/null || true
docker cp "${BACKUP_DIR}/analytics_${TIMESTAMP}" alphazero-web:/app/alpha-zero-engine/

# Restore CMB database
echo "Restoring CMB database..."
docker exec alphazero-cmb cp /srv/cmb/data/cmb.db.backup.${TIMESTAMP} /srv/cmb/data/cmb.db 2>/dev/null || {
    echo "Warning: CMB backup not found for ${TIMESTAMP}, keeping current database"
}

# Restart web service
docker compose "${COMPOSE_ARGS[@]}" start web

# Wait for health check
echo "Waiting for service to become healthy (${HEALTH_URL})..."
for i in {1..30}; do
    if curl -sf "${HEALTH_URL}" > /dev/null; then
        echo "✓ Rollback successful!"
        exit 0
    fi
    sleep 2
done

echo "✗ Rollback failed - service not healthy"
exit 1
