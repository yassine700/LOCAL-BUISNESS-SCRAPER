"""
FastAPI application for the business scraper.
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uuid
import csv
import os
import tempfile
import logging
import asyncio

from backend.database import db
from backend.celery_app import create_scraping_job_task
from backend.websocket_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Local Business Scraper API")

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (frontend)
static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    # Also serve CSS and JS files directly
    @app.get("/styles.css")
    async def get_css():
        css_path = os.path.join(static_dir, "styles.css")
        if os.path.exists(css_path):
            from fastapi.responses import FileResponse
            return FileResponse(css_path, media_type="text/css")
        raise HTTPException(status_code=404)
    
    @app.get("/app.js")
    async def get_js():
        js_path = os.path.join(static_dir, "app.js")
        if os.path.exists(js_path):
            from fastapi.responses import FileResponse
            return FileResponse(js_path, media_type="application/javascript")
        raise HTTPException(status_code=404)


class ScrapeRequest(BaseModel):
    keyword: str
    cities: List[str]
    sources: List[str]
    proxy_api_key: Optional[str] = None


@app.get("/")
async def root():
    """Serve the frontend HTML."""
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        from fastapi.responses import HTMLResponse
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {"message": "Local Business Scraper API", "status": "running"}


@app.post("/api/scrape")
async def create_scrape_job(request: ScrapeRequest):
    """
    Create a new scraping job.
    
    Request body:
    {
        "keyword": "computer shop",
        "cities": ["New York", "Chicago"],
        "sources": ["yellowpages", "yelp"]
    }
    """
    if not request.keyword:
        raise HTTPException(status_code=400, detail="Keyword is required")
    
    if not request.cities:
        raise HTTPException(status_code=400, detail="At least one city is required")
    
    if not request.sources:
        raise HTTPException(status_code=400, detail="At least one source is required")
    
    # Only allow YellowPages
    if not request.sources or "yellowpages" not in request.sources:
        request.sources = ["yellowpages"]
    
    # Filter to only yellowpages
    request.sources = [s for s in request.sources if s == "yellowpages"]
    
    if not request.sources:
        raise HTTPException(
            status_code=400,
            detail="Only YellowPages is currently supported as a data source"
        )
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Create job task with optional proxy API key
    create_scraping_job_task.delay(
        job_id=job_id,
        keyword=request.keyword,
        cities=request.cities,
        sources=request.sources,
        proxy_api_key=request.proxy_api_key
    )
    
    logger.info(f"Created scraping job {job_id} for keyword: {request.keyword}")
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Scraping job created"
    }


@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a scraping job."""
    status = db.get_job_status(job_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return status


@app.get("/api/businesses/{job_id}")
async def get_businesses_json(job_id: str):
    """Get businesses for a job as JSON."""
    # Check if job exists
    status = db.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get businesses
    businesses = db.get_businesses(job_id)
    
    # Transform to match frontend format
    result = []
    for biz in businesses:
        result.append({
            "name": biz["business_name"],
            "website": biz["website"] or "",
            "city": biz["city"],
            "source": biz["source"],
            "status": "new",
            "duplicate": False
        })
    
    return {"businesses": result, "count": len(result)}


@app.get("/api/jobs/{job_id}/events")
async def get_job_events(job_id: str, since: int = 0):
    """
    PHASE 2: Event replay endpoint.
    Get events for a job since a given sequence number.
    
    Args:
        job_id: Job ID
        since: Sequence number to start from (default: 0 = all events)
    
    Returns:
        List of events with sequence numbers
    """
    # Check if job exists
    status = db.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get events
    events = db.get_events(job_id, since_sequence=since)
    
    return {
        "job_id": job_id,
        "since": since,
        "events": events,
        "count": len(events)
    }


@app.get("/api/download/{job_id}")
async def download_results(job_id: str):
    """Download scraping results as CSV."""
    # Check if job exists
    status = db.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get businesses
    businesses = db.get_businesses(job_id)
    
    if not businesses:
        raise HTTPException(status_code=404, detail="No results found for this job")
    
    # Create CSV file
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='')
    
    try:
        writer = csv.DictWriter(temp_file, fieldnames=["business_name", "website", "city", "source", "scraped_at"])
        writer.writeheader()
        writer.writerows(businesses)
        temp_file.close()
        
        return FileResponse(
            temp_file.name,
            media_type="text/csv",
            filename=f"businesses_{job_id}.csv",
            background=lambda: os.unlink(temp_file.name)  # Clean up after download
        )
    except Exception as e:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        raise HTTPException(status_code=500, detail=f"Error creating CSV: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# WebSocket endpoint for real-time updates
@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job updates."""
    await manager.connect(websocket)
    try:
        # Send initial status
        status = db.get_job_status(job_id)
        if status:
            await manager.send_personal_message({
                "type": "status",
                "job_id": job_id,
                "data": status
            }, websocket)
        
        # Subscribe to Redis pub/sub for real-time events
        # FIX: Subscribe to both events and metrics channels to receive all backend signals
        import redis
        from backend.config import REDIS_URL
        redis_client = redis.from_url(REDIS_URL)
        pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(f"job:{job_id}:events")
        pubsub.subscribe(f"job:{job_id}:metrics")  # Subscribe to metrics channel for extraction_stats
        
        # Task to listen for Redis messages and forward to WebSocket
        async def redis_listener():
            while True:
                try:
                    # FIX: pubsub.get_message() is blocking - must run in thread pool to avoid blocking event loop
                    message = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
                    if message and message['type'] == 'message':
                        try:
                            import json
                            event_data = json.loads(message['data'].decode('utf-8'))
                            # Log business events for debugging
                            if event_data.get('type') == 'business':
                                logger.info(f"[PIPELINE DEBUG] Forwarding business event to WebSocket: {event_data.get('data', {}).get('name', 'unknown')}")
                            await websocket.send_json(event_data)
                            logger.debug(f"[PIPELINE DEBUG] WebSocket sent event type={event_data.get('type')}")
                        except Exception as e:
                            logger.error(f"Error forwarding Redis message: {e}", exc_info=True)
                except Exception as e:
                    logger.debug(f"Redis listener error: {e}")
                    break
        
        # Task to periodically send status updates
        async def status_updater():
            while True:
                await asyncio.sleep(2)
                try:
                    status = db.get_job_status(job_id)
                    if status:
                        await websocket.send_json({
                            "type": "status",
                            "job_id": job_id,
                            "data": status
                        })
                except Exception:
                    break
        
        # Run both tasks concurrently
        listener_task = asyncio.create_task(redis_listener())
        updater_task = asyncio.create_task(status_updater())
        
        # Keep connection alive and handle pings
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.debug(f"WebSocket receive error: {e}")
                break
        
        # Cleanup
        listener_task.cancel()
        updater_task.cancel()
        try:
            pubsub.close()
        except:
            pass
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Job control endpoints
@app.post("/api/job/{job_id}/pause")
async def pause_job(job_id: str):
    """Pause a running scraping job. PHASE 2: Now cancels active Celery tasks."""
    success = db.pause_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or not in running state")
    
    # PHASE 2: Cancel active Celery tasks
    from backend.celery_app import celery_app
    active_tasks = db.get_all_active_task_ids(job_id)
    cancelled_count = 0
    
    for task_info in active_tasks:
        try:
            celery_app.control.revoke(task_info["celery_task_id"], terminate=True)
            db.mark_task_cancelled(job_id, task_info["city"])
            cancelled_count += 1
            logger.info(f"Cancelled task {task_info['celery_task_id']} for city {task_info['city']}")
        except Exception as e:
            logger.error(f"Failed to cancel task {task_info['celery_task_id']}: {e}")
    
    logger.info(f"Paused job {job_id}: cancelled {cancelled_count} active tasks")
    
    # Emit status update event
    from backend.event_emitter import emit_event
    emit_event(
        job_id=job_id,
        event_type="status",
        data={"status": "paused", "message": f"Job paused, {cancelled_count} tasks cancelled"}
    )
    
    # Notify WebSocket clients
    status = db.get_job_status(job_id)
    if status:
        await manager.send_status_update(job_id, status)
    
    return {"status": "paused", "message": f"Job paused successfully. {cancelled_count} tasks cancelled."}


@app.post("/api/job/{job_id}/resume")
async def resume_job(job_id: str):
    """Resume a paused scraping job. PHASE 2: Only spawns tasks for incomplete cities."""
    success = db.resume_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or not in paused state")
    
    # PHASE 2: Only spawn tasks for cities not in terminal state
    job_status = db.get_job_status(job_id)
    if job_status:
        from backend.celery_app import celery_app
        keyword = job_status["keyword"]
        cities = job_status["cities"]
        
        # Get cities that are incomplete (not success/failed/cancelled)
        incomplete_cities = db.get_incomplete_cities(job_id)
        
        # Also check scrape progress for cities not in task_status yet
        from backend.config import MAX_PAGES
        for city in cities:
            if city not in incomplete_cities:
                # Check if city has a task status
                task_status = db.get_task_status(job_id, city)
                if not task_status:
                    # No task status yet, check scrape progress
                    last_page = db.get_scrape_progress(job_id, keyword, city)
                    if last_page < MAX_PAGES:
                        incomplete_cities.append(city)
                elif task_status["status"] not in ("success", "failed", "cancelled"):
                    incomplete_cities.append(city)
        
        # Remove duplicates
        incomplete_cities = list(set(incomplete_cities))
        
        if incomplete_cities:
            spawned_count = 0
            for city in incomplete_cities:
                # Only spawn if not already running
                task_status = db.get_task_status(job_id, city)
                if not task_status or task_status["status"] in ("cancelled", "failed"):
                    # FIX Bug 1: Pass proxy_api_key (None for now - proxy key not stored in DB)
                    # TODO: Store proxy_api_key in jobs table for resume capability
                    celery_app.send_task("scrape_business", args=[job_id, keyword, city, "yellowpages"], kwargs={"proxy_api_key": None})
                    spawned_count += 1
                    logger.debug(f"Resumed: spawned task for {city}")
            
            logger.info(f"Resumed job {job_id}: spawned {spawned_count} tasks for incomplete cities")
        else:
            logger.info(f"Job {job_id} all cities already completed, no tasks to spawn")
    
    # Emit status update event
    from backend.event_emitter import emit_event
    emit_event(
        job_id=job_id,
        event_type="status",
        data={"status": "running", "message": "Job resumed"}
    )
    
    # Notify WebSocket clients
    status = db.get_job_status(job_id)
    if status:
        await manager.send_status_update(job_id, status)
    
    return {"status": "running", "message": "Job resumed successfully"}


@app.post("/api/job/{job_id}/kill")
async def kill_job(job_id: str):
    """Immediately kill a scraping job. PHASE 2: Now cancels active Celery tasks."""
    success = db.kill_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # PHASE 2: Cancel all active Celery tasks
    from backend.celery_app import celery_app
    active_tasks = db.get_all_active_task_ids(job_id)
    cancelled_count = 0
    
    for task_info in active_tasks:
        try:
            celery_app.control.revoke(task_info["celery_task_id"], terminate=True)
            db.mark_task_cancelled(job_id, task_info["city"])
            cancelled_count += 1
            logger.info(f"Killed task {task_info['celery_task_id']} for city {task_info['city']}")
        except Exception as e:
            logger.error(f"Failed to kill task {task_info['celery_task_id']}: {e}")
    
    logger.info(f"Killed job {job_id}: cancelled {cancelled_count} active tasks")
    
    # Emit status update event
    from backend.event_emitter import emit_event
    emit_event(
        job_id=job_id,
        event_type="status",
        data={"status": "killed", "message": f"Job killed, {cancelled_count} tasks cancelled"}
    )
    
    # Notify WebSocket clients
    status = db.get_job_status(job_id)
    if status:
        await manager.send_status_update(job_id, status)
    
    return {"status": "killed", "message": f"Job killed successfully. {cancelled_count} tasks cancelled."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

