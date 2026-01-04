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
    task_time_limit=1800,  # 30 minutes per task (direct scraping takes longer)
    task_soft_time_limit=1700,  # 28 minutes soft limit
)


@celery_app.task(bind=True, name="scrape_business")
def scrape_business_task(self, job_id: str, keyword: str, city: str, source: str, proxy_api_key: str = None):
    """
    Celery task to scrape businesses for a single (city, source) combination.
    
    PHASE 2: Now supports true cancellation via Celery revoke().
    
    Note: Celery tasks don't support async/await directly, so we use asyncio.run
    """
    import asyncio
    import json
    import os
    from backend.scrapers.yellowpages import YellowPagesScraper
    from backend.database import db
    from backend.event_emitter import emit_event
    
    # FIX Bug 1: Set proxy API key in worker process environment
    # Environment variables are process-specific, so we must set it in the worker process
    if proxy_api_key:
        os.environ["PROXY_API_KEY"] = proxy_api_key
    
    # PHASE 2: Store task ID for cancellation
    celery_task_id = self.request.id
    db.save_task_id(job_id, city, celery_task_id)
    logger.info(f"Task {celery_task_id} started for job {job_id}, city {city}")
    
    async def run_scraper():
        # FIX Bug 2: Track if task completed normally (for finally block)
        task_completed = False
        saved_count = 0
        exception_occurred = False
        exception_message = None
        
        # PHASE 2: Check if task was cancelled before starting
        # FIX: Check revocation state - Celery's is_aborted() may not be available in all versions
        # Instead, check job status in DB which is updated when task is revoked
        is_revoked = False
        try:
            # Check if task was revoked by checking job status
            job_status = db.get_job_status_simple(job_id)
            if job_status in ("killed", "cancelled"):
                is_revoked = True
        except:
            pass
        
        if is_revoked:
            logger.info(f"Task {celery_task_id} was aborted before starting")
            db.mark_task_cancelled(job_id, city)
            task_completed = True
            # Will be handled in finally block
        
        # Check job status
        elif not task_completed:
            job_status = db.get_job_status_simple(job_id)
            if job_status in ("killed", "cancelled"):
                logger.info(f"Job {job_id} is {job_status}, cancelling task")
                db.mark_task_cancelled(job_id, city)
                task_completed = True
                # Will be handled in finally block
        
        # Only YellowPages supported
        if not task_completed and source != "yellowpages":
            logger.error(f"Unsupported source: {source}. Only yellowpages is supported.")
            db.mark_task_completed(job_id, city, result_count=0, error_message=f"Unsupported source: {source}")
            task_completed = True
            # Will be handled in finally block
        
        # Only proceed with scraping if task wasn't cancelled/failed early
        if not task_completed:
            scraper = YellowPagesScraper()
            
            # FIX Bug 1: Track saved count in callback (only new businesses, not duplicates)
            # Note: saved_count already declared in outer scope for finally block
            
            # PHASE 2: Callback uses event emitter (DB first, then Redis)
            def on_business_callback(business, is_duplicate, page, city_name):
                """Callback when a business is scraped - save immediately and emit event."""
                nonlocal saved_count  # FIX Bug 1: Track saved count in closure
                
                logger.info(f"[PIPELINE DEBUG] Callback invoked: {business.get('business_name', 'unknown')} (page {page}, city {city_name})")
                
                # Check for cancellation before processing
                # FIX: Check job status in DB instead of using is_aborted() which may not exist
                try:
                    job_status = db.get_job_status_simple(job_id)
                    if job_status in ("killed", "cancelled"):
                        logger.info(f"Task {celery_task_id} aborted during business processing (job {job_status})")
                        return
                except Exception as e:
                    # Log error but continue processing
                    logger.debug(f"Error checking job status: {e}")
                
                saved = db.save_business(
                    job_id=job_id,
                    business_name=business.get("business_name", ""),
                    website=business.get("website"),
                    city=city_name,
                    source=source
                )
                
                logger.info(f"[PIPELINE DEBUG] Business saved to DB: {saved} for {business.get('business_name', 'unknown')}")
                
                # FIX Bug 1: Increment saved_count only if business was actually saved (not duplicate)
                if saved:
                    saved_count += 1
                
                # PHASE 2: Use event emitter (saves to DB, then Redis)
                # FIX: Simplified to only business name and website for live parsing
                event_data = {
                    "name": business.get("business_name", ""),
                    "website": business.get("website", ""),
                    "city": city_name,
                    "page": page,
                    "status": "duplicate" if not saved else "new",
                    "duplicate": not saved
                }
                logger.info(f"[PIPELINE DEBUG] Emitting business event: {event_data}")
                sequence = emit_event(
                    job_id=job_id,
                    event_type="business",
                    data=event_data
                )
                logger.info(f"[PIPELINE DEBUG] Event emitted with sequence: {sequence}")
            
            try:
                # Scrape businesses (pass job_id and callback for real-time updates)
                businesses = await scraper.scrape(keyword, city, job_id=job_id, on_business_scraped=on_business_callback)
                
                # Calculate extraction statistics (from scraper results, for metrics)
                total_businesses = len([b for b in businesses if b.get("business_name")])
                with_website = sum(1 for b in businesses if b.get("website"))
                extraction_rate = (with_website / total_businesses * 100) if total_businesses > 0 else 0
                
                # Count by extraction method
                methods_used = {
                    "json_ld": sum(1 for b in businesses if b.get("extraction_method") == "json_ld"),
                    "heuristic": sum(1 for b in businesses if b.get("extraction_method") == "heuristic"),
                    "regex": sum(1 for b in businesses if b.get("extraction_method") == "regex"),
                    "none": sum(1 for b in businesses if not b.get("website"))
                }
                
                # Create extraction stats
                extraction_stats = {
                    "total_businesses": total_businesses,
                    "with_website": with_website,
                    "website_extraction_rate": round(extraction_rate, 2),
                    "methods_used": methods_used
                }
                
                # Log extraction stats
                logger.info(f"City {city} extraction stats: {extraction_stats}")
                
                # PHASE 2: Emit zero-result warning using event emitter
                if total_businesses == 0:
                    emit_event(
                        job_id=job_id,
                        event_type="warning",
                        data={
                            "city": city,
                            "reason": "zero_results",
                            "message": f"No businesses found for '{keyword}' in {city}. This may indicate blocking, invalid search, or no matching businesses."
                        }
                    )
                    logger.warning(f"Zero results for {city} - warning event emitted")
                
                # PHASE 2: Emit metrics using event emitter
                emit_event(
                    job_id=job_id,
                    event_type="extraction_stats",
                    data=extraction_stats,
                    channel="metrics"
                )
                
                logger.info(f"Completed scraping for {city} ({source}). Total businesses: {saved_count}")
                task_completed = True
                
            except Exception as e:
                # PHASE 2: Track exception and mark task as failed
                exception_occurred = True
                exception_message = str(e)
                logger.error(f"TASK FAILED for {city} ({source}): {e}", exc_info=True)
                
                # Emit error event
                emit_event(
                    job_id=job_id,
                    event_type="error",
                    data={
                        "city": city,
                        "error": exception_message,
                        "message": f"Task failed for {city}: {exception_message}"
                    }
                )
                task_completed = True
        
        # FIX Bug 2: Always increment completed_tasks counter, even for early returns
        # This ensures job completion detection works correctly
        if task_completed:
            # PHASE 2: Mark task as completed in task_status table (if not already cancelled)
            # Check if task was cancelled by checking if it exists in task_status with cancelled status
            task_status = db.get_task_status(job_id, city)
            if task_status and task_status.get("status") == "cancelled":
                # Task was cancelled - already marked, just increment counter
                logger.info(f"Task {celery_task_id} was cancelled, incrementing counter only")
            elif exception_occurred:
                # Task failed with exception
                db.mark_task_completed(job_id, city, result_count=0, error_message=exception_message)
                logger.error(f"Task for {city} completed with ERROR state. Error: {exception_message}")
            else:
                # Task completed successfully (or unsupported source)
                # Only mark if not already marked (unsupported source already marked itself)
                if not task_status or task_status.get("status") not in ("cancelled", "success", "failed"):
                    db.mark_task_completed(job_id, city, result_count=saved_count)
            
            # Always increment completed_tasks counter for job completion detection
            # This applies to all terminal states: success, failure, cancellation
            db.increment_completed_tasks(job_id)
            logger.info(f"Task {celery_task_id} completion counter incremented for job {job_id}")
        else:
            # This should never happen, but log if it does
            logger.warning(f"Task {celery_task_id} exited without completing - counter not incremented!")
    
    # Run async scraper
    asyncio.run(run_scraper())


@celery_app.task(name="create_scraping_job")
def create_scraping_job_task(job_id: str, keyword: str, cities: list, sources: list, proxy_api_key: str = None):
    """
    Create scraping job and spawn tasks for each (city) combination.
    Supports optional proxy API key for proxy-based scraping.
    """
    from backend.database import db
    
    # Force YellowPages only
    sources = ["yellowpages"]
    
    # Create job in database
    db.create_job(job_id, keyword, cities, sources)
    db.update_job_status(job_id, "running")
    db.update_started_at(job_id)
    
    # FIX Bug 1: Don't set environment here - it won't propagate to worker processes
    # Instead, pass proxy_api_key as a parameter to scrape_business tasks
    # The worker process will set it in its own environment
    
    # Spawn tasks: (keyword × city) → YellowPages only
    # One task per city (each task handles pagination internally)
    # FIX Bug 1: Pass proxy_api_key to worker tasks so they can use it
    for city in cities:
        celery_app.send_task("scrape_business", args=[job_id, keyword, city, "yellowpages"], kwargs={"proxy_api_key": proxy_api_key})
    
    logger.info(f"Created scraping job {job_id} with {len(cities)} tasks (one per city)")
    return job_id

