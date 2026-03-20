@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo ECM Thinking Engine - Backend Launcher
echo Project: %cd%
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating venv...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create venv.
    pause
    exit /b 1
  )
)

echo [INFO] Installing dependencies (no pip cache)...
call .venv\Scripts\pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed.
  pause
  exit /b 1
)

if not exist ".env" (
  echo [WARN] .env not found. Please copy .env.example to .env and set DEEPSEEK_API_KEY.
  echo.
)

echo [INFO] Starting server on http://127.0.0.1:9000 ...
echo [INFO] Health check: http://127.0.0.1:9000/health
echo [INFO] Run ECM:      POST http://127.0.0.1:9000/ecm/run
echo.

call .venv\Scripts\python -m app.main
echo.
echo [INFO] Server stopped.
pause

