"""
Quick system status check for scraping infrastructure.
"""
import sqlite3
import os
from backend.database import db

def check_system():
    """Check system status."""
    print("=" * 80)
    print("SYSTEM STATUS CHECK")
    print("=" * 80)
    print()
    
    # Check database
    db_path = 'business_scraper.db'
    if os.path.exists(db_path):
        print("[OK] Database: Found")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"   Tables: {', '.join(tables)}")
        
        # Count jobs
        cursor.execute("SELECT COUNT(*) FROM jobs")
        job_count = cursor.fetchone()[0]
        print(f"   Total Jobs: {job_count}")
        
        # Count businesses
        cursor.execute("SELECT COUNT(*) FROM businesses")
        business_count = cursor.fetchone()[0]
        print(f"   Total Businesses: {business_count}")
        
        # Active jobs
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('running', 'paused')")
        active_count = cursor.fetchone()[0]
        print(f"   Active Jobs: {active_count}")
        
        conn.close()
    else:
        print("[ERROR] Database: Not found")
    
    print()
    
    # Check Redis connection (if available)
    try:
        import redis
        from backend.config import REDIS_URL
        redis_client = redis.from_url(REDIS_URL)
        redis_client.ping()
        print("[OK] Redis: Connected")
    except Exception as e:
        print(f"[WARN] Redis: {e}")
    
    print()
    
    # Check recent jobs
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT job_id, keyword, status, total_tasks, completed_tasks, created_at
        FROM jobs 
        ORDER BY created_at DESC 
        LIMIT 5
    """)
    
    recent = cursor.fetchall()
    conn.close()
    
    if recent:
        print("Recent Jobs:")
        print("-" * 80)
        for job in recent:
            job_id = job['job_id']
            keyword = job['keyword']
            status = job['status']
            total = job['total_tasks'] or 0
            completed = job['completed_tasks'] or 0
            progress = (completed / total * 100) if total > 0 else 0
            
            status_icon = {
                'running': '[RUNNING]',
                'paused': '[PAUSED]',
                'completed': '[DONE]',
                'killed': '[KILLED]',
                'error': '[ERROR]'
            }.get(status, '[?]')
            
            print(f"{status_icon} {job_id[:12]}... | {keyword} | {status} | {progress:.1f}%")
        print("-" * 80)
    else:
        print("No jobs found in database.")
    
    print()
    print("=" * 80)
    print("TIP: To start monitoring: python monitor_live.py")
    print("=" * 80)

if __name__ == "__main__":
    check_system()

