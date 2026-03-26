@echo off
setlocal

set ROOT=%~dp0
cd /d %ROOT%

if not exist .venv\Scripts\python.exe (
  python -m venv .venv
)

call .venv\Scripts\python.exe -m pip install -r requirements.txt

start "voiceos-backend" cmd /c ".venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8099"

cd /d "%ROOT%frontend"
call npm install
start "voiceos-frontend" cmd /c "npm run dev -- --host 127.0.0.1 --port 5173"

echo Backend: http://127.0.0.1:8099
echo Frontend: http://127.0.0.1:5173
echo.
echo Press Ctrl+C to stop watching this window. Close the backend/frontend windows to stop the servers.
