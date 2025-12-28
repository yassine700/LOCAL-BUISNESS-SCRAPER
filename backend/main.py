"""
FastAPI application for the business scraper.
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
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
    
    # Create job task
    create_scraping_job_task.delay(
        job_id=job_id,
        keyword=request.keyword,
        cities=request.cities,
        sources=request.sources
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
        import redis
        from backend.config import REDIS_URL
        redis_client = redis.from_url(REDIS_URL)
        pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(f"job:{job_id}:events")
        
        # Task to listen for Redis messages and forward to WebSocket
        async def redis_listener():
            while True:
                try:
                    message = pubsub.get_message(timeout=1.0)
                    if message and message['type'] == 'message':
                        try:
                            import json
                            event_data = json.loads(message['data'].decode('utf-8'))
                            await websocket.send_json(event_data)
                        except Exception as e:
                            logger.debug(f"Error forwarding Redis message: {e}")
                except Exception:
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
    """Pause a running scraping job."""
    success = db.pause_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or not in running state")
    
    # Notify WebSocket clients
    status = db.get_job_status(job_id)
    if status:
        await manager.send_status_update(job_id, status)
    
    return {"status": "paused", "message": "Job paused successfully"}


@app.post("/api/job/{job_id}/resume")
async def resume_job(job_id: str):
    """Resume a paused scraping job."""
    success = db.resume_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or not in paused state")
    
    # Trigger resume by spawning new tasks for remaining work
    job_status = db.get_job_status(job_id)
    if job_status:
        # Re-spawn tasks for cities that haven't completed
        from backend.celery_app import celery_app
        keyword = job_status["keyword"]
        cities = job_status["cities"]
        
        # Spawn tasks for all cities (they'll resume from last page)
        for city in cities:
            celery_app.send_task("scrape_business", args=[job_id, keyword, city, "yellowpages"])
    
    # Notify WebSocket clients
    status = db.get_job_status(job_id)
    if status:
        await manager.send_status_update(job_id, status)
    
    return {"status": "running", "message": "Job resumed successfully"}


@app.post("/api/job/{job_id}/kill")
async def kill_job(job_id: str):
    """Immediately kill a scraping job."""
    success = db.kill_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Notify WebSocket clients
    status = db.get_job_status(job_id)
    if status:
        await manager.send_status_update(job_id, status)
    
    # Note: Celery workers check job status and will exit on their own
    # when they see status = "killed"
    
    return {"status": "killed", "message": "Job killed successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

