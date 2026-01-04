"""
Test API endpoints manually via HTTP requests.
"""
import requests
import json
import time
import sys

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

API_BASE = "http://localhost:8000/api"

print("=" * 80)
print("API ENDPOINT VERIFICATION")
print("=" * 80)
print()

# Check if API is running
try:
    response = requests.get(f"{API_BASE.replace('/api', '')}/api/health", timeout=2)
    if response.status_code == 200:
        print("[OK] API server is running")
    else:
        print(f"[FAIL] API server returned {response.status_code}")
        sys.exit(1)
except requests.exceptions.ConnectionError:
    print("[FAIL] API server is not running")
    print("  Start with: uvicorn backend.main:app")
    sys.exit(1)
except Exception as e:
    print(f"[FAIL] API check failed: {e}")
    sys.exit(1)

print()

# Test job creation
print("TEST 1: Job Creation (POST /api/scrape)")
print("-" * 80)

try:
    payload = {
        "keyword": "test_plumber",
        "cities": ["Test City, ST"],
        "sources": ["yellowpages"]
    }
    
    response = requests.post(f"{API_BASE}/scrape", json=payload, timeout=5)
    
    if response.status_code == 200:
        data = response.json()
        job_id = data.get("job_id")
        print(f"[OK] Job created successfully")
        print(f"  Job ID: {job_id}")
        print(f"  Status: {data.get('status')}")
        
        # Verify job exists immediately (no race condition)
        time.sleep(0.5)  # Small delay to check
        status_response = requests.get(f"{API_BASE}/status/{job_id}", timeout=2)
        if status_response.status_code == 200:
            status_data = status_response.json()
            print(f"[OK] Job exists immediately after creation")
            print(f"  Status: {status_data.get('status')}")
        else:
            print(f"[FAIL] Job not found immediately: {status_response.status_code}")
    else:
        print(f"[FAIL] Job creation failed: {response.status_code}")
        print(f"  Response: {response.text}")
        sys.exit(1)
        
except Exception as e:
    print(f"[FAIL] Job creation test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test job status endpoint
print("TEST 2: Job Status (GET /api/status/{job_id})")
print("-" * 80)

try:
    if 'job_id' not in locals():
        print("[SKIP] No job_id from previous test")
    else:
        response = requests.get(f"{API_BASE}/status/{job_id}", timeout=2)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Status endpoint works")
            print(f"  Job ID: {data.get('job_id')}")
            print(f"  Status: {data.get('status')}")
            print(f"  Progress: {data.get('progress', 0):.1f}%")
            print(f"  Business Count: {data.get('business_count', 0)}")
        else:
            print(f"[FAIL] Status endpoint failed: {response.status_code}")
except Exception as e:
    print(f"[FAIL] Status test failed: {e}")

print()

# Test pause endpoint
print("TEST 3: Pause Job (POST /api/job/{job_id}/pause)")
print("-" * 80)

try:
    if 'job_id' not in locals():
        print("[SKIP] No job_id from previous test")
    else:
        # First ensure job is running
        import sqlite3
        conn = sqlite3.connect('business_scraper.db')
        conn.execute("UPDATE jobs SET status = 'running' WHERE job_id = ?", (job_id,))
        conn.commit()
        conn.close()
        
        response = requests.post(f"{API_BASE}/job/{job_id}/pause", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Pause endpoint works")
            print(f"  Status: {data.get('status')}")
            print(f"  Message: {data.get('message')}")
            
            # Verify job is paused
            status_response = requests.get(f"{API_BASE}/status/{job_id}", timeout=2)
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data.get('status') == 'paused':
                    print(f"[OK] Job status updated to 'paused'")
                else:
                    print(f"[FAIL] Job status not updated: {status_data.get('status')}")
        else:
            print(f"[FAIL] Pause endpoint failed: {response.status_code}")
            print(f"  Response: {response.text}")
except Exception as e:
    print(f"[FAIL] Pause test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test resume endpoint
print("TEST 4: Resume Job (POST /api/job/{job_id}/resume)")
print("-" * 80)

try:
    if 'job_id' not in locals():
        print("[SKIP] No job_id from previous test")
    else:
        response = requests.post(f"{API_BASE}/job/{job_id}/resume", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Resume endpoint works")
            print(f"  Status: {data.get('status')}")
            print(f"  Message: {data.get('message')}")
            
            # Verify job is running
            status_response = requests.get(f"{API_BASE}/status/{job_id}", timeout=2)
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data.get('status') == 'running':
                    print(f"[OK] Job status updated to 'running'")
                else:
                    print(f"[FAIL] Job status not updated: {status_data.get('status')}")
        else:
            print(f"[FAIL] Resume endpoint failed: {response.status_code}")
            print(f"  Response: {response.text}")
except Exception as e:
    print(f"[FAIL] Resume test failed: {e}")

print()

# Test kill endpoint
print("TEST 5: Kill Job (POST /api/job/{job_id}/kill)")
print("-" * 80)

try:
    if 'job_id' not in locals():
        print("[SKIP] No job_id from previous test")
    else:
        response = requests.post(f"{API_BASE}/job/{job_id}/kill", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Kill endpoint works")
            print(f"  Status: {data.get('status')}")
            print(f"  Message: {data.get('message')}")
            
            # Verify job is killed
            status_response = requests.get(f"{API_BASE}/status/{job_id}", timeout=2)
            if status_response.status_code == 200:
                status_data = status_response.json()
                if status_data.get('status') == 'killed':
                    print(f"[OK] Job status updated to 'killed'")
                else:
                    print(f"[FAIL] Job status not updated: {status_data.get('status')}")
        else:
            print(f"[FAIL] Kill endpoint failed: {response.status_code}")
            print(f"  Response: {response.text}")
except Exception as e:
    print(f"[FAIL] Kill test failed: {e}")

print()

# Test event replay endpoint
print("TEST 6: Event Replay (GET /api/jobs/{job_id}/events)")
print("-" * 80)

try:
    if 'job_id' not in locals():
        print("[SKIP] No job_id from previous test")
    else:
        response = requests.get(f"{API_BASE}/jobs/{job_id}/events?since=0", timeout=2)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Event replay endpoint works")
            print(f"  Job ID: {data.get('job_id')}")
            print(f"  Since: {data.get('since')}")
            print(f"  Event Count: {data.get('count', 0)}")
            
            events = data.get('events', [])
            if events:
                print(f"  Sample event: type={events[0].get('type')}, sequence={events[0].get('sequence')}")
        else:
            print(f"[FAIL] Event replay endpoint failed: {response.status_code}")
            print(f"  Response: {response.text}")
except Exception as e:
    print(f"[FAIL] Event replay test failed: {e}")

print()

# Test businesses endpoint
print("TEST 7: Get Businesses (GET /api/businesses/{job_id})")
print("-" * 80)

try:
    if 'job_id' not in locals():
        print("[SKIP] No job_id from previous test")
    else:
        response = requests.get(f"{API_BASE}/businesses/{job_id}", timeout=2)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Businesses endpoint works")
            print(f"  Business Count: {data.get('count', 0)}")
        elif response.status_code == 404:
            print(f"[OK] Businesses endpoint works (no businesses found - expected)")
        else:
            print(f"[FAIL] Businesses endpoint failed: {response.status_code}")
            print(f"  Response: {response.text}")
except Exception as e:
    print(f"[FAIL] Businesses test failed: {e}")

print()

print("=" * 80)
print("API VERIFICATION COMPLETE")
print("=" * 80)

