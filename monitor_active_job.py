"""
Monitor active scraping job and detect issues.
"""
import sqlite3
import time
import sys
from datetime import datetime
from backend.database import db

def monitor_active_job(job_id=None):
    """Monitor a specific job or find active jobs."""
    print("=" * 80)
    print("ACTIVE JOB MONITOR")
    print("=" * 80)
    
    conn = sqlite3.connect('business_scraper.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Find active jobs
    if job_id:
        cursor.execute("""
            SELECT job_id, keyword, status, total_tasks, completed_tasks, created_at
            FROM jobs WHERE job_id = ?
        """, (job_id,))
    else:
        cursor.execute("""
            SELECT job_id, keyword, status, total_tasks, completed_tasks, created_at
            FROM jobs WHERE status IN ('running', 'paused')
            ORDER BY created_at DESC LIMIT 1
        """)
    
    jobs = cursor.fetchall()
    
    if not jobs:
        print("\nNo active jobs found.")
        print("\nChecking recent jobs...")
        cursor.execute("""
            SELECT job_id, keyword, status, total_tasks, completed_tasks, created_at
            FROM jobs ORDER BY created_at DESC LIMIT 3
        """)
        recent = cursor.fetchall()
        if recent:
            print("\nRecent Jobs:")
            for j in recent:
                print(f"  {j['job_id'][:12]}... | {j['keyword']} | {j['status']} | {j['completed_tasks']}/{j['total_tasks']}")
        conn.close()
        return
    
    job = jobs[0]
    job_id = job['job_id']
    keyword = job['keyword']
    status = job['status']
    total = job['total_tasks'] or 0
    completed = job['completed_tasks'] or 0
    
    print(f"\nMonitoring Job: {job_id}")
    print(f"Keyword: {keyword}")
    print(f"Status: {status}")
    print(f"Progress: {completed}/{total} tasks")
    print("\nChecking for issues...\n")
    
    # Check 1: Business count
    cursor.execute("SELECT COUNT(*) FROM businesses WHERE job_id = ?", (job_id,))
    business_count = cursor.fetchone()[0]
    print(f"[1] Businesses in Database: {business_count}")
    
    if business_count == 0 and completed > 0:
        print("   ⚠️  ISSUE: Tasks completed but no businesses found!")
        print("   → Possible causes:")
        print("      - Scraper returning empty results")
        print("      - Businesses not being saved to database")
        print("      - All businesses filtered as duplicates")
    
    # Check 2: City progress
    cursor.execute("""
        SELECT city, last_page, is_blocked, consecutive_403_count, last_updated
        FROM scrape_progress WHERE job_id = ?
        ORDER BY last_updated DESC
    """, (job_id,))
    city_progress = cursor.fetchall()
    
    print(f"\n[2] City Progress: {len(city_progress)} cities")
    blocked_cities = []
    for city_info in city_progress:
        city = city_info['city']
        page = city_info['last_page']
        blocked = city_info['is_blocked']
        errors = city_info['consecutive_403_count']
        
        if blocked:
            blocked_cities.append(city)
            print(f"   🚫 {city}: BLOCKED (Page {page}, 403s: {errors})")
        elif errors > 0:
            print(f"   ⚠️  {city}: Page {page}, 403 errors: {errors}")
        else:
            print(f"   ✓ {city}: Page {page}")
    
    if blocked_cities:
        print(f"\n   ⚠️  ISSUE: {len(blocked_cities)} cities are blocked!")
        print("   → Possible causes:")
        print("      - IP blocked by YellowPages")
        print("      - Need proxy API key")
        print("      - Too many requests")
    
    # Check 3: Task completion vs progress
    if completed >= total and total > 0:
        print(f"\n[3] Task Completion: {completed}/{total} (100%)")
        if business_count == 0:
            print("   ⚠️  ISSUE: Job completed but zero businesses!")
            print("   → This indicates scraping failed silently")
        else:
            print(f"   ✓ Job completed successfully with {business_count} businesses")
    else:
        progress_pct = (completed / total * 100) if total > 0 else 0
        print(f"\n[3] Task Completion: {completed}/{total} ({progress_pct:.1f}%)")
        if status == 'running' and progress_pct == 0 and time.time() - datetime.fromisoformat(job['created_at'].replace('Z', '+00:00')).timestamp() > 60:
            print("   ⚠️  ISSUE: Job running but no progress after 1 minute!")
            print("   → Possible causes:")
            print("      - Celery worker not processing tasks")
            print("      - Tasks failing silently")
            print("      - Redis connection issues")
    
    # Check 4: Recent business additions
    cursor.execute("""
        SELECT COUNT(*) FROM businesses 
        WHERE job_id = ? 
        AND scraped_at > datetime('now', '-5 minutes')
    """, (job_id,))
    recent_businesses = cursor.fetchone()[0]
    print(f"\n[4] Recent Activity: {recent_businesses} businesses in last 5 minutes")
    
    if status == 'running' and recent_businesses == 0 and completed < total:
        print("   ⚠️  ISSUE: No recent business activity!")
        print("   → Job appears stuck")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    issues = []
    if business_count == 0 and completed > 0:
        issues.append("Zero businesses despite completed tasks")
    if blocked_cities:
        issues.append(f"{len(blocked_cities)} cities blocked")
    if status == 'running' and recent_businesses == 0 and completed < total:
        issues.append("No recent activity (job may be stuck)")
    
    if issues:
        print("⚠️  ISSUES DETECTED:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
    else:
        print("✓ No critical issues detected")
        if business_count > 0:
            print(f"✓ {business_count} businesses found")
        if status == 'running':
            print("✓ Job is actively running")
    
    conn.close()
    
    return issues

if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    monitor_active_job(job_id)
