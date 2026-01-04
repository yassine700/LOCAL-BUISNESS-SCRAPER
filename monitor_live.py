"""
Live monitoring tool for scraping jobs.
Monitors active jobs and provides real-time updates.
"""
import sqlite3
import time
import os
from datetime import datetime
from backend.database import db

def format_time(timestamp):
    """Format timestamp for display."""
    if not timestamp:
        return "N/A"
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp

def get_job_status(job_id):
    """Get detailed job status."""
    status = db.get_job_status(job_id)
    if not status:
        return None
    
    # Get city progress
    conn = sqlite3.connect('business_scraper.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT city, last_page, is_blocked, consecutive_403_count, last_updated
        FROM scrape_progress 
        WHERE job_id = ? 
        ORDER BY last_updated DESC
    """, (job_id,))
    city_progress = cursor.fetchall()
    
    conn.close()
    
    return {
        'status': status,
        'city_progress': city_progress
    }

def monitor_live(interval=5):
    """Monitor jobs in real-time."""
    print("=" * 80)
    print("LIVE JOB MONITOR")
    print("=" * 80)
    print("Monitoring for active scraping jobs...")
    print("Press Ctrl+C to stop\n")
    
    last_job_count = 0
    seen_jobs = set()
    
    try:
        while True:
            # Check for jobs
            conn = sqlite3.connect('business_scraper.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT job_id, keyword, status, total_tasks, completed_tasks, 
                       created_at, started_at
                FROM jobs 
                WHERE status IN ('running', 'paused', 'pending')
                ORDER BY created_at DESC
            """)
            
            active_jobs = cursor.fetchall()
            conn.close()
            
            # Check for new jobs
            current_job_ids = {job['job_id'] for job in active_jobs}
            new_jobs = current_job_ids - seen_jobs
            
            if new_jobs:
                print(f"\n🆕 NEW JOB(S) DETECTED: {len(new_jobs)}")
                for job_id in new_jobs:
                    job = next(j for j in active_jobs if j['job_id'] == job_id)
                    print(f"  Job: {job_id[:12]}... | Keyword: {job['keyword']} | Status: {job['status']}")
                seen_jobs.update(new_jobs)
            
            # Monitor active jobs
            if active_jobs:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Active Jobs: {len(active_jobs)}")
                print("-" * 80)
                
                for job in active_jobs:
                    job_id = job['job_id']
                    keyword = job['keyword']
                    status = job['status']
                    total = job['total_tasks'] or 0
                    completed = job['completed_tasks'] or 0
                    progress = (completed / total * 100) if total > 0 else 0
                    
                    # Get business count
                    conn = sqlite3.connect('business_scraper.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM businesses WHERE job_id = ?", (job_id,))
                    business_count = cursor.fetchone()[0]
                    conn.close()
                    
                    # Get detailed status
                    details = get_job_status(job_id)
                    
                    # Status icon
                    icons = {
                        'running': '⚡',
                        'paused': '⏸',
                        'pending': '⏳'
                    }
                    icon = icons.get(status, '❓')
                    
                    print(f"{icon} Job: {job_id[:12]}...")
                    print(f"   Keyword: {keyword}")
                    print(f"   Status: {status.upper()}")
                    print(f"   Progress: {completed}/{total} tasks ({progress:.1f}%)")
                    print(f"   Businesses: {business_count}")
                    
                    # Show city progress if available
                    if details and details['city_progress']:
                        print(f"   Cities:")
                        for city_info in details['city_progress'][:3]:  # Show top 3
                            city = city_info['city']
                            page = city_info['last_page']
                            blocked = city_info['is_blocked']
                            errors = city_info['consecutive_403_count']
                            status_icon = "🚫" if blocked else "📄"
                            print(f"     {status_icon} {city}: Page {page} | 403s: {errors}")
                    
                    print()
                
                print("-" * 80)
            else:
                if last_job_count > 0:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⏸ No active jobs")
                last_job_count = 0
            
            # Wait before next check
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    monitor_live(interval)

