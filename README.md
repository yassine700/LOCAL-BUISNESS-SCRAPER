# Local Business Scraper

A scalable Local Business Scraper with a simple web interface that allows you to scrape business names and websites across multiple cities using YellowPages and Yelp.

## Features

- 🎯 **Multi-city scraping**: Scrape businesses across hundreds of cities
- 🔄 **Multiple data sources**: YellowPages, Yelp (with extensible architecture)
- 🚀 **Async-first design**: Fast parallel scraping with Celery workers
- 🛡️ **Anti-bot measures**: Proxy rotation, headers, delays, retries
- 📊 **Real-time status**: Monitor job progress via web interface
- 📥 **CSV export**: Download results as CSV files
- 🐳 **Docker support**: Easy deployment with Docker Compose

## Architecture

- **Backend**: FastAPI for REST API
- **Task Queue**: Celery + Redis for distributed task processing
- **Scrapers**: Modular async scrapers for each data source
- **Database**: SQLite for storing results
- **Frontend**: Simple HTML/CSS/JavaScript (no framework required)

## Prerequisites

- Python 3.11+
- Redis (for Celery broker)
- Docker & Docker Compose (optional, for containerized deployment)

## Installation

### Option 1: Docker Compose (Recommended)

1. Clone or download this project
2. Run with Docker Compose:

```bash
docker-compose up
```

This will start:
- Redis on port 6379
- API server on http://localhost:8000
- Celery worker(s)

### Option 2: Manual Setup

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Start Redis (required for Celery):

**On Windows:**
- Download Redis from https://redis.io/download
- Or use WSL: `sudo apt-get install redis-server && redis-server`

**On macOS:**
```bash
brew install redis
brew services start redis
```

**On Linux:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

3. Start the API server:

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

4. In a separate terminal, start the Celery worker:

```bash
celery -A backend.celery_app worker --loglevel=info --concurrency=4
```

## Usage

1. **Open the web interface**: Navigate to http://localhost:8000

2. **Create a scraping job**:
   - Enter a search keyword (e.g., "computer shop")
   - Enter cities, one per line:
     ```
     New York
     Chicago
     Los Angeles
     ```
   - Select data sources (YellowPages, Yelp)
   - Click "Start Scraping"

3. **Monitor progress**: The status section shows:
   - Job ID
   - Current status (pending/running/completed)
   - Progress (completed tasks / total tasks)
   - Progress bar

4. **Download results**: When the job is complete, click "Download CSV" to get all scraped businesses.

## Example

```
Keyword: computer shop
Cities:
  New York
  Chicago
  Los Angeles
Sources: YellowPages, Yelp
```

This will create 6 tasks (3 cities × 2 sources) and scrape businesses from each source.

## API Endpoints

- `POST /api/scrape` - Create a new scraping job
  ```json
  {
    "keyword": "computer shop",
    "cities": ["New York", "Chicago"],
    "sources": ["yellowpages", "yelp"]
  }
  ```

- `GET /api/status/{job_id}` - Get job status and progress

- `GET /api/download/{job_id}` - Download results as CSV

## Configuration

Environment variables:

- `REDIS_URL`: Redis connection URL (default: `redis://localhost:6379/0`)
- `DB_PATH`: Database file path (default: `business_scraper.db`)
- `PROXY_LIST`: Comma-separated list of proxy URLs (optional)
- `REQUEST_TIMEOUT`: HTTP request timeout in seconds (default: 30)
- `MAX_RETRIES`: Maximum retry attempts (default: 3)
- `MIN_DELAY` / `MAX_DELAY`: Random delay range between requests (default: 1-3 seconds)

## Project Structure

```
.
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── database.py          # Database models and operations
│   ├── celery_app.py        # Celery tasks
│   ├── config.py            # Configuration
│   └── scrapers/
│       ├── __init__.py
│       ├── base.py          # Base scraper class
│       ├── yellowpages.py   # YellowPages scraper
│       └── yelp.py          # Yelp scraper
├── frontend/
│   ├── index.html           # Main HTML page
│   ├── styles.css           # Stylesheet
│   └── app.js               # JavaScript logic
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile               # Docker image definition
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Anti-Bot Measures

The scrapers include several anti-bot measures:

- **Proxy rotation**: Optional proxy support (set `PROXY_LIST` env var)
- **Randomized headers**: User-Agent rotation and realistic headers
- **Delays**: Random delays between requests (1-3 seconds by default)
- **Retry logic**: Automatic retries with exponential backoff
- **Rate limit handling**: Detects 429 responses and adjusts delays

## Database Schema

**jobs table:**
- `job_id`: Unique job identifier
- `keyword`: Search keyword
- `cities`: Comma-separated list of cities
- `sources`: Comma-separated list of sources
- `status`: Job status (pending/running/completed)
- `total_tasks`: Total number of tasks
- `completed_tasks`: Number of completed tasks

**businesses table:**
- `job_id`: Associated job ID
- `business_name`: Name of the business
- `website`: Website URL (nullable)
- `city`: City name
- `source`: Data source (yellowpages/yelp)
- `scraped_at`: Timestamp

## Scaling

The system is designed for scalability:

- **Horizontal scaling**: Add more Celery workers
- **Async operations**: All scrapers are async
- **Deduplication**: Prevents duplicate entries in database
- **Task-level parallelism**: Each (city, source) combination is a separate task

## Troubleshooting

1. **Redis connection error**: Make sure Redis is running
   ```bash
   redis-cli ping  # Should return PONG
   ```

2. **No results**: Check if the scrapers are being blocked. Consider:
   - Adding proxies (set `PROXY_LIST`)
   - Increasing delays
   - Checking network connectivity

3. **Worker not processing tasks**: Ensure the Celery worker is running and connected to Redis

## License

MIT License - Feel free to use and modify as needed.

## Notes

- This is a local MVP tool - no authentication required
- Designed for internal use and testing
- Respects robots.txt and rate limits where possible
- Results are stored locally in SQLite database

