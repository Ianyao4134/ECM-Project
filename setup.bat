@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo ECM V2.1 - Setup
echo ==========================================
echo.

REM ---------- helpers ----------
set "WINGET_OK=0"
where winget >nul 2>&1
if not errorlevel 1 set "WINGET_OK=1"

REM ---------- 1) Node.js ----------
where node >nul 2>&1
if errorlevel 1 (
  echo [SETUP] Node.js not found.
  if "%WINGET_OK%"=="0" (
    echo [ERROR] winget is not available. Install Node.js LTS from https://nodejs.org/ then run setup.bat again.
    pause
    exit /b 1
  )
  echo [SETUP] Installing Node.js LTS via winget...
  winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo [ERROR] winget failed to install Node.js.
    pause
    exit /b 1
  )
  echo [INFO] If `node` is still not found, close this window, open a new terminal, and run setup.bat again.
)

where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] node is still not on PATH. Restart the terminal and run setup.bat again.
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found. Reinstall Node.js LTS or restart the terminal and run setup.bat again.
  pause
  exit /b 1
)

for /f "delims=" %%V in ('node -v 2^>nul') do echo [OK] Node %%V

REM ---------- 2) Python ----------
if exist "runtime\ecm_backend.exe" (
  echo [SETUP] Found packaged backend ^(runtime\ecm_backend.exe^). Python setup will be skipped.
  goto :SKIP_PY
)

set "PYEXE="
py -3 -c "import sys; print(sys.executable)" >"%TEMP%\ecm_setup_py.txt" 2>nul
if not errorlevel 1 set /p PYEXE=<"%TEMP%\ecm_setup_py.txt"
if defined PYEXE goto :HAVE_PY

python -c "import sys; print(sys.executable)" >"%TEMP%\ecm_setup_py.txt" 2>nul
if not errorlevel 1 set /p PYEXE=<"%TEMP%\ecm_setup_py.txt"

:HAVE_PY
if defined PYEXE (
  echo [OK] Python: %PYEXE%
  goto :PY_DONE
)

echo [SETUP] Python not found.
if "%WINGET_OK%"=="0" (
  echo [ERROR] winget is not available. Install Python 3 from https://www.python.org/downloads/ ^(check "Add to PATH"^) then run setup.bat again.
  pause
  exit /b 1
)
echo [SETUP] Installing Python 3.12 via winget...
winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo [ERROR] winget failed to install Python.
  pause
  exit /b 1
)
echo [INFO] If Python is still not found, close this window, open a new terminal, and run setup.bat again.

set "PYEXE="
py -3 -c "import sys; print(sys.executable)" >"%TEMP%\ecm_setup_py.txt" 2>nul
if not errorlevel 1 set /p PYEXE=<"%TEMP%\ecm_setup_py.txt"
if not defined PYEXE (
  python -c "import sys; print(sys.executable)" >"%TEMP%\ecm_setup_py.txt" 2>nul
  if not errorlevel 1 set /p PYEXE=<"%TEMP%\ecm_setup_py.txt"
)
if not defined PYEXE (
  echo [ERROR] Python is still not on PATH. Restart the terminal and run setup.bat again.
  pause
  exit /b 1
)
echo [OK] Python: %PYEXE%

:PY_DONE

REM ---------- 3) pip dependencies (venv, same as start_ecm_backend.bat) ----------
set "REBUILD_VENV=0"
if exist ".venv\pyvenv.cfg" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$cfg='%cd%\\.venv\\pyvenv.cfg'; $py='%PYEXE%'; $pyHome=(Select-String -Path $cfg -Pattern '^\s*home\s*=\s*(.+)$' | Select-Object -First 1).Matches.Groups[1].Value.Trim(); if([string]::IsNullOrWhiteSpace($pyHome)){ exit 0 }; $homePy=Join-Path $pyHome 'python.exe'; if(-not (Test-Path $homePy)){ exit 1 }; try { $homeFull=(Get-Item $homePy).FullName.ToLowerInvariant(); $curFull=(Get-Item $py).FullName.ToLowerInvariant(); if($homeFull -ne $curFull){ exit 2 } else { exit 0 } } catch { exit 3 }"
  if errorlevel 1 set "REBUILD_VENV=1"
)

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Creating virtual environment .venv ...
  "%PYEXE%" -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    pause
    exit /b 1
  )
)

call ".venv\Scripts\python.exe" -c "import sys; print(sys.executable)" >nul 2>&1
if errorlevel 1 (
  set "REBUILD_VENV=1"
)

if "%REBUILD_VENV%"=="1" (
  echo [SETUP] Existing .venv is invalid or stale. Recreating .venv ...
  if exist ".venv" rmdir /s /q ".venv"
  "%PYEXE%" -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to recreate .venv
    pause
    exit /b 1
  )
)

echo [SETUP] pip install -r requirements.txt ...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [WARN] pip upgrade failed. Continue to dependency install...
)
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [WARN] First pip install failed, retrying once with no cache...
  call ".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install failed after retry.
    pause
    exit /b 1
  )
)

:SKIP_PY
REM ---------- 4) npm dependencies ----------
echo [SETUP] npm install ...
call npm.cmd install
if errorlevel 1 (
  echo [ERROR] npm install failed.
  pause
  exit /b 1
)

REM ---------- 5) Config files (keep existing; fill only what is missing) ----------
if not exist ".env.example" (
  echo [SETUP] Creating .env.example ...
  (
    echo # Required: DeepSeek API key
    echo DEEPSEEK_API_KEY=
    echo.
    echo # Optional ^(Python backend / app.config^)
    echo # DEEPSEEK_BASE_URL=https://api.deepseek.com
    echo # DEEPSEEK_MODEL=deepseek-chat
    echo # DEEPSEEK_TIMEOUT_S=60
    echo # ECM_PROMPTS_DIR=prompts
    echo # ECM_DATA_DIR=data
    echo.
    echo # Optional ^(Express proxy in server/index.js^)
    echo # PORT=8787
  ) > .env.example
)

if not exist ".env" (
  if exist ".env.example" (
    echo [SETUP] Creating .env from .env.example ^(edit DEEPSEEK_API_KEY^) ...
    copy /y ".env.example" ".env" >nul
  )
)

echo.
echo ==========================================
echo 安装完成，请运行 start.bat
echo ==========================================
pause
exit /b 0
