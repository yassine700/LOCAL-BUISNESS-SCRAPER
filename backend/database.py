"""
Database models and connection handling.
"""
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager
import os

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
                    UNIQUE(business_name, website, city, source)
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
            
            # Resume capability: Track last page scraped per city
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scrape_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    city TEXT NOT NULL,
                    last_page INTEGER DEFAULT 0,
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
        """
        with self._get_connection() as conn:
            # One task per city (YellowPages only)
            total_tasks = len(cities)
            conn.execute(
                """
                INSERT INTO jobs (job_id, keyword, cities, sources, total_tasks)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, keyword, ",".join(cities), ",".join(sources), total_tasks)
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
        """Increment completed tasks counter."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET completed_tasks = completed_tasks + 1 WHERE job_id = ?",
                (job_id,)
            )
            conn.commit()
            
            # Check if job is complete
            cursor = conn.execute(
                "SELECT total_tasks, completed_tasks FROM jobs WHERE job_id = ?",
                (job_id,)
            )
            row = cursor.fetchone()
            if row and row["total_tasks"] == row["completed_tasks"]:
                self.update_job_status(job_id, "completed")
    
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
            
            return {
                "job_id": row["job_id"],
                "keyword": row["keyword"],
                "cities": row["cities"].split(","),
                "sources": row["sources"].split(","),
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
        """
        with self._get_connection() as conn:
            try:
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
                # Duplicate entry, ignore
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


# Global database instance
db = Database()

