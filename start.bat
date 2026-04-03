@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo ECM V2.1 - Dev Launcher
echo Project: %cd%
echo ==========================================
echo.
echo [INFO] One command starts: API ^(8787^) + Vite ^(5173^) + ECM Python ^(9000^).
echo [INFO] Open in browser: http://127.0.0.1:5173/
echo.

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
echo        Copy .env.example to .env and set DEEPSEEK_API_KEY ^(required for AI features^).
echo.

:START
echo [INFO] Starting dev server ^(close this window or press Ctrl+C to stop^)...
echo.
call npm.cmd run dev
echo.
echo [INFO] Dev server stopped.
pause
exit /b 0

:ERR_NODE
echo [ERROR] Node.js not found. Run setup.bat or install Node.js LTS.
pause
exit /b 1

:ERR_NPM
echo [ERROR] npm not found. Reinstall Node.js.
pause
exit /b 1

:ERR_INSTALL
echo [ERROR] npm install failed.
pause
exit /b 1
