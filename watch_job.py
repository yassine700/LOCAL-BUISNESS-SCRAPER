"""
Watch a specific job or all active jobs with detailed monitoring.
"""
import sqlite3
import time
import sys
from datetime import datetime
from backend.database import db

def watch_job(job_id=None, interval=3):
    """Watch a specific job or all active jobs."""
    print("=" * 80)
    if job_id:
        print(f"WATCHING JOB: {job_id}")
    else:
        print("WATCHING ALL ACTIVE JOBS")
    print("=" * 80)
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            conn = sqlite3.connect('business_scraper.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if job_id:
                cursor.execute("""
                    SELECT job_id, keyword, status, total_tasks, completed_tasks, 
                           created_at, started_at
                    FROM jobs 
                    WHERE job_id = ?
                """, (job_id,))
            else:
                cursor.execute("""
                    SELECT job_id, keyword, status, total_tasks, completed_tasks, 
                           created_at, started_at
                    FROM jobs 
                    WHERE status IN ('running', 'paused', 'pending')
                    ORDER BY created_at DESC
                """)
            
            jobs = cursor.fetchall()
            
            if not jobs:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No active jobs found. Waiting...")
                time.sleep(interval)
                conn.close()
                continue
            
            # Clear screen (optional - comment out if issues)
            # os.system('cls' if os.name == 'nt' else 'clear')
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] STATUS UPDATE")
            print("=" * 80)
            
            for job in jobs:
                jid = job['job_id']
                keyword = job['keyword']
                status = job['status']
                total = job['total_tasks'] or 0
                completed = job['completed_tasks'] or 0
                progress = (completed / total * 100) if total > 0 else 0
                
                # Get business count
                cursor.execute("SELECT COUNT(*) FROM businesses WHERE job_id = ?", (jid,))
                business_count = cursor.fetchone()[0]
                
                # Get city progress
                cursor.execute("""
                    SELECT city, last_page, is_blocked, consecutive_403_count
                    FROM scrape_progress 
                    WHERE job_id = ? 
                    ORDER BY last_updated DESC
                """, (jid,))
                city_progress = cursor.fetchall()
                
                # Status display
                status_display = {
                    'running': '[RUNNING]',
                    'paused': '[PAUSED]',
                    'pending': '[PENDING]',
                    'completed': '[COMPLETED]',
                    'killed': '[KILLED]',
                    'error': '[ERROR]'
                }.get(status, '[UNKNOWN]')
                
                print(f"\nJob ID: {jid}")
                print(f"  Keyword: {keyword}")
                print(f"  Status: {status_display} {status.upper()}")
                print(f"  Progress: {completed}/{total} tasks ({progress:.1f}%)")
                print(f"  Businesses Found: {business_count}")
                
                # Progress bar
                bar_width = 50
                filled = int(bar_width * progress / 100)
                bar = '=' * filled + '-' * (bar_width - filled)
                print(f"  [{bar}] {progress:.1f}%")
                
                # City details
                if city_progress:
                    print(f"  City Progress:")
                    for city_info in city_progress:
                        city = city_info['city']
                        page = city_info['last_page']
                        blocked = city_info['is_blocked']
                        errors = city_info['consecutive_403_count']
                        block_status = "[BLOCKED]" if blocked else "[OK]"
                        print(f"    {block_status} {city}: Page {page} | 403 Errors: {errors}")
                
                # Check if job completed
                if status in ('completed', 'killed', 'error'):
                    print(f"  >>> Job finished with status: {status}")
            
            print("\n" + "=" * 80)
            conn.close()
            
            # Check if all jobs are terminal
            if all(j['status'] in ('completed', 'killed', 'error') for j in jobs):
                print("\nAll jobs are in terminal state. Monitoring stopped.")
                break
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    watch_job(job_id, interval)

