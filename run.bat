@echo off
echo ============================================================
echo  GUIOC — Autonomous Computer Use Agent
echo ============================================================
echo.

if "%ANTHROPIC_API_KEY%"=="" (
    echo [ERROR] ANTHROPIC_API_KEY is not set.
    echo Set it with:  set ANTHROPIC_API_KEY=sk-ant-...
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    python guioc.py --interactive
) else (
    python guioc.py %*
)
