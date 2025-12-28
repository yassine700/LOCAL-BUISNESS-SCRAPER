# Windows Setup Guide

Since Docker is not installed, here's how to set up and run the scraper on Windows manually.

## Step 1: Install Redis

Redis is required for Celery to work. You have several options:

### Option A: Use WSL (Windows Subsystem for Linux) - Recommended

1. Install WSL if you haven't already:
   ```powershell
   wsl --install
   ```
   (You'll need to restart your computer)

2. After restart, open WSL and install Redis:
   ```bash
   sudo apt-get update
   sudo apt-get install redis-server
   ```

3. Start Redis in WSL:
   ```bash
   redis-server
   ```

### Option B: Install Redis for Windows

1. Download Redis for Windows from:
   - Official: https://github.com/microsoftarchive/redis/releases
   - Or use Memurai (Redis-compatible): https://www.memurai.com/

2. Install and start Redis service

### Option C: Use Redis in Docker (if you install Docker later)

```powershell
docker run -d -p 6379:6379 redis:7-alpine
```

## Step 2: Verify Dependencies

Most Python packages should already be installed. If there were any errors:

```powershell
pip install fastapi uvicorn celery redis httpx beautifulsoup4 lxml
```

**Note**: If you get permission errors, try running PowerShell as Administrator, or use:
```powershell
python -m pip install --user <package-name>
```

## Step 3: Start the Application

### Terminal 1: Start the API Server

Open PowerShell and navigate to the project directory:

```powershell
cd "C:\Users\think\Desktop\local buisness scraper"
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Terminal 2: Start the Celery Worker

Open a **new** PowerShell window:

```powershell
cd "C:\Users\think\Desktop\local buisness scraper"
celery -A backend.celery_app worker --loglevel=info --concurrency=4
```

You should see:
```
celery@hostname v5.3.4 ready.
```

## Step 4: Use the Web Interface

1. Open your web browser
2. Navigate to: **http://localhost:8000**
3. Enter:
   - Keyword: `computer shop`
   - Cities (one per line):
     ```
     New York
     Chicago
     Los Angeles
     ```
   - Select sources: YellowPages, Yelp
4. Click "Start Scraping"

## Troubleshooting

### "Redis connection refused" error

- Make sure Redis is running
- Check Redis is listening on port 6379:
  ```powershell
  # In WSL:
  redis-cli ping
  # Should return: PONG
  ```

### "Module not found" errors

Install missing packages:
```powershell
pip install <package-name>
```

### Port 8000 already in use

Change the port:
```powershell
python -m uvicorn backend.main:app --reload --port 8001
```
Then open http://localhost:8001

### Permission errors during pip install

1. Run PowerShell as Administrator
2. Or install to user directory:
   ```powershell
   python -m pip install --user <package>
   ```

## Quick Test

Test if everything works:

```powershell
# Test API health
curl http://localhost:8000/api/health
```

Should return: `{"status":"healthy"}`

## Alternative: Use the Batch Script

I've created a batch script (`run_local.bat`) that can help start both services, but you'll still need Redis running first.

## Next Steps

- Read [QUICKSTART.md](QUICKSTART.md) for more details
- Read [README.md](README.md) for full documentation
- Configure proxies (optional) for better scraping success rates

