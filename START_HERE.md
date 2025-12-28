# 🚀 Quick Start Guide for Windows

## Current Status

✅ **Python is installed** (3.12.4)  
✅ **Dependencies are mostly installed**  
❌ **Redis is NOT installed** (Required for background tasks)  
❌ **Docker is NOT installed** (Optional, for easy setup)

## What You Need to Do

### Option 1: Install Redis via WSL (Recommended - Easiest)

1. **Install WSL** (if not already installed):
   ```powershell
   wsl --install
   ```
   - Restart your computer when prompted

2. **After restart**, open WSL and install Redis:
   ```bash
   sudo apt-get update
   sudo apt-get install redis-server
   redis-server
   ```
   - Keep this terminal open (Redis must stay running)

3. **In a new PowerShell**, start the API:
   ```powershell
   cd "C:\Users\think\Desktop\local buisness scraper"
   python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **In another PowerShell**, start the worker:
   ```powershell
   cd "C:\Users\think\Desktop\local buisness scraper"
   celery -A backend.celery_app worker --loglevel=info --concurrency=4
   ```

5. **Open browser**: http://localhost:8000

### Option 2: Install Redis for Windows

1. Download Memurai (Redis-compatible for Windows):
   - https://www.memurai.com/get-memurai
   - Install and start the service

2. Then follow steps 3-5 from Option 1

### Option 3: Install Docker Desktop (Easiest - No Redis setup needed)

1. Download Docker Desktop for Windows:
   - https://www.docker.com/products/docker-desktop/

2. Install and start Docker Desktop

3. Run:
   ```powershell
   docker compose up
   ```
   (Note: Use `docker compose` not `docker-compose` in newer versions)

4. Open browser: http://localhost:8000

## Test Without Redis (Limited Functionality)

If you just want to see the web interface:

```powershell
cd "C:\Users\think\Desktop\local buisness scraper"
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000 - you'll see the UI, but scraping jobs won't work without Redis + Celery worker.

## Verify Everything Works

Once Redis and workers are running:

1. Open http://localhost:8000
2. Enter:
   - Keyword: `computer shop`
   - Cities:
     ```
     New York
     Chicago
     ```
   - Sources: YellowPages, Yelp
3. Click "Start Scraping"
4. Watch the progress bar
5. Download CSV when done

## Need Help?

- See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for detailed setup instructions
- See [README.md](README.md) for full documentation

