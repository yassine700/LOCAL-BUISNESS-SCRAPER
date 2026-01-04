# System Architecture - Generic Proxy API

## High-Level Architecture

```
╔════════════════════════════════════════════════════════════════════════════╗
║                          USER INTERFACE (Frontend)                          ║
║                                                                            ║
║  ┌──────────────────────────────────────────────────────────────────────┐ ║
║  │ Business Scraper                                                     │ ║
║  │                                                                      │ ║
║  │ Search Keyword: [___________]  "restaurant"                         │ ║
║  │ Cities:        [___________]  Toledo, OH                            │ ║
║  │                [___________]  St Pete, FL                           │ ║
║  │                [___________]  ...                                   │ ║
║  │                                                                      │ ║
║  │ Proxy API Key (Optional):                                           │ ║
║  │ [________________]  (password field)                                │ ║
║  │                                                                      │ ║
║  │ 📡 Direct scraping (FREE): Leave empty                             │ ║
║  │ 🔑 With proxy: Add ScrapingBee, Bright Data, Apify, etc.           │ ║
║  │                                                                      │ ║
║  │                        [▶ Start Scraping]                           │ ║
║  └──────────────────────────────────────────────────────────────────────┘ ║
║                                                                            ║
║  WebSocket Connection: ws://localhost:8000/ws/{job_id}                    ║
║  Real-time Updates: Status, Progress, Results                             ║
╚════════════════════════════════════════════════════════════════════════════╝
                                    │
                                    │ POST /api/scrape
                                    │ {keyword, cities, sources, proxy_api_key}
                                    ↓
╔════════════════════════════════════════════════════════════════════════════╗
║                     BACKEND API (FastAPI, Port 8000)                       ║
║                                                                            ║
║  POST /api/scrape                                                         ║
║  ├─ Accept: keyword, cities, sources, proxy_api_key (optional)           ║
║  ├─ Validate inputs                                                       ║
║  ├─ Generate job_id (UUID)                                                ║
║  ├─ Store proxy_api_key if provided                                       ║
║  └─ Spawn Celery tasks (1 per city)                                      ║
║                                                                            ║
║  GET /api/status/{job_id}                                                 ║
║  └─ Return: job status, progress, business count                         ║
║                                                                            ║
║  WebSocket /ws/{job_id}                                                   ║
║  └─ Send real-time updates from Redis pub/sub                            ║
║                                                                            ║
║  GET /api/download/{job_id}                                              ║
║  └─ Return: CSV file with results                                        ║
╚════════════════════════════════════════════════════════════════════════════╝
                                    │
                                    │ Celery task dispatch
                                    ↓
╔════════════════════════════════════════════════════════════════════════════╗
║              BACKGROUND TASK QUEUE (Celery + Redis Broker)                 ║
║                                                                            ║
║  create_scraping_job_task()                                               ║
║  ├─ Create job record in database                                         ║
║  ├─ Store proxy_api_key in PROXY_API_KEY env var                         ║
║  └─ For each city:                                                        ║
║      └─ Dispatch scrape_business_task(job_id, keyword, city)             ║
║                                                                            ║
║  scrape_business_task(job_id, keyword, city)                             ║
║  └─ Invoke YellowPagesScraper.scrape()                                   ║
╚════════════════════════════════════════════════════════════════════════════╝
                                    │
                                    ↓
╔════════════════════════════════════════════════════════════════════════════╗
║                   SCRAPER ENGINE (YellowPagesScraper)                      ║
║                                                                            ║
║  For each page in YellowPages search:                                     ║
║  │                                                                        ║
║  ├─ Option A: Direct IP Scraping (No API key)                           ║
║  │  ├─ Build: https://www.yellowpages.com/search?...                   ║
║  │  ├─ Fetch with httpx (async HTTP client)                            ║
║  │  ├─ Parse HTML with BeautifulSoup                                   ║
║  │  └─ Extract listings with lxml                                       ║
║  │                                                                        ║
║  └─ Option B: Proxy API Scraping (With API key)                          ║
║     ├─ Check: USE_PROXY = bool(PROXY_API_KEY)                           ║
║     ├─ Initialize: ProxyAPIClient()                                      ║
║     │  ├─ Read API key: os.getenv("PROXY_API_KEY")                      ║
║     │  └─ Support: ScrapingBee, Bright Data, Apify, etc.               ║
║     │                                                                     ║
║     └─ Fetch page through proxy service:                                 ║
║        ├─ POST to service API with URL                                   ║
║        ├─ Receive rendered HTML                                          ║
║        ├─ Parse with BeautifulSoup                                       ║
║        └─ Extract listings                                               ║
║                                                                            ║
║  For each listing on page:                                               ║
║  ├─ Extract basic info (name, phone, category)                          ║
║  ├─ Visit detail page (same A/B scraping method)                        ║
║  └─ Extract website using:                                               ║
║     ├─ JSON-LD structured data (priority)                               ║
║     ├─ Heuristic patterns (fallback)                                    ║
║     └─ Regex patterns (final fallback)                                  ║
║                                                                            ║
║  For each business extracted:                                            ║
║  ├─ Check BLOCKED_DOMAINS filter                                         ║
║  ├─ Save to SQLite (deduplication)                                       ║
║  ├─ Emit event to Redis pub/sub                                          ║
║  └─ Update job progress                                                  ║
║                                                                            ║
║  After all pages:                                                        ║
║  ├─ Calculate extraction statistics                                      ║
║  ├─ Emit metrics to Redis                                                ║
║  └─ Mark task complete                                                   ║
╚════════════════════════════════════════════════════════════════════════════╝
                                    │
                                    ↓
╔════════════════════════════════════════════════════════════════════════════╗
║              PROXY API CLIENT (Generic - Works with Any Service)           ║
║                                                                            ║
║  Class: ProxyAPIClient                                                    ║
║  ├─ Supports: ScrapingBee, Bright Data, Apify, etc.                     ║
║  │                                                                        ║
║  ├─ Initialize:                                                          ║
║  │  └─ Read API key from PROXY_API_KEY environment variable             ║
║  │                                                                        ║
║  ├─ Method: fetch_url(url, country_code="us", premium_proxy=True)      ║
║  │  ├─ Build request parameters                                         ║
║  │  ├─ POST to proxy API (currently: ScrapingBee, can change)          ║
║  │  ├─ Retry on rate limit or server error                            ║
║  │  └─ Return HTML response                                             ║
║  │                                                                        ║
║  └─ Error Handling:                                                      ║
║     ├─ 400: Invalid API key                                             ║
║     ├─ 429: Rate limited (retry with backoff)                          ║
║     ├─ 500+: Server error (retry)                                       ║
║     └─ Timeout: Network error (retry)                                   ║
║                                                                            ║
║  Backward Compatibility:                                                 ║
║  ├─ Alias: ScrapingBeeClient = ProxyAPIClient                           ║
║  └─ Function: get_scrapingbee_client() → ProxyAPIClient()              ║
╚════════════════════════════════════════════════════════════════════════════╝
                                    │
                                    ↓
╔════════════════════════════════════════════════════════════════════════════╗
║                        DATABASE (SQLite)                                   ║
║                                                                            ║
║  Tables:                                                                 ║
║  ├─ jobs (job_id, keyword, status, started_at, completed_at)           ║
║  ├─ tasks (job_id, keyword, city, status, progress)                    ║
║  └─ businesses (                                                        ║
║      job_id, business_name, website, city, source,                    ║
║      UNIQUE(business_name, website, city, source)  ← Deduplication    ║
║     )                                                                    ║
║                                                                            ║
║  Purpose:                                                                ║
║  ├─ Store results persistently                                          ║
║  ├─ Track job progress                                                  ║
║  ├─ Enable pause/resume                                                ║
║  └─ Support pagination on resume                                        ║
╚════════════════════════════════════════════════════════════════════════════╝
                                    │
                                    ├─────────────────────────────────────┐
                                    │                                     │
                                    ↓                                     ↓
╔════════════════════════════════════════════════════════════════════════════╗
║                 REDIS MESSAGE QUEUE (Real-time Events)                     ║
║                                                                            ║
║  Channels:                                                               ║
║  ├─ job:{job_id}:events                                                 ║
║  │  └─ Business scraped events (for WebSocket broadcasting)             ║
║  │                                                                       ║
║  └─ job:{job_id}:metrics                                                ║
║     └─ Extraction statistics (methods used, success rates)              ║
║                                                                           ║
║  Message Format:                                                        ║
║  {                                                                       ║
║    "type": "business" | "extraction_stats",                            ║
║    "job_id": "uuid",                                                    ║
║    "data": {...}                                                        ║
║  }                                                                       ║
╚════════════════════════════════════════════════════════════════════════════╝
                                                                             │
                                                                             └─ Broadcast to connected WebSocket clients
                                                                                    │
                                                                                    ↓
                                                                    ┌──────────────────────────┐
                                                                    │ Frontend WebSocket Update│
                                                                    │ - Refresh business count │
                                                                    │ - Update progress bar    │
                                                                    │ - Add row to results     │
                                                                    │ - Show current city      │
                                                                    └──────────────────────────┘
```

