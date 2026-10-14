@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Falta el entorno local .venv de Nucleus.
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0app.py" %*
