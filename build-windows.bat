@echo off
setlocal

cd /d "%~dp0Windows_and_Linux"

echo [1/4] Finding Python...
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
    echo [2/4] Creating build environment...
    python -m venv .build-venv
    if errorlevel 1 goto :failed
)
goto :build

:python_found
if not exist ".build-venv\Scripts\python.exe" (
    echo [2/4] Creating build environment...
    py -3 -m venv .build-venv
    if errorlevel 1 goto :failed
)

:build
set "BUILD_PYTHON=%CD%\.build-venv\Scripts\python.exe"

echo [3/4] Installing build dependencies...
"%BUILD_PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

echo [4/4] Building Writing Tools...
"%BUILD_PYTHON%" pyinstaller-build-script.py
if errorlevel 1 goto :failed

set "EXE_NAME="
for %%F in ("dist\Writing Tools v*.exe") do if exist "%%~fF" set "EXE_NAME=%%~nxF"
if not defined EXE_NAME goto :failed
if not exist "dist\%EXE_NAME%" goto :failed

copy /y "dist\%EXE_NAME%" "%~dp0%EXE_NAME%" >nul
if errorlevel 1 goto :failed

echo.
echo Build complete: %~dp0%EXE_NAME%
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
