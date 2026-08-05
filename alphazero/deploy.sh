#!/bin/bash
# Alpha Zero Production Deployment Script
# Usage: ./deploy.sh [version_tag]
# If no version_tag provided, uses 'latest' from local build

set -euo pipefail

VERSION="${1:-latest}"
COMPOSE_FILE="/home/tablet/alieninc/alphazero/docker-compose.yml"
BACKUP_DIR="/home/tablet/alpha_zero_backups"
DATE=$(date +%Y%m%d_%H%M%S)

echo "=== Alpha Zero Deploy v${VERSION} ==="

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Backup current database state
echo "Backing up CMB database..."
docker exec alphazero-cmb cp /srv/cmb/data/cmb.db /srv/cmb/data/cmb.db.backup.${DATE} 2>/dev/null || true

# Backup analytics data
echo "Backing up analytics..."
docker cp alphazero-web:/app/alpha-zero-engine/analytics_data "${BACKUP_DIR}/analytics_${DATE}" 2>/dev/null || true

# Pull/build new images
echo "Building images..."
docker compose -f "${COMPOSE_FILE}" build --pull

# Rolling update with health checks
echo "Starting rolling update..."
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --scale web=2 web

# Wait for new container to be healthy
echo "Waiting for health check..."
for i in {1..30}; do
    if docker compose -f "${COMPOSE_FILE}" ps web | grep -q "healthy"; then
        echo "New container healthy!"
        break
    fi
    sleep 2
done

# Scale back to single instance
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --scale web=1 web

# Verify deployment
echo "Verifying deployment..."
sleep 3
if curl -sf http://localhost:8080/api/health > /dev/null; then
    echo "✓ Deployment successful!"
    echo "  Health: $(curl -s http://localhost:8080/api/health | jq -r '.status')"
    echo "  Uptime: $(curl -s http://localhost:8080/api/health | jq -r '.uptime_seconds')s"
else
    echo "✗ Deployment failed - rolling back..."
    ./rollback.sh
    exit 1
fi

echo "=== Deploy complete ==="