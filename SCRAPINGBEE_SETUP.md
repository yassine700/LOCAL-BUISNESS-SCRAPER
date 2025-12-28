# ScrapingBee Integration Guide

## Overview

The YellowPages scraper now uses **ScrapingBee** for residential proxy and anti-bot protection, enabling high-volume scraping with minimal blocking.

## Setup

### 1. Get ScrapingBee API Key

1. Sign up at https://www.scrapingbee.com/
2. Get your API key from the dashboard
3. **Never share or commit your API key**

### 2. Set Environment Variable

**Linux/macOS:**
```bash
export SCRAPINGBEE_API_KEY="your_api_key_here"
```

**Windows (PowerShell):**
```powershell
$env:SCRAPINGBEE_API_KEY="your_api_key_here"
```

**Windows (CMD):**
```cmd
set SCRAPINGBEE_API_KEY=your_api_key_here
```

**Docker Compose:**
Add to `docker-compose.yml`:
```yaml
services:
  api:
    environment:
      - SCRAPINGBEE_API_KEY=${SCRAPINGBEE_API_KEY}
  worker:
    environment:
      - SCRAPINGBEE_API_KEY=${SCRAPINGBEE_API_KEY}
```

Then create `.env` file:
```
SCRAPINGBEE_API_KEY=your_api_key_here
```

### 3. Configure Scraper Mode

**Safe Mode** (for testing):
```bash
export SCRAPER_MODE=safe
```
- Max 5 pages per city
- 2-4 second delays
- No retries

**High-Volume Mode** (production):
```bash
export SCRAPER_MODE=high_volume
```
- Max 25 pages per city
- 1-2 second delays
- 3 retries per request

Default: `high_volume`

## How It Works

### Request Flow

```
Your Code → ScrapingBee API → Residential Proxy → YellowPages → HTML Response
```

1. Scraper calls `scrapingbee_client.fetch_url(url)`
2. ScrapingBee routes through US residential proxy
3. YellowPages sees legitimate US residential IP
4. HTML is returned to scraper
5. Scraper parses HTML normally

### Features

✅ **Residential IPs**: Real US residential IP addresses  
✅ **Anti-Bot Protection**: TLS fingerprinting, header realism  
✅ **CAPTCHA Handling**: Automatic CAPTCHA solving  
✅ **Browser Emulation**: Full Chrome-like headers  
✅ **Retry Logic**: Automatic retries on failures  

## Resume Capability

The scraper automatically saves progress and can resume from the last scraped page.

**How it works:**
- After each page, saves: `job_id + keyword + city + last_page`
- On restart, checks for existing progress
- Resumes from `last_page + 1`

**Example:**
- Job scraped pages 1-10, then crashed
- Restart job with same `job_id`, `keyword`, `city`
- Automatically resumes from page 11

## API Usage & Costs

### ScrapingBee Pricing

- **Free tier**: Limited requests/month
- **Paid plans**: Based on requests
- Each page = 1 request
- Each detail page = 1 request

**Cost example** (High-Volume mode):
- 10 cities × 25 pages × 30 listings/page = ~7,500 requests
- Plus detail pages = ~7,500 more requests
- Total: ~15,000 requests per full job

### Optimization Tips

1. **Use Safe Mode for Testing**: Test with 1-2 cities first
2. **Monitor API Usage**: Check ScrapingBee dashboard
3. **Resume Jobs**: Use resume capability to avoid re-scraping
4. **Batch Processing**: Process cities in smaller batches

## Fallback Behavior

If ScrapingBee is not configured (no API key):
- Falls back to direct HTTP requests
- May encounter 403 errors
- Suitable for local testing only

**Check if ScrapingBee is active:**
```python
from backend.config import USE_SCRAPINGBEE
print(f"ScrapingBee enabled: {USE_SCRAPINGBEE}")
```

## Error Handling

### Common Errors

**"Invalid API key"**
- Check environment variable is set correctly
- Verify API key is valid in ScrapingBee dashboard

**"Rate limited" (429)**
- ScrapingBee free tier limits exceeded
- Upgrade plan or wait for quota reset
- Reduce concurrency

**"Timeout"**
- Increase timeout in `scrapingbee_client.py`
- Check network connectivity
- YellowPages may be slow to respond

### Debugging

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security

✅ **API Key Security:**
- Never hardcoded
- Never logged or printed
- Only from environment variable
- Validated on startup

✅ **Request Security:**
- HTTPS only
- No sensitive data in URLs
- Proper error handling

## Testing

### Test ScrapingBee Connection

```python
from backend.scrapers.scrapingbee_client import get_scrapingbee_client
import asyncio

async def test():
    client = get_scrapingbee_client()
    html = await client.fetch_url("https://www.yellowpages.com/search?search_terms=test&geo_location_terms=New+York,NY")
    print(f"Success: {len(html) if html else 0} characters")

asyncio.run(test())
```

### Test Full Scraper

1. Set `SCRAPER_MODE=safe`
2. Run with 1 city, simple keyword
3. Check logs for ScrapingBee usage
4. Verify results in database

## Performance

**Expected throughput** (High-Volume mode):
- ~30-60 pages/minute (with delays)
- ~150-300 businesses/minute
- Limited by ScrapingBee rate limits

**Bottlenecks:**
1. ScrapingBee API rate limits
2. Network latency
3. YellowPages response time
4. Delay settings (1-2s per request)

## Next Steps

1. ✅ Get ScrapingBee API key
2. ✅ Set `SCRAPINGBEE_API_KEY` environment variable
3. ✅ Set `SCRAPER_MODE` (safe or high_volume)
4. ✅ Test with 1-2 cities
5. ✅ Monitor API usage
6. ✅ Scale up to full volume

---

**Questions?** Check ScrapingBee docs: https://www.scrapingbee.com/documentation/

