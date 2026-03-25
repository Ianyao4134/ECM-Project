@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo Build ECM Backend EXE
echo ==========================================
echo.

set "PYEXE="
for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
if not defined PYEXE (
  for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
)
if not defined PYEXE (
  echo [ERROR] Python not found. This build script must run on a dev machine with Python.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating .venv...
  "%PYEXE%" -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    pause
    exit /b 1
  )
)

set "VENV_PY=.venv\Scripts\python.exe"
echo [INFO] Installing backend dependencies and pyinstaller...
call "%VENV_PY%" -m pip install --upgrade pip
call "%VENV_PY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo [ERROR] Dependency install failed.
  pause
  exit /b 1
)

echo [INFO] Building one-file backend executable...
call "%VENV_PY%" -m PyInstaller --noconfirm --onefile --name ecm_backend app\main.py
if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

if not exist "runtime" mkdir runtime
copy /y "dist\ecm_backend.exe" "runtime\ecm_backend.exe" >nul

if errorlevel 1 (
  echo [ERROR] Failed to copy runtime\ecm_backend.exe
  pause
  exit /b 1
)

echo.
echo [OK] Build complete: runtime\ecm_backend.exe
echo [OK] End users can run setup.bat/start.bat without installing Python.
pause
exit /b 0
