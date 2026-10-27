#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || echo "note: no .env present — AI/alerts stay off (fine)"
echo "==> pull images"; docker compose pull
echo "==> up";          docker compose up -d
docker compose ps
echo "Local: http://localhost:${FRONTEND_PORT:-5190}"
