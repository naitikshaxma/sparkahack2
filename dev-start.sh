#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ ! -f ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

".venv/bin/python" -m pip install -r requirements.txt

".venv/bin/python" -m uvicorn backend.main:app --host 127.0.0.1 --port 8099 &
BACKEND_PID=$!

cd "$ROOT/frontend"
npm install
npm run dev -- --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!

echo "Backend: http://127.0.0.1:8099"
echo "Frontend: http://127.0.0.1:5173"

wait $BACKEND_PID $FRONTEND_PID
