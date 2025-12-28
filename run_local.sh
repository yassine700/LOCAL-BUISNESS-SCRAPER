#!/bin/bash
# Script to run the scraper locally (without Docker)

echo "Starting Local Business Scraper..."

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Error: Redis is not running. Please start Redis first."
    echo "  macOS: brew services start redis"
    echo "  Linux: sudo systemctl start redis"
    echo "  Windows: redis-server (or use WSL)"
    exit 1
fi

echo "✓ Redis is running"

# Start API server in background
echo "Starting API server..."
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait a bit for API to start
sleep 2

# Start Celery worker
echo "Starting Celery worker..."
celery -A backend.celery_app worker --loglevel=info --concurrency=4 &
WORKER_PID=$!

echo ""
echo "✓ API server running on http://localhost:8000 (PID: $API_PID)"
echo "✓ Celery worker running (PID: $WORKER_PID)"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for Ctrl+C
trap "echo ''; echo 'Stopping services...'; kill $API_PID $WORKER_PID; exit" INT
wait

