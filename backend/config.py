"""
Configuration settings for the scraper.
"""
import os
from typing import List

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# Database
DB_PATH = os.getenv("DB_PATH", "business_scraper.db")

# Scraping configuration
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "2.0"))
# MIN_DELAY, MAX_DELAY, MAX_RETRIES, MAX_PAGES are set based on SCRAPER_MODE above

# ScrapingBee configuration
SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY", "")
USE_SCRAPINGBEE = bool(SCRAPINGBEE_API_KEY)

# Scraper mode: "safe" or "high_volume"
SCRAPER_MODE = os.getenv("SCRAPER_MODE", "high_volume").lower()

# Mode-specific settings
if SCRAPER_MODE == "safe":
    MAX_PAGES = 5
    MIN_DELAY = 2.0
    MAX_DELAY = 4.0
    MAX_RETRIES = 1  # No retries in safe mode
else:  # high_volume
    MAX_PAGES = 25
    MIN_DELAY = 1.0
    MAX_DELAY = 2.0
    MAX_RETRIES = 3

# Proxy configuration (legacy, not used with ScrapingBee)
# Format: "http://proxy1:port,http://proxy2:port"
PROXY_LIST = os.getenv("PROXY_LIST", "").split(",") if os.getenv("PROXY_LIST") else []

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Headers for requests
def get_headers() -> dict:
    """
    Get randomized headers for requests that look like a real Chrome browser.
    Headers are rotated every request to avoid detection.
    """
    import random
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": random.choice(["none", "same-origin", "cross-site"]),
        "Sec-Fetch-User": "?1",
        "Cache-Control": random.choice(["max-age=0", "no-cache", ""]),
    }

