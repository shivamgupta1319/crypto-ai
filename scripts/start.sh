#!/usr/bin/env bash
# Launch the dockerized stack, auto-picking FREE host ports (verifies each port
# is bindable before use). Override the starting points with BACKEND_PORT /
# FRONTEND_PORT env vars.
set -euo pipefail
cd "$(dirname "$0")/.."

find_free_port() {
  python3 - "$1" <<'PY'
import socket, sys
p = int(sys.argv[1])
while p < 65535:
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", p))
        s.close()
        print(p)
        break
    except OSError:
        p += 1
    finally:
        s.close()
PY
}

BACKEND_PORT="$(find_free_port "${BACKEND_PORT:-8090}")"
FRONTEND_PORT="$(find_free_port "${FRONTEND_PORT:-5190}")"
if [ "$FRONTEND_PORT" = "$BACKEND_PORT" ]; then
  FRONTEND_PORT="$(find_free_port "$((BACKEND_PORT + 1))")"
fi
export BACKEND_PORT FRONTEND_PORT

echo "▶ crypto-ai starting (free ports verified)"
echo "  Frontend → http://localhost:${FRONTEND_PORT}"
echo "  Backend  → http://localhost:${BACKEND_PORT}  (API + docs at /docs)"
echo

# Prefer the v2 plugin syntax, fall back to docker-compose.
if docker compose version >/dev/null 2>&1; then
  exec docker compose up --build
else
  exec docker-compose up --build
fi
