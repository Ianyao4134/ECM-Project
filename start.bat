@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo DeepSeek Notes - Dev Launcher
echo Project: %cd%
echo ==========================================
echo.

echo [INFO] Starting backend (ECM Thinking Engine)...
if exist "start_ecm_backend.bat" (
  start "ECM Backend" cmd /c "start_ecm_backend.bat"
) else (
  echo [WARN] start_ecm_backend.bat not found. Backend will NOT be started automatically.
)
echo.
echo [INFO] Waiting backend health (http://127.0.0.1:9000/health)...
powershell -NoProfile -Command "$ok=$false; for($i=0; $i -lt 15; $i++){ try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9000/health' -TimeoutSec 2; if($r.StatusCode -eq 200){ $ok=$true; break } } catch {}; Start-Sleep -Seconds 1 }; if($ok){ exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [WARN] Backend health check failed. Login/register may fail.
  echo [WARN] Please check the "ECM Backend" window for detailed errors.
  echo.
) else (
  echo [OK] Backend is healthy.
  echo.
)

where node >nul 2>&1
if errorlevel 1 goto :ERR_NODE

where npm >nul 2>&1
if errorlevel 1 goto :ERR_NPM

if not exist node_modules\ goto :INSTALL

if not exist .env goto :WARN_ENV
goto :START

:INSTALL
echo [INFO] node_modules not found. Running npm install...
call npm.cmd install
if errorlevel 1 goto :ERR_INSTALL
goto :START

:WARN_ENV
echo [WARN] .env not found.
echo        Please create .env and set DEEPSEEK_API_KEY first.
echo        You can copy .env.example to .env
echo.
goto :START

:START
echo [INFO] Opening browser...
where msedge >nul 2>&1
if not errorlevel 1 (
  start "" msedge "http://127.0.0.1:5173/"
) else (
  start "" "http://127.0.0.1:5173/"
)
echo.
echo If Vite says port 5173 is in use, it may choose 5174/5175.
echo In that case, use the URL printed in this window.
echo.
echo [INFO] Starting dev server (web + api)...
echo Close this window to stop the server.
echo.

call npm.cmd run dev
echo.
echo [INFO] Dev server stopped.
pause
exit /b 0

:ERR_NODE
echo [ERROR] Node.js not found. Please install Node.js first.
pause
exit /b 1

:ERR_NPM
echo [ERROR] npm not found. Please reinstall Node.js (npm is included).
pause
exit /b 1

:ERR_INSTALL
echo.
echo [ERROR] npm install failed.
pause
exit /b 1

