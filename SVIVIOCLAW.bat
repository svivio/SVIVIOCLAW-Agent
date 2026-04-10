@echo off
echo ================================================================
echo   SVIVIOCLAW — Autonomous Computer Use Agent by Vivaan.io
echo   Competing: OpenClaw  ^|  Manus  ^|  Perplexity Computer
echo ================================================================
echo.

if "%ANTHROPIC_API_KEY%"=="" (
    set /p ANTHROPIC_API_KEY="Enter your Anthropic API key: "
)

echo Choose a mode:
echo   [1] Desktop GUI  (recommended)
echo   [2] Web Dashboard  (http://localhost:7788)
echo   [3] Interactive CLI
echo   [4] Run a single task
echo.
set /p choice="Enter choice (1-4): "

if "%choice%"=="1" (
    python svivioclaw.py --gui
) else if "%choice%"=="2" (
    python svivioclaw.py --web
) else if "%choice%"=="3" (
    python svivioclaw.py --interactive
) else if "%choice%"=="4" (
    set /p task="Enter task: "
    python svivioclaw.py "%task%"
) else (
    python svivioclaw.py --gui
)
pause
