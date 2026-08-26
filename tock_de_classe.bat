@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%"

set "STREAMLIT_CMD="
if exist "%CD%\.venv\Scripts\python.exe" (
    set "STREAMLIT_CMD="%CD%\.venv\Scripts\python.exe" -m streamlit"
) else (
    where uv >nul 2>nul
    if not errorlevel 1 set "STREAMLIT_CMD=uv run streamlit"
)

if not defined STREAMLIT_CMD (
    echo Python do projeto ou uv nao encontrado.
    echo Execute primeiro: py -3.11 -m venv .venv
    echo Depois instale: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Abrindo Tock de Classe em http://127.0.0.1:8502
%STREAMLIT_CMD% run .\webui\TockDeClasse.py --server.address=127.0.0.1 --server.port=8502 --browser.gatherUsageStats=False --client.toolbarMode=minimal
