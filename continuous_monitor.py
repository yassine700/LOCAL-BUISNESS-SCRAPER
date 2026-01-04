"""
Continuous monitoring for scraping jobs - detects new jobs and monitors them.
"""
import sqlite3
import time
import sys
from datetime import datetime
from backend.database import db

def continuous_monitor(interval=5):
    """Continuously monitor for jobs and track their progress."""
    print("=" * 80)
    print("CONTINUOUS JOB MONITOR")
    print("=" * 80)
    print("Watching for new and active scraping jobs...")
    print("Press Ctrl+C to stop\n")
    
    monitored_jobs = set()
    last_check = {}
    
    try:
        while True:
            # Get all jobs (active and recent)
            conn = sqlite3.connect('business_scraper.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT job_id, keyword, status, total_tasks, completed_tasks, created_at
                FROM jobs 
                WHERE status IN ('running', 'paused', 'pending', 'completed', 'killed', 'error')
                ORDER BY created_at DESC
                LIMIT 10
            """)
            
            jobs = cursor.fetchall()
            conn.close()
            
            # Check for new jobs
            current_job_ids = {job['job_id'] for job in jobs}
            new_jobs = current_job_ids - monitored_jobs
            
            if new_jobs:
                print(f"\n🆕 NEW JOB(S) DETECTED: {len(new_jobs)}")
                for job_id in new_jobs:
                    job = next(j for j in jobs if j['job_id'] == job_id)
                    print(f"  Job: {job_id[:12]}... | Keyword: {job['keyword']} | Status: {job['status']}")
                monitored_jobs.update(new_jobs)
            
            # Monitor active jobs
            active_jobs = [j for j in jobs if j['status'] in ('running', 'paused', 'pending')]
            
            if active_jobs:
                timestamp = datetime.now().strftime('%H:%M:%S')
                print(f"\n[{timestamp}] Active Jobs: {len(active_jobs)}")
                print("-" * 80)
                
                for job in active_jobs:
                    job_id = job['job_id']
                    keyword = job['keyword']
                    status = job['status']
                    total = job['total_tasks'] or 0
                    completed = job['completed_tasks'] or 0
                    progress = (completed / total * 100) if total > 0 else 0
                    
                    # Get detailed status
                    job_status = db.get_job_status(job_id)
                    business_count = job_status['business_count'] if job_status else 0
                    
                    # Get city progress
                    conn = sqlite3.connect('business_scraper.db')
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT city, last_page, is_blocked, consecutive_403_count
                        FROM scrape_progress 
                        WHERE job_id = ? 
                        ORDER BY last_updated DESC
                    """, (job_id,))
                    city_progress = cursor.fetchall()
                    conn.close()
                    
                    # Check for issues
                    issues = []
                    
                    # Check if stuck
                    job_key = job_id
                    if job_key in last_check:
                        last_biz = last_check[job_key].get('business_count', 0)
                        last_tasks = last_check[job_key].get('completed_tasks', 0)
                        if business_count == last_biz and completed == last_tasks:
                            issues.append("⚠️  No progress detected")
                    
                    last_check[job_key] = {
                        'business_count': business_count,
                        'completed_tasks': completed
                    }
                    
                    # Check for blocked cities
                    blocked = [c for c in city_progress if c['is_blocked']]
                    if blocked:
                        issues.append(f"🚫 {len(blocked)} cities blocked")
                    
                    # Check for high 403s
                    high_403 = [c for c in city_progress if c['consecutive_403_count'] >= 3]
                    if high_403:
                        issues.append(f"⚠️  {len(high_403)} cities with 403 errors")
                    
                    # Status display
                    status_icon = {
                        'running': '[RUNNING]',
                        'paused': '[PAUSED]',
                        'pending': '[PENDING]'
                    }.get(status, '[?]')
                    
                    print(f"{status_icon} Job: {job_id[:12]}...")
                    print(f"   Keyword: {keyword}")
                    print(f"   Progress: {completed}/{total} tasks ({progress:.1f}%)")
                    print(f"   Businesses: {business_count}")
                    
                    if city_progress:
                        print(f"   Cities: {len(city_progress)} active")
                        for city_info in city_progress[:2]:
                            city = city_info['city']
                            page = city_info['last_page']
                            blocked = city_info['is_blocked']
                            errors = city_info['consecutive_403_count']
                            icon = "🚫" if blocked else ("⚠️" if errors >= 3 else "📄")
                            print(f"     {icon} {city}: Page {page} | 403s: {errors}")
                    
                    if issues:
                        print(f"   Issues: {' | '.join(issues)}")
                    
                    print()
                
                print("-" * 80)
            else:
                # Check completed jobs for issues
                completed_jobs = [j for j in jobs if j['status'] == 'completed']
                for job in completed_jobs[:3]:  # Check last 3 completed
                    job_id = job['job_id']
                    job_status = db.get_job_status(job_id)
                    if job_status:
                        business_count = job_status['business_count'] or 0
                        if business_count == 0:
                            print(f"\n⚠️  WARNING: Completed job {job_id[:12]}... has ZERO businesses")
                            print(f"   Keyword: {job['keyword']}")
                            print(f"   This may indicate scraping failure or blocking")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    continuous_monitor(interval)

