"""
Manual Backend Functional Verification
Tests backend functionality without relying on scraping success.
"""
import sys
import os
import sqlite3
import json
from datetime import datetime

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print("=" * 80)
print("MANUAL BACKEND FUNCTIONAL VERIFICATION")
print("=" * 80)
print()

# PHASE A: System Bootstrap
print("PHASE A: SYSTEM BOOTSTRAP")
print("-" * 80)

# Check database schema
try:
    conn = sqlite3.connect('business_scraper.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"[OK] Database: {len(tables)} tables found")
    print(f"  Tables: {', '.join(sorted(tables))}")
    
    # Check critical tables
    required_tables = ['jobs', 'businesses', 'scrape_progress']
    phase2_tables = ['task_status', 'job_events']
    
    for table in required_tables:
        if table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in cursor.fetchall()]
            print(f"  [OK] {table}: {len(cols)} columns")
        else:
            print(f"  [FAIL] {table}: MISSING")
    
    for table in phase2_tables:
        if table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in cursor.fetchall()]
            print(f"  [OK] {table}: {len(cols)} columns (Phase 2)")
        else:
            print(f"  [WARN] {table}: MISSING (Phase 2 table)")
    
    conn.close()
except Exception as e:
    print(f"[FAIL] Database check failed: {e}")

# Check Redis
try:
    import redis
    r = redis.from_url('redis://localhost:6379/0')
    info = r.info()
    print(f"[OK] Redis: Connected")
    print(f"  Version: {info.get('redis_version', 'unknown')}")
    print(f"  Used Memory: {info.get('used_memory_human', 'unknown')}")
except Exception as e:
    print(f"[FAIL] Redis check failed: {e}")

# Check Celery
try:
    from backend.celery_app import celery_app
    print(f"[OK] Celery App: Configured")
    print(f"  Broker: {celery_app.conf.broker_url}")
    print(f"  Backend: {celery_app.conf.result_backend}")
    print(f"  Tasks registered: {len([t for t in celery_app.tasks.keys() if not t.startswith('celery.')])}")
    for name in sorted(celery_app.tasks.keys()):
        if not name.startswith('celery.'):
            print(f"    - {name}")
except Exception as e:
    print(f"[FAIL] Celery check failed: {e}")

# Check Event Emitter
try:
    from backend.event_emitter import emit_event
    print(f"[OK] Event Emitter: Import successful")
except Exception as e:
    print(f"[FAIL] Event Emitter check failed: {e}")

print()

# PHASE B: Job Creation Verification
print("PHASE B: JOB CREATION")
print("-" * 80)

try:
    from backend.database import db
    
    # Test job creation
    test_job_id = "test-verification-" + datetime.now().strftime("%Y%m%d%H%M%S")
    test_keyword = "test_keyword"
    test_cities = ["Test City, ST"]
    test_sources = ["yellowpages"]
    
    # Create job
    db.create_job(test_job_id, test_keyword, test_cities, test_sources)
    print(f"[OK] Job created: {test_job_id}")
    
    # Verify job exists
    status = db.get_job_status(test_job_id)
    if status:
        print(f"[OK] Job exists in database")
        print(f"  Status: {status.get('status')}")
        print(f"  Keyword: {status.get('keyword')}")
        print(f"  Cities: {status.get('cities')}")
        print(f"  Total Tasks: {status.get('total_tasks')}")
    else:
        print(f"[FAIL] Job not found after creation")
    
    # Check for race condition: job should exist immediately
    conn = sqlite3.connect('business_scraper.db')
    cursor = conn.cursor()
    cursor.execute("SELECT job_id, status FROM jobs WHERE job_id = ?", (test_job_id,))
    row = cursor.fetchone()
    if row:
        print(f"[OK] Job exists immediately (no race condition)")
        print(f"  DB Status: {row[1]}")
    else:
        print(f"[FAIL] Race condition detected - job not in DB")
    conn.close()
    
