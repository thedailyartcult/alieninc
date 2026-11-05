#!/bin/bash
# Alpha Zero Production Deployment Script
# Usage: ./deploy.sh [version_tag]
# Environment:
#   AZ_HEALTH_URL     Health endpoint to verify (default http://localhost:8080/api/health)
#   AZ_COMPOSE_FILES  Space-separated compose files (default "docker-compose.yml")
#                     e.g. on the server: AZ_COMPOSE_FILES="docker-compose.yml docker-compose.server.yml"
#   AZ_SKIP_BUILD=1   Skip `docker compose build` (image-only deploy)

set -euo pipefail

VERSION="${1:-latest}"
COMPOSE_FILES="${AZ_COMPOSE_FILES:-docker-compose.yml}"
HEALTH_URL="${AZ_HEALTH_URL:-http://localhost:8080/api/health}"
BACKUP_DIR="/home/tablet/alpha_zero_backups"
DATE=$(date +%Y%m%d_%H%M%S)
COMPOSE_ARGS=()
for f in ${COMPOSE_FILES}; do COMPOSE_ARGS+=(-f "$f"); done

echo "=== Alpha Zero Deploy v${VERSION} ==="
mkdir -p "${BACKUP_DIR}"

# Backup current database state
echo "Backing up CMB database..."
docker exec alphazero-cmb cp /srv/cmb/data/cmb.db /srv/cmb/data/cmb.db.backup.${DATE} 2>/dev/null || true

# Backup analytics data
echo "Backing up analytics..."
docker cp alphazero-web:/app/alpha-zero-engine/analytics_data "${BACKUP_DIR}/analytics_${DATE}" 2>/dev/null || true

# Build new images (skippable for image-only deploys)
if [[ "${AZ_SKIP_BUILD:-0}" != "1" ]]; then
    echo "Building images..."
    docker compose "${COMPOSE_ARGS[@]}" build
else
    echo "AZ_SKIP_BUILD=1 — skipping image build"
fi

# Recreate changed services (idempotent; unchanged services are untouched)
echo "Recreating services..."
docker compose "${COMPOSE_ARGS[@]}" up -d

# Wait for health check
echo "Waiting for health check (${HEALTH_URL})..."
for i in {1..30}; do
    if curl -sf "${HEALTH_URL}" > /dev/null; then
        echo "✓ Deployment successful!"
        echo "  Health: $(curl -s "${HEALTH_URL}" | grep -o '"status":"[^"]*"' | head -1)"
        exit 0
    fi
    sleep 2
done

echo "✗ Deployment failed - rolling back..."
./rollback.sh
exit 1
