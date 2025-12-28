"""
Celery app configuration and task definitions.
"""
from celery import Celery
from backend.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
import logging
import uuid

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "business_scraper",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes per task
    task_soft_time_limit=240,  # 4 minutes soft limit
)


@celery_app.task(bind=True, name="scrape_business")
def scrape_business_task(self, job_id: str, keyword: str, city: str, source: str):
    """
    Celery task to scrape businesses for a single (city, source) combination.
    
    Note: Celery tasks don't support async/await directly, so we use asyncio.run
    """
    import asyncio
    from backend.scrapers.yellowpages import YellowPagesScraper
    from backend.database import db
    
    async def run_scraper():
        # Only YellowPages supported
        if source != "yellowpages":
            logger.error(f"Unsupported source: {source}. Only yellowpages is supported.")
            db.increment_completed_tasks(job_id)
            return
        
        scraper = YellowPagesScraper()
        
        # Callback for real-time updates (emit via Redis pub/sub or direct DB flag)
        def on_business_callback(business, is_duplicate, page, city_name):
            """Callback when a business is scraped - save immediately and emit event."""
            saved = db.save_business(
                job_id=job_id,
                business_name=business.get("business_name", ""),
                website=business.get("website"),
                city=city_name,
                source=source
            )
            # Emit event via Redis pub/sub for WebSocket distribution
            try:
                import redis
                from backend.config import REDIS_URL
                redis_client = redis.from_url(REDIS_URL)
                redis_client.publish(
                    f"job:{job_id}:events",
                    f'{{"type":"business","job_id":"{job_id}","data":{{"name":"{business.get("business_name","")}","website":"{business.get("website","")}","city":"{city_name}","state":"{city_name.split(",")[-1].strip() if "," in city_name else ""}","page":{page},"status":"{"duplicate" if not saved else "new"}","duplicate":{str(not saved).lower()}}}}}'
                )
            except Exception as e:
                logger.debug(f"Failed to emit event: {e}")
        
        try:
            # Scrape businesses (pass job_id and callback for real-time updates)
            businesses = await scraper.scrape(keyword, city, job_id=job_id, on_business_scraped=on_business_callback)
            
            # Count saved businesses (some may already be saved via callback)
            saved_count = len([b for b in businesses if b.get("business_name")])
            
            logger.info(f"Completed scraping for {city} ({source}). Total businesses: {saved_count}")
            
        except Exception as e:
            logger.error(f"Error in scrape task for {city} ({source}): {e}", exc_info=True)
        finally:
            # Mark task as completed
            db.increment_completed_tasks(job_id)
    
    # Run async scraper
    asyncio.run(run_scraper())


@celery_app.task(name="create_scraping_job")
def create_scraping_job_task(job_id: str, keyword: str, cities: list, sources: list):
    """
    Create scraping job and spawn tasks for each (keyword × city) combination.
    Since we only support YellowPages, sources is ignored but kept for compatibility.
    """
    from backend.database import db
    
    # Force YellowPages only
    sources = ["yellowpages"]
    
    # Create job in database
    db.create_job(job_id, keyword, cities, sources)
    db.update_job_status(job_id, "running")
    
    # Spawn tasks: (keyword × city) → YellowPages only
    # One task per city (each task handles pagination internally)
    for city in cities:
        celery_app.send_task("scrape_business", args=[job_id, keyword, city, "yellowpages"])
    
    logger.info(f"Created scraping job {job_id} with {len(cities)} tasks (one per city)")
    return job_id

