@echo off
setlocal

for %%I in ("%~dp0.") do set "REPO_DIR=%%~fI"
set "APP_DIR=%REPO_DIR%\Windows_and_Linux"
set "PYTHON=%APP_DIR%\.build-venv\Scripts\python.exe"
set "RUNTIME_DIR=%LOCALAPPDATA%\Writing Tools\Source Runtime"

if not exist "%PYTHON%" (
    echo Writing Tools' Python environment was not found:
    echo %PYTHON%
    goto :failed
)

if not exist "%APP_DIR%\main.py" (
    echo Writing Tools' source entry point was not found:
    echo %APP_DIR%\main.py
    goto :failed
)

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
if errorlevel 1 (
    echo Could not create the source runtime folder:
    echo %RUNTIME_DIR%
    goto :failed
)

if not exist "%RUNTIME_DIR%\config.json" (
    if not exist "%REPO_DIR%\config.json" (
        echo No existing Writing Tools config.json was found.
        goto :failed
    )
    copy /y "%REPO_DIR%\config.json" "%RUNTIME_DIR%\config.json" >nul
    if errorlevel 1 (
        echo Could not initialize the source runtime config.
        goto :failed
    )
)

set "OPTIONS_SOURCE=%REPO_DIR%\options.json"
if not exist "%OPTIONS_SOURCE%" set "OPTIONS_SOURCE=%APP_DIR%\options.json"
if not exist "%RUNTIME_DIR%\options.json" (
    if not exist "%OPTIONS_SOURCE%" (
        echo Writing Tools options.json was not found.
        goto :failed
    )
    copy /y "%OPTIONS_SOURCE%" "%RUNTIME_DIR%\options.json" >nul
    if errorlevel 1 (
        echo Could not initialize the source runtime options.
        goto :failed
    )
)

if not exist "%APP_DIR%\icons\" (
    echo Writing Tools' icons folder was not found:
    echo %APP_DIR%\icons
    goto :failed
)

xcopy "%APP_DIR%\icons\*" "%RUNTIME_DIR%\icons\" /E /I /Y >nul
if errorlevel 1 (
    echo Could not prepare Writing Tools' source icons.
    goto :failed
)

echo Writing Tools is starting from source. Keep this window open while it runs.
pushd "%RUNTIME_DIR%"
"%PYTHON%" -c "import sys;sys.path.insert(0,r'%APP_DIR%');sys.argv[0]=r'%RUNTIME_DIR%\main.py';exec(compile(open(r'%APP_DIR%\main.py',encoding='utf-8').read(),r'%APP_DIR%\main.py','exec'),{'__name__':'__main__','__file__':r'%APP_DIR%\main.py'})"
set "APP_EXIT_CODE=%ERRORLEVEL%"
popd
if not "%APP_EXIT_CODE%"=="0" (
    echo Writing Tools exited with code %APP_EXIT_CODE%.
    goto :failed
)

echo Writing Tools has closed.
endlocal
exit /b 0

:failed
echo.
pause
endlocal
exit /b 1
