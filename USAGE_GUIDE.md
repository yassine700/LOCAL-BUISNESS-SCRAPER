# 🎯 How to Use the Business Scraper

## Your application is running! Here's how to use it:

### Step 1: Open the Web Interface

Open your web browser and go to:
**http://localhost:8000**

You should see the Local Business Scraper interface.

### Step 2: Create a Scraping Job

Fill in the form:

1. **Search Keyword**: 
   - Enter: `computer shop`
   - (or any business type: restaurant, gym, dentist, etc.)

2. **Cities** (one per line):
   ```
   New York
   Chicago
   Los Angeles
   ```

3. **Data Sources**:
   - ✅ YellowPages (checked)
   - ✅ Yelp (checked)
   - ⚠️ Search Engines (disabled - coming soon)

4. Click **"🚀 Start Scraping"**

### Step 3: Monitor Progress

After clicking Start Scraping, you'll see:

- **Job ID**: Unique identifier for your job
- **Status**: 
  - `PENDING` → `RUNNING` → `COMPLETED`
- **Progress**: 
  - Shows: `completed_tasks / total_tasks (percentage%)`
  - Progress bar updates in real-time
- **Refresh Status**: Click to manually update (auto-refreshes every 2 seconds)

### Step 4: Download Results

Once status shows **COMPLETED**:

1. Click **"📥 Download CSV"** button
2. Save the file (contains all scraped businesses)
3. Open in Excel/Google Sheets to view results

## Example CSV Output

The downloaded CSV will have columns:
- `business_name`: Name of the business
- `website`: Website URL (if found)
- `city`: City where business is located
- `source`: Data source (yellowpages or yelp)
- `scraped_at`: Timestamp when scraped

## Tips

### For Best Results:
- Start with 1-3 cities to test
- Use specific keywords (e.g., "computer repair shop" vs just "computer")
- Allow some time for scraping (each city+source combination takes 1-3 minutes)

### If Scraping is Slow:
- This is normal - we have delays to avoid being blocked
- Check the worker logs in the Docker terminal for progress
- Some sites may block requests - this is expected

### Troubleshooting:
- **No results?** Some sites block scrapers. Try different keywords/cities.
- **Job stuck?** Check Docker logs: `docker-compose logs worker`
- **API error?** Check API logs: `docker-compose logs api`

## Testing the API Directly

You can also test using curl or Postman:

```bash
# Create a job
curl -X POST "http://localhost:8000/api/scrape" \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "computer shop",
    "cities": ["New York", "Chicago"],
    "sources": ["yellowpages", "yelp"]
  }'

# Check status (replace JOB_ID)
curl "http://localhost:8000/api/status/JOB_ID"

# Download results (replace JOB_ID)
curl "http://localhost:8000/api/download/JOB_ID" -o results.csv
```

## What Happens Behind the Scenes

1. **Job Created**: API receives your request
2. **Tasks Generated**: Creates one task per (city × source) combination
   - Example: 3 cities × 2 sources = 6 tasks
3. **Tasks Queued**: Sent to Redis message queue
4. **Worker Processing**: Celery worker picks up tasks and scrapes
5. **Results Saved**: Businesses saved to SQLite database
6. **Progress Updated**: Status updates in real-time
7. **Completion**: When all tasks done, status → COMPLETED

## Stopping the Application

Press `Ctrl+C` in the terminal where Docker Compose is running, or:

```bash
docker-compose down
```

To restart:
```bash
docker-compose up
```

## Viewing Logs

See what's happening:
```bash
# All services
docker-compose logs -f

# Just worker
docker-compose logs -f worker

# Just API
docker-compose logs -f api
```

---

**Ready to scrape? Go to http://localhost:8000!** 🚀

