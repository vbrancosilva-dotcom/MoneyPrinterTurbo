@echo off
setlocal
set "CURRENT_DIR=%CD%"
set "PYTHONPATH=%CURRENT_DIR%"

if not defined MPT_STORY_HOST set "MPT_STORY_HOST=127.0.0.1"
if not defined MPT_STORY_PORT set "MPT_STORY_PORT=8502"

set "STREAMLIT_CMD="
if exist "%CURRENT_DIR%\.venv\Scripts\python.exe" (
    set "STREAMLIT_CMD="%CURRENT_DIR%\.venv\Scripts\python.exe" -m streamlit"
) else (
    where uv >nul 2>nul
    if not errorlevel 1 set "STREAMLIT_CMD=uv run streamlit"
)

if not defined STREAMLIT_CMD (
    echo Python environment not found. Run: uv sync --frozen
    pause
    exit /b 1
)

echo Story WebUI: http://%MPT_STORY_HOST%:%MPT_STORY_PORT%
%STREAMLIT_CMD% run .\webui\Story.py --server.address=%MPT_STORY_HOST% --server.port=%MPT_STORY_PORT% --browser.gatherUsageStats=False --client.toolbarMode=minimal
