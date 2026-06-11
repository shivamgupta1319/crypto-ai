#!/usr/bin/env bash
# Run backend + frontend locally (no Docker), auto-picking FREE ports and wiring
# the Vite dev proxy to the chosen backend port. Requires backend/.venv set up
# and frontend deps installed.
set -euo pipefail
cd "$(dirname "$0")/.."

find_free_port() {
  python3 - "$1" <<'PY'
import socket, sys
p = int(sys.argv[1])
while p < 65535:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        s.close()
        print(p)
        break
    except OSError:
        p += 1
    finally:
        s.close()
PY
}

BPORT="$(find_free_port "${BACKEND_PORT:-8000}")"
FPORT="$(find_free_port "${FRONTEND_PORT:-5173}")"
[ "$FPORT" = "$BPORT" ] && FPORT="$(find_free_port "$((BPORT + 1))")"

echo "▶ backend  → http://127.0.0.1:${BPORT}"
echo "▶ frontend → http://127.0.0.1:${FPORT}"

( cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port "$BPORT" ) &
BACK_PID=$!
trap 'kill "$BACK_PID" 2>/dev/null || true' EXIT

cd frontend
VITE_API_PROXY="http://127.0.0.1:${BPORT}" npm run dev -- --port "$FPORT"
