@echo off
setlocal

cd /d "%~dp0Windows_and_Linux"

echo [1/6] Finding Python...
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv --help >nul 2>nul
    if not errorlevel 1 goto :python_found
)

where python >nul 2>nul
if errorlevel 1 goto :python_missing
python -m venv --help >nul 2>nul
if errorlevel 1 goto :python_missing

if not exist ".build-venv\Scripts\python.exe" (
    echo [3/6] Creating build environment...
    python -m venv .build-venv
    if errorlevel 1 goto :failed
)
goto :build

:python_found
if not exist ".build-venv\Scripts\python.exe" (
    echo [3/6] Creating build environment...
    py -3 -m venv .build-venv
    if errorlevel 1 goto :failed
)

:build
set "BUILD_PYTHON=%CD%\.build-venv\Scripts\python.exe"

echo [3/6] Cleaning previous build artifacts...
REM Clean locked directories using PowerShell to handle antivirus/OneDrive locks
if exist "build" (
    powershell.exe -NoProfile -Command "Get-ChildItem -Path 'build' -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue 2>$null; Remove-Item -Path 'build' -Recurse -Force -ErrorAction SilentlyContinue 2>$null"
)
if exist "dist" (
    powershell.exe -NoProfile -Command "Remove-Item -Path 'dist' -Recurse -Force -ErrorAction SilentlyContinue 2>$null"
)
REM Also clean __pycache__ directories that might be locked
powershell.exe -NoProfile -Command "Get-ChildItem -Path '.' -Filter '__pycache__' -Recurse -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue 2>$null"

echo [4/6] Installing build dependencies...
"%BUILD_PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

echo [5/6] Building Writing Tools...
"%BUILD_PYTHON%" pyinstaller-build-script.py
if errorlevel 1 goto :failed

set "EXE_NAME="
for %%F in ("dist\Writing Tools v*.exe") do if exist "%%~fF" set "EXE_NAME=%%~nxF"
if not defined EXE_NAME goto :failed
if not exist "dist\%EXE_NAME%" goto :failed

copy /y "dist\%EXE_NAME%" "%~dp0%EXE_NAME%" >nul
if errorlevel 1 goto :failed

echo [6/6] Replacing the previous version and starting the new build...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Write-Host \"[6/6] Cleaning up any previous Writing Tools v*.exe instances before launching new binary\""
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Windows_and_Linux\finalize-windows-build.ps1" -RepoRoot "%~dp0." -ExeName "%EXE_NAME%"
if errorlevel 1 goto :failed

echo.
echo Build complete and running: %~dp0%EXE_NAME%
exit /b 0

:python_missing
echo.
echo Python 3 was not found. Install it from https://www.python.org/downloads/windows/
echo During installation, select "Add Python to PATH", then run this file again.
exit /b 1

:failed
echo.
echo Build failed. Review the error messages above.
exit /b 1
