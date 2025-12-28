@echo off
REM Script to run the scraper locally on Windows

echo Starting Local Business Scraper...

REM Check if Redis is running (basic check)
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo Error: Redis is not running. Please start Redis first.
    echo   Download Redis from https://redis.io/download
    echo   Or use WSL: sudo apt-get install redis-server ^&^& redis-server
    pause
    exit /b 1
)

echo [OK] Redis is running

REM Start API server
echo Starting API server...
start "API Server" cmd /k "python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"

REM Wait a bit
timeout /t 3 /nobreak >nul

REM Start Celery worker
echo Starting Celery worker...
start "Celery Worker" cmd /k "celery -A backend.celery_app worker --loglevel=info --concurrency=4"

echo.
echo [OK] API server running on http://localhost:8000
echo [OK] Celery worker running
echo.
echo Both windows are now open. Close them when done.
pause

