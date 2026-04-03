@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\pip.exe" (
  echo [ERROR] No .venv. Run start_ecm_backend.bat or: py -3.11 -m venv .venv
  exit /b 1
)
echo [INFO] Removing broken partial installs (~umpy) if present...
if exist ".venv\Lib\site-packages\~umpy" rmdir /s /q ".venv\Lib\site-packages\~umpy"
if exist ".venv\Lib\site-packages\~umpy-0.dist-info" rmdir /s /q ".venv\Lib\site-packages\~umpy-0.dist-info"
if exist ".venv\Lib\site-packages\~umpy.dist-info" rmdir /s /q ".venv\Lib\site-packages\~umpy.dist-info"
echo [INFO] Reinstalling numpy + matplotlib...
call ".venv\Scripts\pip.exe" uninstall -y numpy matplotlib 2>nul
call ".venv\Scripts\pip.exe" install --no-cache-dir "numpy==1.26.4" "matplotlib==3.8.4"
if errorlevel 1 exit /b 1
echo [INFO] Test import...
call ".venv\Scripts\python.exe" -c "import numpy; import matplotlib; print('OK:', numpy.__version__)"
if errorlevel 1 (
  echo [WARN] Still failing. Install Microsoft Visual C++ Redistributable x64, then run this script again.
  exit /b 1
)
echo [INFO] Done.
exit /b 0
