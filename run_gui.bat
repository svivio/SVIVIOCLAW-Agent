@echo off
echo ============================================================
echo  GUIOC Desktop GUI — Native Window
echo ============================================================
echo.

if "%ANTHROPIC_API_KEY%"=="" (
    echo [ERROR] ANTHROPIC_API_KEY is not set.
    echo Set it with:  set ANTHROPIC_API_KEY=sk-ant-...
    echo.
    pause
    exit /b 1
)

python guioc.py --gui %*
