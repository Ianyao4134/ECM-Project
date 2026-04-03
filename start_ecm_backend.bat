@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo ECM Thinking Engine - Backend Launcher
echo Project: %cd%
echo ==========================================
echo.

if exist "runtime\ecm_backend.exe" (
  echo [INFO] Found packaged backend: runtime\ecm_backend.exe
  echo [INFO] Starting server on http://127.0.0.1:9000 ...
  echo [INFO] Health check: http://127.0.0.1:9000/health
  echo [INFO] Run ECM:      POST http://127.0.0.1:9000/ecm/run
  echo.
  call "runtime\ecm_backend.exe"
  echo.
  echo [INFO] Server stopped.
  pause
  exit /b 0
)

set "SYS_PY="
REM Prefer Python 3.11 to avoid source-build failures on newer Python (e.g. 3.15).
for /f "delims=" %%P in ('py -3.11 -c "import sys; print(sys.executable)" 2^>nul') do set "SYS_PY=%%P"
if not defined SYS_PY (
  for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "SYS_PY=%%P"
)
if not defined SYS_PY (
  for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "SYS_PY=%%P"
)
if not defined SYS_PY (
  echo [ERROR] Python not found on PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating venv...
  "%SYS_PY%" -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create venv.
    pause
    exit /b 1
  )
)

set "REBUILD_VENV=0"
if exist ".venv\pyvenv.cfg" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$cfg='%cd%\\.venv\\pyvenv.cfg'; $py='%SYS_PY%'; $pyHome=(Select-String -Path $cfg -Pattern '^\s*home\s*=\s*(.+)$' | Select-Object -First 1).Matches.Groups[1].Value.Trim(); if([string]::IsNullOrWhiteSpace($pyHome)){ exit 0 }; $homePy=Join-Path $pyHome 'python.exe'; if(-not (Test-Path $homePy)){ exit 1 }; try { $homeFull=(Get-Item $homePy).FullName.ToLowerInvariant(); $curFull=(Get-Item $py).FullName.ToLowerInvariant(); if($homeFull -ne $curFull){ exit 2 } else { exit 0 } } catch { exit 3 }"
  if errorlevel 1 set "REBUILD_VENV=1"
)

call ".venv\Scripts\python.exe" -c "import sys; print(sys.executable)" >nul 2>&1
if errorlevel 1 (
  set "REBUILD_VENV=1"
)

if "%REBUILD_VENV%"=="1" (
  echo [WARN] Existing .venv is invalid or stale, recreating...
  if exist ".venv" rmdir /s /q ".venv"
  "%SYS_PY%" -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to recreate venv.
    pause
    exit /b 1
  )
)

set "PY_EXE=.venv\Scripts\python.exe"
echo [INFO] Installing dependencies...
call "%PY_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [WARN] pip upgrade failed. Continue to dependency install...
)
call "%PY_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [WARN] First pip install failed, retrying once with no cache...
  call "%PY_EXE%" -m pip install --no-cache-dir -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install failed after retry.
    pause
    exit /b 1
  )
)

if not exist ".env" (
  echo [WARN] .env not found. Please copy .env.example to .env and set DEEPSEEK_API_KEY.
  echo.
)

echo [INFO] Starting server on http://127.0.0.1:9000 ...
echo [INFO] Health check: http://127.0.0.1:9000/health
echo [INFO] Run ECM:      POST http://127.0.0.1:9000/ecm/run
echo.

call "%PY_EXE%" -m app.main
echo.
echo [INFO] Server stopped.
pause

