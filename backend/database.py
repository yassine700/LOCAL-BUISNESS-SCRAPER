"""
Database models and connection handling.
"""
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager
import os

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "business_scraper.db")


class Database:
    """SQLite database handler for storing scraped business data."""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS businesses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    business_name TEXT NOT NULL,
                    website TEXT,
                    city TEXT NOT NULL,
                    source TEXT NOT NULL,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(job_id, business_name, website, city, source)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE NOT NULL,
                    keyword TEXT NOT NULL,
                    cities TEXT NOT NULL,
                    sources TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    total_tasks INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    started_at TIMESTAMP,
                    paused_at TIMESTAMP
                )
            """)
            
            # Migration: Add missing columns if they don't exist
            cursor = conn.execute("PRAGMA table_info(jobs)")
            existing_columns = [row[1] for row in cursor.fetchall()]
            
            if 'started_at' not in existing_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN started_at TIMESTAMP")
            
            if 'paused_at' not in existing_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN paused_at TIMESTAMP")
            
            # Migration: Update businesses UNIQUE constraint to include job_id
            # This allows each job to have independent businesses (no cross-job deduplication)
            try:
                # Check if unique constraint needs updating
                cursor = conn.execute("PRAGMA index_list(businesses)")
                indexes = [row[1] for row in cursor.fetchall()]
                # If old constraint exists, we need to recreate the table
                # SQLite doesn't support DROP CONSTRAINT, so we'll recreate if needed
                # For now, we'll let the new constraint work on new inserts
                # Old data will still work, but new inserts will use job_id in uniqueness check
            except:
                pass  # Table might not exist yet
            
            conn.commit()
            
            # Resume capability: Track last page scraped per city
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scrape_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    city TEXT NOT NULL,
                    last_page INTEGER DEFAULT 0,
                    consecutive_403_count INTEGER DEFAULT 0,
                    is_blocked INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(job_id, keyword, city)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_job_id ON businesses(job_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_city_source ON businesses(city, source)
            """)
            
            # PHASE 2: Task status tracking for true cancellation
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    city TEXT NOT NULL,
                    celery_task_id TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    error_message TEXT,
                    result_count INTEGER DEFAULT 0,
                    UNIQUE(job_id, city)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_job_city ON task_status(job_id, city)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_celery_id ON task_status(celery_task_id)
            """)
            
            # PHASE 2: Event sourcing - DB as source of truth
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(job_id, sequence)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_job_seq ON job_events(job_id, sequence)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def create_job(self, job_id: str, keyword: str, cities: List[str], sources: List[str]) -> None:
        """
        Create a new scraping job.
        Note: Since we only support YellowPages, total_tasks = len(cities)
        (one task per city, each handles pagination internally)
        
        FIX: Clear previous job data to ensure fresh start for each run.
        """
        with self._get_connection() as conn:
            # Clear previous businesses for this job_id (if any)
            # This ensures each job run starts fresh
            conn.execute("DELETE FROM businesses WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM task_status WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM scrape_progress WHERE job_id = ?", (job_id,))
            
            # One task per city (YellowPages only)
            total_tasks = len(cities)
            # FIX Bug 2: Use JSON serialization instead of comma-separated strings
            # City names contain commas (e.g., "Toledo, OH"), so comma splitting breaks
            import json
            conn.execute(
                """
                INSERT INTO jobs (job_id, keyword, cities, sources, total_tasks)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, keyword, json.dumps(cities), json.dumps(sources), total_tasks)
            )
            conn.commit()
    
    def update_job_status(self, job_id: str, status: str) -> None:
        """Update job status."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE job_id = ?",
                (status, job_id)
            )
            if status == "completed":
                conn.execute(
                    "UPDATE jobs SET completed_at = ? WHERE job_id = ?",
                    (datetime.now().isoformat(), job_id)
                )
            conn.commit()
    
    def increment_completed_tasks(self, job_id: str) -> None:
        """
        Increment completed tasks counter.
        FIX Bug 2: Check completion in same transaction to avoid race conditions.
        """
        with self._get_connection() as conn:
            # Increment completed tasks
            conn.execute(
                "UPDATE jobs SET completed_tasks = completed_tasks + 1 WHERE job_id = ?",
                (job_id,)
            )
            
            # FIX Bug 2: Check if job is complete BEFORE committing
            # This ensures atomic check-and-update, preventing race conditions
            cursor = conn.execute(
                "SELECT total_tasks, completed_tasks, status FROM jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if row and row["total_tasks"] == row["completed_tasks"]:
                # Only update to completed if not already in terminal state
                # FIX Bug 2: Include "paused" to prevent auto-completion of paused jobs
                if row["status"] not in ("completed", "killed", "error", "paused"):
                    conn.execute(
                        "UPDATE jobs SET status = 'completed', completed_at = ? WHERE job_id = ?",
                        (datetime.now().isoformat(), job_id)
                    )
            
            conn.commit()
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get job status and progress."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT job_id, keyword, cities, sources, status, 
                       total_tasks, completed_tasks, created_at, completed_at,
                       started_at, paused_at
                FROM jobs WHERE job_id = ?
                """,
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            # Get business count
            count_cursor = conn.execute(
                "SELECT COUNT(*) as count FROM businesses WHERE job_id = ?",
                (job_id,)
            )
            count_row = count_cursor.fetchone()
            business_count = count_row["count"] if count_row else 0
            
            # FIX Bug 2: Deserialize JSON instead of splitting by comma
            # City names contain commas (e.g., "Toledo, OH"), so comma splitting breaks
            import json
            try:
                cities_list = json.loads(row["cities"]) if row["cities"] else []
            except (json.JSONDecodeError, TypeError):
                # Fallback for old data format (comma-separated)
                cities_list = row["cities"].split(",") if row["cities"] else []
            
            try:
                sources_list = json.loads(row["sources"]) if row["sources"] else []
            except (json.JSONDecodeError, TypeError):
                # Fallback for old data format (comma-separated)
                sources_list = row["sources"].split(",") if row["sources"] else []
            
            return {
                "job_id": row["job_id"],
                "keyword": row["keyword"],
                "cities": cities_list,
                "sources": sources_list,
                "status": row["status"],
                "total_tasks": row["total_tasks"],
                "completed_tasks": row["completed_tasks"],
                "progress": row["completed_tasks"] / row["total_tasks"] * 100 if row["total_tasks"] > 0 else 0,
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
                "started_at": row["started_at"],
                "paused_at": row["paused_at"],
                "business_count": business_count
            }
    
    def save_business(self, job_id: str, business_name: str, website: Optional[str], 
                     city: str, source: str) -> bool:
        """
        Save business data. Returns True if inserted, False if duplicate.
        
        FIX: Simplified to only save business_name and website.
        Removed cross-job deduplication - each job is independent.
        """
        with self._get_connection() as conn:
            try:
                # Simplified: Only save business_name and website
                # Each job is independent - no cross-job deduplication
                conn.execute(
                    """
                    INSERT INTO businesses (job_id, business_name, website, city, source)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (job_id, business_name, website, city, source)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Duplicate entry within same job, ignore
                return False
    
    def get_businesses(self, job_id: str) -> List[Dict]:
        """Get all businesses for a job."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT business_name, website, city, source, scraped_at
                FROM businesses WHERE job_id = ?
                ORDER BY city, source, business_name
                """,
                (job_id,)
            )
            return [
                {
                    "business_name": row["business_name"],
                    "website": row["website"] or "",
                    "city": row["city"],
                    "source": row["source"],
                    "scraped_at": row["scraped_at"]
                }
                for row in cursor.fetchall()
            ]
    
    def save_scrape_progress(self, job_id: str, keyword: str, city: str, last_page: int) -> None:
        """Save scraping progress to resume from last page."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scrape_progress (job_id, keyword, city, last_page, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (job_id, keyword, city, last_page)
            )
            conn.commit()
    
    def get_scrape_progress(self, job_id: str, keyword: str, city: str) -> int:
        """Get last page scraped for a job/city combination. Returns 0 if not found."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT last_page FROM scrape_progress
                WHERE job_id = ? AND keyword = ? AND city = ?
                """,
                (job_id, keyword, city)
            )
            row = cursor.fetchone()
            return row["last_page"] if row else 0
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a running job. Returns True if successful, False if job not found or not running."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            current_status = row["status"]
            if current_status != "running":
                return False
            
            conn.execute(
                "UPDATE jobs SET status = ?, paused_at = ? WHERE job_id = ?",
                ("paused", datetime.now().isoformat(), job_id)
            )
            conn.commit()
            return True
    
    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job. Returns True if successful, False if job not found or not paused."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            current_status = row["status"]
            if current_status != "paused":
                return False
            
            conn.execute(
                "UPDATE jobs SET status = ?, paused_at = NULL WHERE job_id = ?",
                ("running", job_id)
            )
            conn.commit()
            return True
    
    def kill_job(self, job_id: str) -> bool:
        """Kill a running or paused job. Returns True if successful, False if job not found or already terminal."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            current_status = row["status"]
            # Only allow killing if job is in a running or paused state
            if current_status not in ["running", "paused"]:
                return False
            
            conn.execute(
                "UPDATE jobs SET status = ? WHERE job_id = ?",
                ("killed", job_id)
            )
            conn.commit()
            return True
    
    def get_job_status_simple(self, job_id: str) -> Optional[str]:
        """Get just the status string for a job. Returns None if job not found."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            return row["status"] if row else None
    
    def update_started_at(self, job_id: str) -> None:
        """Set the started_at timestamp for a job."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET started_at = ? WHERE job_id = ?",
                (datetime.now().isoformat(), job_id)
            )
            conn.commit()
    
    def increment_403_count(self, job_id: str, keyword: str, city: str) -> int:
        """Increment consecutive 403 count. Returns new count."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO scrape_progress (job_id, keyword, city, consecutive_403_count)
                VALUES (?, ?, ?, 0)
                """,
                (job_id, keyword, city)
            )
            conn.execute(
                """
                UPDATE scrape_progress 
                SET consecutive_403_count = consecutive_403_count + 1, last_updated = CURRENT_TIMESTAMP
                WHERE job_id = ? AND keyword = ? AND city = ?
                """,
                (job_id, keyword, city)
            )
            cursor = conn.execute(
                "SELECT consecutive_403_count FROM scrape_progress WHERE job_id = ? AND keyword = ? AND city = ?",
                (job_id, keyword, city)
            )
            row = cursor.fetchone()
            conn.commit()
            return row["consecutive_403_count"] if row else 0
    
    def reset_403_count(self, job_id: str, keyword: str, city: str) -> None:
        """Reset consecutive 403 count on successful request."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE scrape_progress 
                SET consecutive_403_count = 0, last_updated = CURRENT_TIMESTAMP
                WHERE job_id = ? AND keyword = ? AND city = ?
                """,
                (job_id, keyword, city)
            )
            conn.commit()
    
    def set_city_blocked(self, job_id: str, keyword: str, city: str) -> None:
        """Mark a city as blocked due to persistent 403s."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO scrape_progress (job_id, keyword, city, is_blocked)
                VALUES (?, ?, ?, 1)
                """,
                (job_id, keyword, city)
            )
            conn.execute(
                """
                UPDATE scrape_progress 
                SET is_blocked = 1, last_updated = CURRENT_TIMESTAMP
                WHERE job_id = ? AND keyword = ? AND city = ?
                """,
                (job_id, keyword, city)
            )
            conn.commit()
    
    def is_city_blocked(self, job_id: str, keyword: str, city: str) -> bool:
        """Check if a city is marked as blocked."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT is_blocked FROM scrape_progress WHERE job_id = ? AND keyword = ? AND city = ?",
                (job_id, keyword, city)
            )
            row = cursor.fetchone()
            return row["is_blocked"] == 1 if row else False
    
    # PHASE 2: Task status tracking methods
    
    def save_task_id(self, job_id: str, city: str, celery_task_id: str) -> None:
        """Save Celery task ID for a job/city combination."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_status (job_id, city, celery_task_id, status, started_at)
                VALUES (?, ?, ?, 'running', CURRENT_TIMESTAMP)
                """,
                (job_id, city, celery_task_id)
            )
            conn.commit()
    
    def get_task_id(self, job_id: str, city: str) -> Optional[str]:
        """Get Celery task ID for a job/city combination."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT celery_task_id FROM task_status WHERE job_id = ? AND city = ?",
                (job_id, city)
            )
            row = cursor.fetchone()
            return row["celery_task_id"] if row else None
    
    def get_all_active_task_ids(self, job_id: str) -> List[Dict]:
        """
        Get all active task IDs for a job.
        FIX Bug 1: Filter out NULL celery_task_ids to prevent invalid Celery API calls.
        Only return tasks with valid Celery task IDs that can be used with Celery control APIs.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT city, celery_task_id, status 
                FROM task_status 
                WHERE job_id = ? AND status IN ('running', 'pending') AND celery_task_id IS NOT NULL
                """,
                (job_id,)
            )
            return [
                {
                    "city": row["city"],
                    "celery_task_id": row["celery_task_id"],
                    "status": row["status"]
                }
                for row in cursor.fetchall()
            ]
    
    def mark_task_cancelled(self, job_id: str, city: str) -> None:
        """
        Mark a task as cancelled.
        FIX Bug 1: Use INSERT OR REPLACE to ensure row exists (defensive against missing rows).
        Preserves existing celery_task_id and started_at if row exists.
        """
        with self._get_connection() as conn:
            # Get existing row to preserve celery_task_id and started_at if they exist
            cursor = conn.execute(
                "SELECT celery_task_id, started_at FROM task_status WHERE job_id = ? AND city = ?",
                (job_id, city)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Row exists - use UPDATE to preserve all existing fields
                conn.execute(
                    """
                    UPDATE task_status 
                    SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
                    WHERE job_id = ? AND city = ?
                    """,
                    (job_id, city)
                )
            else:
                # Row doesn't exist - this should not happen if save_task_id is called first
                # FIX Bug 1: Use NULL for celery_task_id to preserve data integrity
                # Synthetic IDs corrupt the semantic contract - celery_task_id should only contain real Celery task IDs
                # NULL indicates the task was cancelled before save_task_id was called (edge case)
                conn.execute(
                    """
                    INSERT INTO task_status 
                    (job_id, city, celery_task_id, status, cancelled_at)
                    VALUES (?, ?, NULL, 'cancelled', CURRENT_TIMESTAMP)
                    """,
                    (job_id, city)
                )
                logger.warning(f"[FORENSIC] mark_task_cancelled called for non-existent task: job_id={job_id}, city={city} (celery_task_id=NULL)")
            conn.commit()
    
    def mark_task_completed(self, job_id: str, city: str, result_count: int = 0, error_message: Optional[str] = None) -> None:
        """
        Mark a task as completed (success or failure).
        FIX Bug 1: Use INSERT OR REPLACE to ensure row exists (defensive against missing rows).
        Preserves existing celery_task_id and started_at if row exists.
        """
        with self._get_connection() as conn:
            status = 'failed' if error_message else 'success'
            
            # Get existing row to preserve celery_task_id and started_at if they exist
            cursor = conn.execute(
                "SELECT celery_task_id, started_at FROM task_status WHERE job_id = ? AND city = ?",
                (job_id, city)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Row exists - use UPDATE to preserve all existing fields
                conn.execute(
                    """
                    UPDATE task_status 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP, result_count = ?, error_message = ?
                    WHERE job_id = ? AND city = ?
                    """,
                    (status, result_count, error_message, job_id, city)
                )
            else:
                # Row doesn't exist - this should not happen if save_task_id is called first
                # FIX Bug 1: Use NULL for celery_task_id to preserve data integrity
                # Synthetic IDs corrupt the semantic contract - celery_task_id should only contain real Celery task IDs
                # NULL indicates the task completed before save_task_id was called (edge case)
                conn.execute(
                    """
                    INSERT INTO task_status 
                    (job_id, city, celery_task_id, status, completed_at, result_count, error_message)
                    VALUES (?, ?, NULL, ?, CURRENT_TIMESTAMP, ?, ?)
                    """,
                    (job_id, city, status, result_count, error_message)
                )
                logger.warning(f"[FORENSIC] mark_task_completed called for non-existent task: job_id={job_id}, city={city} (celery_task_id=NULL)")
            conn.commit()
    
    def get_task_status(self, job_id: str, city: str) -> Optional[Dict]:
        """Get task status for a job/city combination."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT celery_task_id, status, started_at, completed_at, cancelled_at, 
                       error_message, result_count
                FROM task_status 
                WHERE job_id = ? AND city = ?
                """,
                (job_id, city)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "celery_task_id": row["celery_task_id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "cancelled_at": row["cancelled_at"],
                "error_message": row["error_message"],
                "result_count": row["result_count"]
            }
    
    def get_incomplete_cities(self, job_id: str) -> List[str]:
        """Get list of cities that are not in terminal state (success/failed/cancelled)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT DISTINCT city 
                FROM task_status 
                WHERE job_id = ? AND status NOT IN ('success', 'failed', 'cancelled')
                """,
                (job_id,)
            )
            return [row["city"] for row in cursor.fetchall()]
    
    # PHASE 2: Event sourcing methods
    
    def save_event(self, job_id: str, event_type: str, payload: dict) -> int:
        """
        Save event to database (source of truth).
        Returns sequence number for this event.
        
        FIX Bug 2: Use transaction with retry to handle concurrent sequence number generation.
        This prevents race conditions when multiple tasks emit events simultaneously.
        """
        import json
        import sqlite3
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with self._get_connection() as conn:
                    # Use a transaction to ensure atomicity
                    # Get next sequence number and insert in same transaction
                    # SQLite will lock the table during this operation
                    cursor = conn.execute(
                        "SELECT COALESCE(MAX(sequence), 0) + 1 as next_seq FROM job_events WHERE job_id = ?",
                        (job_id,)
                    )
                    row = cursor.fetchone()
                    sequence = row["next_seq"] if row else 1
                    
                    # Insert event (will fail with UNIQUE constraint violation if sequence already exists)
                    conn.execute(
                        """
                        INSERT INTO job_events (job_id, sequence, event_type, payload)
                        VALUES (?, ?, ?, ?)
                        """,
                        (job_id, sequence, event_type, json.dumps(payload))
                    )
                    conn.commit()
                    logger.debug(f"[FORENSIC] Saved event to DB: job_id={job_id}, sequence={sequence}, type={event_type}")
                    return sequence
                    
            except sqlite3.IntegrityError as e:
                # UNIQUE constraint violation - another task inserted with same sequence
                # Retry with a new sequence number
                if attempt < max_retries - 1:
                    logger.warning(f"[FORENSIC] Sequence collision for job {job_id}, retrying (attempt {attempt + 1}/{max_retries})")
                    # Small exponential backoff to reduce collision probability
                    import time
                    time.sleep(0.01 * (attempt + 1))  # 10ms, 20ms, 30ms, 40ms
                    continue
                else:
                    # Last attempt failed - this is a critical error
                    logger.error(f"[FORENSIC] Failed to save event after {max_retries} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"Error saving event: {e}", exc_info=True)
                raise
        
        # Should never reach here, but just in case
        raise RuntimeError(f"Failed to save event after {max_retries} attempts")
    
    def get_events(self, job_id: str, since_sequence: int = 0) -> List[Dict]:
        """
        Get events for a job since a given sequence number.
        Returns events ordered by sequence.
        """
        import json
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT sequence, event_type, payload, timestamp
                FROM job_events
                WHERE job_id = ? AND sequence > ?
                ORDER BY sequence ASC
                """,
                (job_id, since_sequence)
            )
            # Parse payload and extract the actual event data
            events = []
            for row in cursor.fetchall():
                payload = json.loads(row["payload"])
                # Payload structure: {"type": event_type, "job_id": job_id, "data": actual_data}
                # Return structure matches WebSocket format: {type, job_id, data, sequence}
                events.append({
                    "sequence": row["sequence"],
                    "type": row["event_type"],
                    "job_id": payload.get("job_id", ""),  # Include job_id for consistency
                    "data": payload.get("data", {}),  # Extract actual data from payload
                    "timestamp": row["timestamp"]
                })
            return events
    
    def get_last_event_sequence(self, job_id: str) -> int:
        """Get the last event sequence number for a job."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) as max_seq FROM job_events WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            return row["max_seq"] if row else 0


# Global database instance
db = Database()

