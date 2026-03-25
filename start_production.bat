@echo off
setlocal
cd /d "%~dp0"

rem Prefer UTF-8 so console output doesn't get mangled.
chcp 65001 >nul

if not exist "dist\index.html" (
  echo [ERROR] dist\index.html not found. Run: npm run build
  pause
  exit /b 1
)

set "WAITRESS_EXE="
if exist ".venv\Scripts\waitress-serve.exe" set "WAITRESS_EXE=.venv\Scripts\waitress-serve.exe"

if "%WAITRESS_EXE%"=="" (
  where waitress-serve >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] waitress-serve not found.
    echo Install deps first: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
  )
  set "WAITRESS_EXE=waitress-serve"
)

echo Starting Python backend (127.0.0.1:9000)...
start "ECM-Python" cmd /k "%WAITRESS_EXE% --listen=127.0.0.1:9000 app.main:app"
timeout /t 2 /nobreak >nul

set "PORT=8080"
set "HOST=127.0.0.1"
echo Starting gateway (http://%HOST%:%PORT%)...
node server/prod.js
pause