## Configuration Flow

```
User submits form with optional proxy_api_key
    │
    ↓
Frontend sends POST /api/scrape {proxy_api_key: "key"}
    │
    ↓
Backend stores in environment: os.environ["PROXY_API_KEY"] = proxy_api_key
    │
    ↓
Celery worker reads: PROXY_API_KEY = os.getenv("PROXY_API_KEY", "")
    │
    ↓
Check: USE_PROXY = bool(PROXY_API_KEY)
    │
    ├─ If True:  Initialize ProxyAPIClient() → Uses provided API key
    │
    └─ If False: Use direct httpx scraping (Free)
```

## Proxy Service Support Matrix

```
┌──────────────┬──────────────┬──────────┬──────────┬──────────────┐
│ Service      │ API Key Type │ Endpoint │ Supports │ Cost         │
├──────────────┼──────────────┼──────────┼──────────┼──────────────┤
│ ScrapingBee  │ api_key      │ Standard │ ✅ YES   │ Free-$200/mo │
│ Bright Data  │ user_key     │ Custom   │ ✅ YES   │ $300+/mo     │
│ Apify        │ api_key      │ Standard │ ✅ YES   │ Free-$25+/mo │
│ Oxylabs      │ user:pass    │ Custom   │ ✅ YES   │ $200+/mo     │
│ SmartProxy   │ api_key      │ Standard │ ✅ YES   │ $0-300+/mo   │
│ Bright Data  │ Standard     │ HTTP API │ ✅ YES   │ Custom       │
└──────────────┴──────────────┴──────────┴──────────┴──────────────┘

✅ Supported: Any service with standard HTTP API + API key authentication
⚠️ Requires: Adapter may need modification for custom endpoints
```

