"""
Event emission helper for Phase 2: Event sourcing.
Saves events to DB (source of truth) then publishes to Redis (real-time).
"""
import json
import logging
from typing import Dict, Any
import redis
from backend.config import REDIS_URL
from backend.database import db

logger = logging.getLogger(__name__)

# Singleton Redis client (reuse connection)
_redis_client = None

def _get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL)
            # Test connection
            _redis_client.ping()
            logger.info("[PIPELINE DEBUG] Redis client initialized successfully")
        except Exception as e:
            logger.error(f"[PIPELINE DEBUG] Failed to initialize Redis client: {e}", exc_info=True)
            _redis_client = None
    return _redis_client


def emit_event(job_id: str, event_type: str, data: Dict[str, Any], channel: str = "events") -> int:
    """
    Emit an event: save to DB first (source of truth), then publish to Redis (real-time).
    
    Args:
        job_id: Job ID
        event_type: Type of event (business, status, warning, error, etc.)
        data: Event payload dictionary
        channel: Redis channel suffix ("events" or "metrics")
    
    Returns:
        Sequence number of the saved event
    """
    try:
        # Step 1: Save to DB (source of truth)
        payload = {
            "type": event_type,
            "job_id": job_id,
            "data": data
        }
        sequence = db.save_event(job_id, event_type, payload)
        
        # Step 2: Publish to Redis (real-time streaming)
        try:
            redis_client = _get_redis_client()
            if not redis_client:
                logger.warning(f"[PIPELINE DEBUG] Redis client not available, skipping publish (event saved to DB)")
            else:
                # Include sequence in Redis message for frontend tracking
                redis_payload = {
                    "type": event_type,
                    "job_id": job_id,
                    "data": data,
                    "sequence": sequence  # Frontend can track last seen sequence
                }
                redis_channel = f"job:{job_id}:{channel}"
                redis_message = json.dumps(redis_payload)
                subscribers = redis_client.publish(redis_channel, redis_message)
                logger.info(f"[PIPELINE DEBUG] Published to Redis channel '{redis_channel}': event_type={event_type}, sequence={sequence}, subscribers={subscribers}")
                if subscribers == 0:
                    logger.warning(f"[PIPELINE DEBUG] No subscribers on channel '{redis_channel}' - WebSocket may not be connected")
                logger.debug(f"Emitted event {event_type} (seq={sequence}) for job {job_id}")
        except Exception as e:
            # Redis failure is non-critical - event is already in DB
            logger.error(f"[PIPELINE DEBUG] Failed to publish event to Redis (event saved to DB): {e}", exc_info=True)
        
        return sequence
        
    except Exception as e:
        logger.error(f"Failed to emit event {event_type} for job {job_id}: {e}", exc_info=True)
        # Return 0 to indicate failure (caller can handle)
        return 0

