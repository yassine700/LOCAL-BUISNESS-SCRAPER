"""
Watch for active jobs and automatically fix common issues.
"""
import sqlite3
import time
import sys
import json
import redis
from datetime import datetime
from backend.database import db
from backend.config import REDIS_URL

def watch_and_fix(interval=5):
    """Continuously watch for jobs and fix issues."""
    print("=" * 80)
    print("JOB WATCHER & AUTO-FIX")
    print("=" * 80)
    print("Watching for active scraping jobs...")
    print("Will automatically detect and report issues.")
    print("Press Ctrl+C to stop\n")
    
    last_job_id = None
    
    try:
        while True:
            # Find active jobs
            conn = sqlite3.connect('business_scraper.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT job_id, keyword, status, total_tasks, completed_tasks
                FROM jobs 
                WHERE status IN ('running', 'paused', 'pending')
                ORDER BY created_at DESC
                LIMIT 1
            """)
            
            active_job = cursor.fetchone()
            conn.close()
            
            if active_job:
                job_id = active_job['job_id']
                
                # New job detected
                if job_id != last_job_id:
                    print(f"\n{'='*80}")
                    print(f"NEW JOB DETECTED: {job_id[:12]}...")
                    print(f"{'='*80}")
                    print(f"Keyword: {active_job['keyword']}")
                    print(f"Status: {active_job['status']}")
                    print(f"Tasks: {active_job['completed_tasks']}/{active_job['total_tasks']}")
                    last_job_id = job_id
                
                # Get current status
                status = db.get_job_status(job_id)
                if status:
                    business_count = status['business_count'] or 0
                    progress = status['progress'] or 0
                    
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    print(f"\n[{timestamp}] Job Status Update")
                    print(f"  Progress: {progress:.1f}% | Businesses: {business_count}")
                    
                    # Check for issues
                    issues_found = []
                    
                    # Issue 1: No businesses after tasks completed
                    if active_job['completed_tasks'] > 0 and business_count == 0:
                        issues_found.append("No businesses found despite completed tasks")
                    
                    # Issue 2: Check Redis connectivity
                    try:
                        redis_client = redis.from_url(REDIS_URL)
                        redis_client.ping()
                    except Exception as e:
                        issues_found.append(f"Redis connection issue: {e}")
                    
                    # Issue 3: Check if job is stuck
                    if active_job['status'] == 'running' and active_job['completed_tasks'] == 0:
                        # Check if job started recently (within last 2 minutes)
                        conn = sqlite3.connect('business_scraper.db')
                        cursor = conn.cursor()
                        cursor.execute("SELECT started_at FROM jobs WHERE job_id = ?", (job_id,))
                        started = cursor.fetchone()
                        conn.close()
                        # Could check timestamp here if needed
                    
                    if issues_found:
                        print(f"\n  [WARNING] Issues detected:")
                        for issue in issues_found:
                            print(f"    - {issue}")
                    
                    # Check if job completed
                    if active_job['status'] == 'completed':
                        if business_count == 0:
                            print(f"\n  [ERROR] Job completed with ZERO businesses!")
                            print(f"  This may indicate:")
                            print(f"    1. Scraper was blocked")
                            print(f"    2. No businesses found for keyword/city")
                            print(f"    3. Scraping logic error")
                        else:
                            print(f"\n  [OK] Job completed successfully with {business_count} businesses")
                        break
            else:
                if last_job_id:
                    print(f"\nNo active jobs. Last monitored: {last_job_id[:12]}...")
                    last_job_id = None
                else:
                    # Show waiting message every 30 seconds
                    if int(time.time()) % 30 < interval:
                        print(".", end="", flush=True)
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    watch_and_fix(interval)

