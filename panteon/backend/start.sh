#!/bin/bash
set -e

echo "=== Panteon Backend ==="
echo ""

if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Edit .env with your API keys before starting."
fi

echo "Starting PostgreSQL, Redis, and Panteon API..."
docker compose up -d

echo ""
echo "Services:"
echo "  API:     http://localhost:8000"
echo "  Docs:    http://localhost:8000/docs"
echo "  Postgres: localhost:5432 (panteon/panteon)"
echo "  Redis:   localhost:6379"
echo ""
echo "To stop: docker compose down"
echo "To see logs: docker compose logs -f"
