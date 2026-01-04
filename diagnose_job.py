"""
Comprehensive job diagnostic tool - checks all potential failure points.
"""
import sqlite3
import json
import sys
import redis
from datetime import datetime
from backend.database import db
from backend.config import REDIS_URL

def diagnose_job(job_id=None):
    """Run comprehensive diagnostics on a job."""
    print("=" * 80)
    print("COMPREHENSIVE JOB DIAGNOSTIC")
    print("=" * 80)
    
    # Find job if not provided
    if not job_id:
        conn = sqlite3.connect('business_scraper.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT job_id, keyword, status 
            FROM jobs 
            ORDER BY created_at DESC 
            LIMIT 1
        """)
        job = cursor.fetchone()
        conn.close()
        
        if not job:
            print("\n[ERROR] No jobs found in database.")
            return
        
        job_id = job['job_id']
        print(f"\nAnalyzing job: {job_id}")
        print(f"Keyword: {job['keyword']}")
        print(f"Status: {job['status']}")
    else:
        print(f"\nAnalyzing job: {job_id}")
    
    print("\n" + "=" * 80)
    print("DIAGNOSTIC CHECKS")
    print("=" * 80)
    
    issues = []
    warnings = []
    
    # 1. Check job exists in database
    print("\n[1] Database Job Record")
    print("-" * 80)
    conn = sqlite3.connect('business_scraper.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT job_id, keyword, status, total_tasks, completed_tasks, created_at, started_at
        FROM jobs WHERE job_id = ?
    """, (job_id,))
    
    job_record = cursor.fetchone()
    if not job_record:
        print("[ERROR] CRITICAL: Job not found in database")
        issues.append("Job record missing from database")
        conn.close()
        return
    else:
        print(f"[OK] Job found in database")
        print(f"   Status: {job_record['status']}")
        print(f"   Tasks: {job_record['completed_tasks']}/{job_record['total_tasks']}")
        print(f"   Created: {job_record['created_at']}")
        if job_record['started_at']:
            print(f"   Started: {job_record['started_at']}")
    
    # 2. Check businesses in database
    print("\n[2] Businesses in Database")
    print("-" * 80)
    cursor.execute("""
        SELECT COUNT(*) as count, 
               COUNT(DISTINCT city) as cities,
               COUNT(DISTINCT website) as unique_websites
        FROM businesses WHERE job_id = ?
    """, (job_id,))
    
    biz_stats = cursor.fetchone()
    business_count = biz_stats['count'] if biz_stats else 0
    
    if business_count == 0:
        print("[WARNING] Zero businesses in database")
        warnings.append("No businesses saved to database")
    else:
        print(f"[OK] Found {business_count} businesses")
        print(f"   Cities: {biz_stats['cities']}")
        print(f"   Unique websites: {biz_stats['unique_websites']}")
    
    # 3. Check scrape progress
    print("\n[3] Scrape Progress")
    print("-" * 80)
    cursor.execute("""
        SELECT city, last_page, is_blocked, consecutive_403_count, last_updated
        FROM scrape_progress 
        WHERE job_id = ?
        ORDER BY last_page DESC
    """, (job_id,))
    
    progress_records = cursor.fetchall()
    conn.close()
    
    if not progress_records:
        print("[WARNING] No scrape progress records")
        warnings.append("No progress tracking found")
    else:
        print(f"[OK] Found progress for {len(progress_records)} cities")
        blocked_count = sum(1 for r in progress_records if r['is_blocked'])
        high_403_count = sum(1 for r in progress_records if r['consecutive_403_count'] >= 3)
        
        if blocked_count > 0:
            print(f"[WARNING] {blocked_count} cities blocked")
            warnings.append(f"{blocked_count} cities are blocked")
        
        if high_403_count > 0:
            print(f"[WARNING] {high_403_count} cities with high 403 errors")
            warnings.append(f"{high_403_count} cities have persistent 403 errors")
        
        print("\n   Top cities by progress:")
        for record in progress_records[:5]:
            status = "[BLOCKED]" if record['is_blocked'] else ("[WARN]" if record['consecutive_403_count'] >= 3 else "[OK]")
            print(f"   {status} {record['city']}: Page {record['last_page']} | 403s: {record['consecutive_403_count']}")
    
    # 4. Check Redis connectivity
    print("\n[4] Redis Connectivity")
    print("-" * 80)
    try:
        redis_client = redis.from_url(REDIS_URL)
        redis_client.ping()
        print("[OK] Redis connection successful")
    except Exception as e:
        print(f"[ERROR] CRITICAL: Redis connection failed: {e}")
        issues.append(f"Redis connection failed: {e}")
        return
    
    # 5. Check for active WebSocket subscriptions (can't directly check, but verify channels exist)
    print("\n[5] Event Channels")
    print("-" * 80)
    events_channel = f"job:{job_id}:events"
    metrics_channel = f"job:{job_id}:metrics"
    print(f"   Events channel: {events_channel}")
    print(f"   Metrics channel: {metrics_channel}")
    print("   (Channels are created dynamically when events are published)")
    
    # 6. Check task completion status
    print("\n[6] Task Completion")
    print("-" * 80)
    total = job_record['total_tasks'] or 0
    completed = job_record['completed_tasks'] or 0
    progress_pct = (completed / total * 100) if total > 0 else 0
    
    print(f"   Progress: {completed}/{total} tasks ({progress_pct:.1f}%)")
    
    if total == 0:
        print("[WARNING] No tasks spawned")
        warnings.append("Job has zero tasks")
    elif completed == 0 and job_record['status'] == 'running':
        print("[WARNING] Job running but no tasks completed")
        warnings.append("No tasks have completed yet")
    elif completed == total and business_count == 0:
        print("[ERROR] CRITICAL: All tasks completed but zero businesses")
        issues.append("All tasks completed with zero results - possible scraping failure")
    elif completed == total and business_count > 0:
        print("[OK] All tasks completed with results")
    
    # 7. Check for common issues
    print("\n[7] Common Issues Check")
    print("-" * 80)
    
    # Issue: Job completed but no businesses
    if job_record['status'] == 'completed' and business_count == 0:
        print("[ERROR] CRITICAL: Job marked completed with ZERO businesses")
        issues.append("Job completed with zero businesses")
    
    # Issue: Running but stuck
    if job_record['status'] == 'running' and completed > 0:
        # Check if progress is recent (within last 5 minutes would require timestamp comparison)
        print("   Job is running...")
    
    # Issue: No progress records but tasks completed
    if completed > 0 and not progress_records:
        print("[WARNING] Tasks completed but no progress records")
        warnings.append("Progress tracking may be broken")
    
    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 80)
    
    if issues:
        print("\n[ERROR] CRITICAL ISSUES:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
    
    if warnings:
        print("\n[WARNING] WARNINGS:")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")
    
    if not issues and not warnings:
        print("\n[OK] No critical issues detected")
    
    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    if business_count == 0 and job_record['status'] == 'running':
        print("\n1. Check if scraper is actually finding businesses:")
        print("   - Open browser console (F12) and watch for WebSocket messages")
        print("   - Check backend logs for 'Published business event' messages")
        print("   - Verify YellowPages is not blocking requests")
    
    if blocked_count > 0:
        print("\n2. Blocked cities detected:")
        print("   - Consider using proxies or rotating IPs")
        print("   - Check circuit breaker settings")
    
    if completed == total and business_count == 0:
        print("\n3. All tasks completed with zero results:")
        print("   - Check if keyword/city combination returns results on YellowPages")
        print("   - Verify scraper is not being blocked")
        print("   - Check backend logs for errors during scraping")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    diagnose_job(job_id)

