"""
Monitor active scraping jobs and their status.
"""
import sqlite3
import json
from datetime import datetime
from backend.database import db

def monitor_jobs():
    """Monitor all jobs and their current status."""
    print("=" * 80)
    print("SCRAPING JOB MONITOR")
    print("=" * 80)
    print()
    
    # Get all jobs
    conn = sqlite3.connect('business_scraper.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all jobs ordered by creation time
    cursor.execute("""
        SELECT job_id, keyword, cities, sources, status, 
               total_tasks, completed_tasks, created_at, completed_at
        FROM jobs 
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    
    jobs = cursor.fetchall()
    
    if not jobs:
        print("No jobs found in database.")
        return
    
    print(f"Found {len(jobs)} job(s):\n")
    
    for job in jobs:
        job_id = job['job_id']
        keyword = job['keyword']
        status = job['status']
        total_tasks = job['total_tasks'] or 0
        completed_tasks = job['completed_tasks'] or 0
        progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # Get business count for this job
        cursor.execute("SELECT COUNT(*) FROM businesses WHERE job_id = ?", (job_id,))
        business_count = cursor.fetchone()[0]
        
        # Get scrape progress details
        cursor.execute("""
            SELECT city, last_page, is_blocked, consecutive_403_count 
            FROM scrape_progress 
            WHERE job_id = ? 
            ORDER BY last_updated DESC
        """, (job_id,))
        progress_details = cursor.fetchall()
        
        print(f"Job ID: {job_id[:8]}...")
        print(f"  Keyword: {keyword}")
        print(f"  Status: {status.upper()}")
        print(f"  Progress: {completed_tasks}/{total_tasks} tasks ({progress:.1f}%)")
        print(f"  Businesses Found: {business_count}")
        print(f"  Created: {job['created_at']}")
        if job['completed_at']:
            print(f"  Completed: {job['completed_at']}")
        
        # Show city progress
        if progress_details:
            print(f"  City Progress:")
            for city_prog in progress_details:
                city = city_prog['city']
                page = city_prog['last_page']
                blocked = city_prog['is_blocked']
                errors = city_prog['consecutive_403_count']
                status_icon = "🚫" if blocked else "✅"
                print(f"    {status_icon} {city}: Page {page} | 403s: {errors} | Blocked: {blocked}")
        
        # Status-specific info
        if status == 'running':
            print(f"  ⚡ ACTIVE - Currently scraping")
        elif status == 'paused':
            print(f"  ⏸ PAUSED - Waiting for resume")
        elif status == 'completed':
            print(f"  ✅ COMPLETED")
        elif status == 'killed':
            print(f"  ⏹ KILLED")
        elif status == 'error':
            print(f"  ❌ ERROR")
        
        print()
    
    # Check for active jobs
    active_jobs = [j for j in jobs if j['status'] in ('running', 'paused')]
    if active_jobs:
        print(f"\n⚠️  {len(active_jobs)} ACTIVE JOB(S) DETECTED")
        print("=" * 80)
    else:
        print("\n✅ No active jobs - All jobs are in terminal state")
        print("=" * 80)
    
    conn.close()

if __name__ == "__main__":
    try:
        monitor_jobs()
    except Exception as e:
        print(f"Error monitoring jobs: {e}")
        import traceback
        traceback.print_exc()

