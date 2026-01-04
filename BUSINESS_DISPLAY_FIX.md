# Business Display Issue - Investigation & Fixes

## Issue
Frontend shows "Live Results (0 businesses)" even when businesses are being scraped.

## Root Cause Analysis

### Potential Issues Identified:
1. **WebSocket not receiving events** - Events published but not forwarded
2. **Frontend not processing events** - Events received but not displayed
3. **Businesses not being scraped** - Scraper returning empty results
4. **Events lost in Redis** - Publishing succeeds but messages not delivered

## Fixes Applied

### 1. Enhanced Debug Logging
**Files:** `frontend/app.js`, `backend/main.py`, `backend/celery_app.py`

- Added console.log statements to track:
  - WebSocket message reception
  - Business event handling
  - Table row addition
  - Business count updates

**How to use:**
- Open browser console (F12)
- Watch for log messages when businesses arrive
- Check for errors in console

### 2. JSON API Endpoint for Businesses
**File:** `backend/main.py`

- Added `/api/businesses/{job_id}` endpoint
- Returns businesses as JSON (not CSV)
- Allows frontend to load existing businesses on page refresh

### 3. Load Existing Businesses on Job Start
**File:** `frontend/app.js`

- Automatically loads businesses from database when job starts
- Handles page refresh scenario
- Populates table with existing results

### 4. Improved Error Handling
**Files:** `backend/main.py`, `backend/celery_app.py`

- Better error logging for Redis publish failures
- WebSocket forwarding errors now logged at ERROR level
- Business event publishing errors logged with stack trace

## How to Diagnose

### Step 1: Check Browser Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Start a scraping job
4. Look for:
   - "WebSocket message received: business"
   - "Business event received: ..."
   - "Adding business to table: ..."
   - "Business count updated: X"

### Step 2: Check Backend Logs
Look for:
- "Published business event: [name] for job [id]"
- "Forwarding business event to WebSocket: [name]"
- Any ERROR messages about Redis or WebSocket

### Step 3: Verify Database
```bash
python -c "from backend.database import db; import sys; job_id = sys.argv[1] if len(sys.argv) > 1 else None; businesses = db.get_businesses(job_id) if job_id else []; print(f'Businesses in DB: {len(businesses)}')"
```

### Step 4: Test WebSocket Connection
1. Check WebSocket status in UI (should show "Connected")
2. If disconnected, check for reconnection attempts in logs
3. Verify Redis is running and accessible

## Expected Behavior

### When Business is Scraped:
1. Backend: `on_business_callback` called
2. Backend: Business saved to database
3. Backend: Event published to Redis `job:{id}:events`
4. Backend: WebSocket receives from Redis
5. Backend: WebSocket forwards to frontend
6. Frontend: `handleBusinessEvent` called
7. Frontend: `addBusinessRow` called
8. Frontend: Table updated, count incremented
9. Frontend: Log entry added

### Debug Output Should Show:
```
Backend: Published business event: Business Name for job abc123
Backend: Forwarding business event to WebSocket: Business Name
Frontend: WebSocket message received: business {...}
Frontend: Business event received: {...}
Frontend: Adding business to table: Business Name
Frontend: Row added to table. Total rows: 1
Frontend: Business count updated: 1
```

## Next Steps

1. **Start a scraping job**
2. **Monitor browser console** for debug messages
3. **Check backend logs** for event publishing
4. **Verify WebSocket connection** status in UI
5. **Report findings** - which step is failing?

## Files Modified

- `frontend/app.js` - Added debug logging, load existing businesses
- `backend/main.py` - Added JSON endpoint, improved WebSocket logging
- `backend/celery_app.py` - Improved event publishing error handling

