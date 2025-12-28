# Quick Start Guide

## Option 1: Docker Compose (Easiest)

1. **Start everything:**
   ```bash
   docker-compose up
   ```

2. **Open browser:**
   Navigate to http://localhost:8000

3. **Start scraping:**
   - Enter keyword: `computer shop`
   - Enter cities (one per line):
     ```
     New York
     Chicago
     Los Angeles
     ```
   - Select sources (YellowPages, Yelp)
   - Click "Start Scraping"

That's it! The system will:
- Create scraping tasks
- Process them in parallel
- Show real-time progress
- Allow CSV download when complete

## Option 2: Manual Setup

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Start Redis

**Windows:**
- Download from https://redis.io/download
- Run `redis-server`

**macOS:**
```bash
brew install redis
brew services start redis
```

**Linux:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

Verify Redis is running:
```bash
redis-cli ping
# Should return: PONG
```

### Step 3: Start API Server

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4: Start Celery Worker

In a new terminal:
```bash
celery -A backend.celery_app worker --loglevel=info --concurrency=4
```

### Step 5: Use the Web Interface

Open http://localhost:8000 in your browser and start scraping!

## Windows Quick Start

Use the provided batch script:

```cmd
run_local.bat
```

This will:
- Check if Redis is running
- Start the API server in one window
- Start the Celery worker in another window

## Testing the API

You can also test the API directly:

```bash
# Create a scraping job
curl -X POST "http://localhost:8000/api/scrape" \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "computer shop",
    "cities": ["New York", "Chicago"],
    "sources": ["yellowpages", "yelp"]
  }'

# Check job status (replace JOB_ID)
curl "http://localhost:8000/api/status/JOB_ID"

# Download results (replace JOB_ID)
curl "http://localhost:8000/api/download/JOB_ID" -o results.csv
```

## Troubleshooting

**Issue: Redis connection error**
- Make sure Redis is installed and running
- Check: `redis-cli ping`

**Issue: No results from scrapers**
- This is normal if sites block the requests
- Consider adding proxies (set `PROXY_LIST` environment variable)
- Increase delays in `backend/config.py`

**Issue: Worker not processing**
- Check if worker is connected to Redis
- Check worker logs for errors
- Verify job was created: Check the database or API status endpoint

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Configure proxies for better success rates
- Scale by adding more Celery workers
- Extend scrapers to add more data sources

