#!/bin/bash
# Alpha Zero Rollback Script
# Usage: ./rollback.sh [backup_timestamp]
# If no timestamp provided, rolls back to the most recent backup

set -euo pipefail

BACKUP_DIR="/home/tablet/alpha_zero_backups"
COMPOSE_FILE="/home/tablet/alieninc/alphazero/docker-compose.yml"
TIMESTAMP="${1:-}"

echo "=== Alpha Zero Rollback ==="

# Find backup to restore
if [[ -z "${TIMESTAMP}" ]]; then
    TIMESTAMP=$(ls -1 "${BACKUP_DIR}"/analytics_* 2>/dev/null | sed 's/.*analytics_\(.*\)/\1/' | sort -r | head -1)
fi

if [[ -z "${TIMESTAMP}" || ! -d "${BACKUP_DIR}/analytics_${TIMESTAMP}" ]]; then
    echo "No backup found for timestamp: ${TIMESTAMP}"
    echo "Available backups:"
    ls -1 "${BACKUP_DIR}"/analytics_* 2>/dev/null | sed 's/.*analytics_\(.*\)/\1/' || echo "  (none)"
    exit 1
fi

echo "Rolling back to backup: ${TIMESTAMP}"

# Stop web service
docker compose -f "${COMPOSE_FILE}" stop web

# Restore analytics data
echo "Restoring analytics..."
docker cp "${BACKUP_DIR}/analytics_${TIMESTAMP}" alphazero-web:/app/alpha-zero-engine/analytics_data

# Restore CMB database
echo "Restoring CMB database..."
docker exec alphazero-cmb cp /srv/cmb/data/cmb.db.backup.${TIMESTAMP} /srv/cmb/data/cmb.db 2>/dev/null || {
    echo "Warning: CMB backup not found for ${TIMESTAMP}, keeping current database"
}

# Restart web service
docker compose -f "${COMPOSE_FILE}" start web

# Wait for health check
echo "Waiting for service to become healthy..."
for i in {1..30}; do
    if curl -sf http://localhost:8080/api/health > /dev/null; then
        echo "✓ Rollback successful!"
        echo "  Health: $(curl -s http://localhost:8080/api/health | jq -r '.status')"
        exit 0
    fi
    sleep 2
done

echo "✗ Rollback failed - service not healthy"
exit 1