## Data Flow During Scraping

```
Scrape Job Created
    │
    ├─ Create Job Record
    │  ├─ job_id: UUID
    │  ├─ keyword: "restaurant"
    │  ├─ cities: ["Toledo, OH", "St Pete, FL"]
    │  └─ status: "running"
    │
    ├─ For each city in parallel:
    │  │
    │  ├─ For each page (1-25):
    │  │  │
    │  │  ├─ Fetch page
    │  │  │  ├─ If USE_PROXY:
    │  │  │  │  └─ ProxyAPIClient.fetch_url(url)
    │  │  │  └─ Else:
    │  │  │     └─ httpx.get(url)
    │  │  │
    │  │  ├─ Parse HTML
    │  │  ├─ Extract listings (30 per page avg)
    │  │  │
    │  │  └─ For each listing:
    │  │     │
    │  │     ├─ Fetch detail page
    │  │     ├─ Extract website
    │  │     ├─ Validate domain
    │  │     │
    │  │     ├─ Check deduplication:
    │  │     │  ├─ name + website + city = unique key
    │  │     │  └─ Skip if already in database
    │  │     │
    │  │     ├─ Save to database (if new)
    │  │     │
    │  │     ├─ Emit Redis event
    │  │     │  └─ job:{job_id}:events → {type:"business"...}
    │  │     │
    │  │     └─ WebSocket broadcast to frontend
    │  │        └─ Update results table
    │  │
    │  └─ After all pages for city:
    │     ├─ Calculate extraction stats
    │     ├─ Emit Redis metrics
    │     │  └─ job:{job_id}:metrics → {type:"extraction_stats"...}
    │     └─ Mark city task complete
    │
    └─ After all cities:
       ├─ Mark job complete
       ├─ Calculate overall statistics
       └─ Enable CSV export
```

---

This architecture provides:
- ✅ **Flexibility**: Switch proxy providers without code changes
- ✅ **Scalability**: Multiple cities processed in parallel
- ✅ **Reliability**: Retry logic, error handling, deduplication
- ✅ **Real-time**: WebSocket updates to frontend during scraping
- ✅ **Cost efficiency**: Free direct scraping or any paid provider
- ✅ **Maintainability**: Generic, service-agnostic code
