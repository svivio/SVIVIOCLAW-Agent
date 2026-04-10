@echo off
echo ============================================================
echo  GUIOC Setup - Installing dependencies
echo ============================================================
echo.

pip install -r requirements.txt --quiet

if %errorlevel% neq 0 (
    echo [ERROR] pip install failed. Make sure Python is in your PATH.
    pause
    exit /b 1
)

echo.
echo [OK] All dependencies installed!
echo.
echo Next steps:
echo   1. Set your API key:   set ANTHROPIC_API_KEY=sk-ant-...
echo   2. Run the agent:      python guioc.py "your task here"
echo   3. Web dashboard:      python guioc.py --web
echo.
pause
