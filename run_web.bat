@echo off
echo ============================================================
echo  GUIOC Web Dashboard — http://localhost:7788
echo ============================================================
echo.

if "%ANTHROPIC_API_KEY%"=="" (
    echo [ERROR] ANTHROPIC_API_KEY is not set.
    echo Set it with:  set ANTHROPIC_API_KEY=sk-ant-...
    echo.
    pause
    exit /b 1
)

python guioc.py --web --port 7788
pause