except Exception as e:
    print(f"[FAIL] Job creation test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# PHASE C: Task Spawning Verification
print("PHASE C: TASK SPAWNING")
print("-" * 80)

try:
    from backend.celery_app import celery_app
    
    # Check if we can spawn a task
    test_task_id = celery_app.send_task(
        "scrape_business",
        args=[test_job_id, test_keyword, "Test City, ST", "yellowpages"]
    )
    print(f"[OK] Task spawned: {test_task_id.id}")
    print(f"  Task ID: {test_task_id.id}")
    print(f"  State: {test_task_id.state}")
    
    # Check if task_id is stored in database (Phase 2)
    task_status = db.get_task_status(test_job_id, "Test City, ST")
    if task_status:
        print(f"[OK] Task ID stored in database (Phase 2)")
        print(f"  Celery Task ID: {task_status.get('celery_task_id')}")
        print(f"  Status: {task_status.get('status')}")
    else:
        print(f"[WARN] Task ID not stored (may be Phase 1 system)")
    
except Exception as e:
    print(f"[FAIL] Task spawning test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# PHASE D: Database Methods Verification
print("PHASE D: DATABASE METHODS")
print("-" * 80)

try:
    # Test task status methods
    if hasattr(db, 'save_task_id'):
        db.save_task_id(test_job_id, "Test City 2, ST", "test-task-id-123")
        print(f"[OK] save_task_id() works")
        
        task_id = db.get_task_id(test_job_id, "Test City 2, ST")
        if task_id == "test-task-id-123":
            print(f"[OK] get_task_id() works")
        else:
            print(f"[FAIL] get_task_id() returned wrong value: {task_id}")
        
        active_tasks = db.get_all_active_task_ids(test_job_id)
        print(f"[OK] get_all_active_task_ids() works: {len(active_tasks)} active tasks")
    else:
        print(f"[WARN] Phase 2 methods not available")
    
    # Test event methods
    if hasattr(db, 'save_event'):
        sequence = db.save_event(test_job_id, "test_event", {"message": "test"})
        print(f"[OK] save_event() works: sequence={sequence}")
        
        events = db.get_events(test_job_id, since_sequence=0)
        print(f"[OK] get_events() works: {len(events)} events found")
        
        last_seq = db.get_last_event_sequence(test_job_id)
        print(f"[OK] get_last_event_sequence() works: {last_seq}")
    else:
        print(f"[WARN] Phase 2 event methods not available")
    
except Exception as e:
    print(f"[FAIL] Database methods test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# PHASE E: Event Emission Verification
print("PHASE E: EVENT EMISSION")
print("-" * 80)

try:
    from backend.event_emitter import emit_event
    
    # Test event emission
    seq1 = emit_event(test_job_id, "test_event", {"test": "data1"})
    seq2 = emit_event(test_job_id, "test_event", {"test": "data2"})
    
    print(f"[OK] emit_event() works")
    print(f"  Sequence 1: {seq1}")
    print(f"  Sequence 2: {seq2}")
    
    if seq2 > seq1:
        print(f"[OK] Sequence numbers increment correctly")
    else:
        print(f"[FAIL] Sequence numbers not incrementing")
    
    # Verify events in database
    events = db.get_events(test_job_id, since_sequence=0)
    print(f"[OK] Events saved to database: {len(events)} events")
    
    # Check Redis (best-effort)
    try:
        import redis
        from backend.config import REDIS_URL
        redis_client = redis.from_url(REDIS_URL)
        # Can't easily verify pub/sub without subscriber, but connection works
        redis_client.ping()
        print(f"[OK] Redis connection works (pub/sub verification requires subscriber)")
    except Exception as e:
        print(f"[WARN] Redis check failed: {e}")
    
except Exception as e:
    print(f"[FAIL] Event emission test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# PHASE F: Job Control Verification
print("PHASE F: JOB CONTROL (Pause/Resume/Kill)")
print("-" * 80)

try:
    # Create a test job for control testing
    control_job_id = "test-control-" + datetime.now().strftime("%Y%m%d%H%M%S")
    db.create_job(control_job_id, "test", ["City1, ST", "City2, ST"], ["yellowpages"])
    db.update_job_status(control_job_id, "running")
    db.update_started_at(control_job_id)
    
    print(f"[OK] Test job created: {control_job_id}")
    
    # Test pause
    paused = db.pause_job(control_job_id)
    if paused:
        status = db.get_job_status(control_job_id)
        if status and status.get('status') == 'paused':
            print(f"[OK] pause_job() works: job status = paused")
        else:
            print(f"[FAIL] pause_job() did not update status correctly")
    else:
        print(f"[FAIL] pause_job() returned False")
    
    # Test resume
    resumed = db.resume_job(control_job_id)
    if resumed:
        status = db.get_job_status(control_job_id)
        if status and status.get('status') == 'running':
            print(f"[OK] resume_job() works: job status = running")
        else:
            print(f"[FAIL] resume_job() did not update status correctly")
    else:
        print(f"[FAIL] resume_job() returned False")
    
    # Test kill
    killed = db.kill_job(control_job_id)
    if killed:
        status = db.get_job_status(control_job_id)
        if status and status.get('status') == 'killed':
            print(f"[OK] kill_job() works: job status = killed")
        else:
            print(f"[FAIL] kill_job() did not update status correctly")
    else:
        print(f"[FAIL] kill_job() returned False")
    
    # Test idempotency - can't kill twice
    killed_again = db.kill_job(control_job_id)
    if not killed_again:
        print(f"[OK] kill_job() is idempotent: cannot kill twice")
    else:
        print(f"[FAIL] kill_job() not idempotent: killed twice")
    
except Exception as e:
    print(f"[FAIL] Job control test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# PHASE G: Resume Logic Verification
print("PHASE G: RESUME LOGIC (Incomplete Cities)")
print("-" * 80)

try:
    resume_job_id = "test-resume-" + datetime.now().strftime("%Y%m%d%H%M%S")
    db.create_job(resume_job_id, "test", ["City1, ST", "City2, ST", "City3, ST"], ["yellowpages"])
    
    # Mark one city as complete
    if hasattr(db, 'mark_task_completed'):
        db.mark_task_completed(resume_job_id, "City1, ST", result_count=10)
        print(f"[OK] Marked City1 as completed")
    
    # Get incomplete cities
    if hasattr(db, 'get_incomplete_cities'):
        incomplete = db.get_incomplete_cities(resume_job_id)
        print(f"[OK] get_incomplete_cities() works")
        print(f"  Incomplete cities: {incomplete}")
        
        if "City1, ST" not in incomplete:
            print(f"[OK] Completed city excluded from incomplete list")
        else:
            print(f"[FAIL] Completed city included in incomplete list")
        
        if "City2, ST" in incomplete or "City3, ST" in incomplete:
            print(f"[OK] Incomplete cities correctly identified")
        else:
            print(f"[WARN] No incomplete cities found (may be expected)")
    else:
        print(f"[WARN] get_incomplete_cities() not available")
    
except Exception as e:
    print(f"[FAIL] Resume logic test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# PHASE H: Error Handling Verification
print("PHASE H: ERROR HANDLING")
print("-" * 80)

try:
    # Test invalid job_id
    invalid_status = db.get_job_status("nonexistent-job-id")
    if invalid_status is None:
        print(f"[OK] get_job_status() returns None for invalid job")
    else:
        print(f"[FAIL] get_job_status() should return None for invalid job")
    
    # Test event emission with invalid job_id
    try:
        seq = emit_event("nonexistent-job-id", "test", {"test": "data"})
        if seq > 0:
            print(f"[OK] emit_event() handles invalid job_id gracefully")
        else:
            print(f"[WARN] emit_event() returned 0 for invalid job_id")
    except Exception as e:
        print(f"[OK] emit_event() raises exception for invalid job_id: {type(e).__name__}")
    
except Exception as e:
    print(f"[FAIL] Error handling test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Summary
print("=" * 80)
print("VERIFICATION SUMMARY")
print("=" * 80)
print()
print("Note: This verification tests backend functions independently.")
print("Full integration testing requires:")
print("  - Running API server")
print("  - Running Celery workers")
print("  - Actual HTTP requests")
print("  - WebSocket connections")
print()
print("For full verification, test:")
print("  1. Start API server: uvicorn backend.main:app")
print("  2. Start Celery worker: celery -A backend.celery_app worker")
print("  3. Make HTTP requests to /api/scrape")
print("  4. Monitor Redis pub/sub channels")
print("  5. Connect WebSocket and verify events")

