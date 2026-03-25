@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo Windows Block Fix + Setup Launcher
echo Project: %cd%
echo ==========================================
echo.

REM ---------- 0) Admin check ----------
net session >nul 2>&1
if not errorlevel 1 (
  set "IS_ADMIN=1"
) else (
  set "IS_ADMIN=0"
)
if "%IS_ADMIN%"=="0" (
  echo [WARN] Not running as Administrator.
  echo [WARN] Policy checks may be incomplete.
  echo.
)

REM ---------- 1) Unblock this script + setup ----------
echo [STEP 1/4] Unblock this script and setup.bat...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -LiteralPath '%~f0' -ErrorAction SilentlyContinue; Unblock-File -LiteralPath '%~dp0setup.bat' -ErrorAction SilentlyContinue"
if errorlevel 1 echo [WARN] Single-file unblock returned non-zero.
echo.

REM ---------- 2) Unblock all files in project ----------
echo [STEP 2/4] Unblock all files in project folder...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; Get-ChildItem -LiteralPath '%cd%' -Recurse -File | Unblock-File"
if errorlevel 1 (
  echo [WARN] Bulk unblock returned non-zero.
) else (
  echo [OK] Bulk unblock completed.
)
echo.

REM ---------- 3) Check key security items ----------
echo [STEP 3/4] Read key security settings...
echo.

echo [CHECK] SmartScreen setting:
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer" /v SmartScreenEnabled 2>nul
if errorlevel 1 echo [INFO] Could not read SmartScreenEnabled.
echo.

echo [CHECK] Attachment Manager policy:
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Associations" /v LowRiskFileTypes 2>nul
if errorlevel 1 echo [INFO] LowRiskFileTypes is not configured.
echo.

echo [CHECK] UAC setting:
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v EnableLUA 2>nul
if errorlevel 1 echo [INFO] Could not read EnableLUA.
echo.

echo [CHECK] setup.bat Zone.Identifier stream:
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = Get-Item -LiteralPath '%~dp0setup.bat' -Stream Zone.Identifier -ErrorAction SilentlyContinue; if($s){'FOUND Zone.Identifier'} else {'NOT FOUND Zone.Identifier'}"
echo.

REM ---------- 4) Launch setup ----------
echo [STEP 4/4] Launch setup.bat...
if /i "%SKIP_SETUP%"=="1" (
  echo [INFO] SKIP_SETUP=1, setup launch skipped.
  set "SETUP_EXIT=0"
  goto :DONE
)
if not exist "setup.bat" (
  echo [ERROR] setup.bat not found: %cd%\setup.bat
  pause
  exit /b 1
)

call "%cd%\setup.bat"
set "SETUP_EXIT=%ERRORLEVEL%"
echo.
echo [INFO] setup.bat exit code: %SETUP_EXIT%
if not "%SETUP_EXIT%"=="0" (
  echo [WARN] setup did not complete successfully.
) else (
  echo [OK] setup completed.
)

:DONE
echo.
pause
exit /b %SETUP_EXIT%
