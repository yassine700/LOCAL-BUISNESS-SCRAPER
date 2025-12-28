"""
WebSocket manager for real-time job updates.
"""
from typing import Set
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSocket clients."""
        if not self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")
                disconnected.add(connection)
        
        # Remove disconnected connections
        for connection in disconnected:
            self.disconnect(connection)
    
    async def send_business_update(self, job_id: str, business: dict, is_duplicate: bool, page: int, city: str):
        """Send a business scraped event to all connected clients."""
        message = {
            "type": "business",
            "job_id": job_id,
            "data": {
                "name": business.get("business_name", ""),
                "website": business.get("website", ""),
                "city": city,
                "state": city.split(",")[-1].strip() if "," in city else "",
                "page": page,
                "status": "duplicate" if is_duplicate else "new",
                "duplicate": is_duplicate
            }
        }
        await self.broadcast(message)
    
    async def send_status_update(self, job_id: str, status: dict):
        """Send a job status update to all connected clients."""
        message = {
            "type": "status",
            "job_id": job_id,
            "data": status
        }
        await self.broadcast(message)
    
    async def send_progress_update(self, job_id: str, city: str, page: int, businesses_count: int):
        """Send a progress update to all connected clients."""
        message = {
            "type": "progress",
            "job_id": job_id,
            "data": {
                "city": city,
                "page": page,
                "businesses_count": businesses_count
            }
        }
        await self.broadcast(message)


# Global connection manager instance
manager = ConnectionManager()

