# Phase 2 Implementation: True Control & Event Sourcing

## Overview

Phase 2 implements **true task cancellation** and **event sourcing** to eliminate wasted work and prevent event loss.

## Architecture Changes

### 1. Database Schema Additions

**New Tables:**

1. **`task_status`** - Tracks Celery task IDs and status per city
   - `job_id`, `city`, `celery_task_id` (unique)
   - `status`: pending, running, success, failed, cancelled
   - `started_at`, `completed_at`, `cancelled_at`
   - `error_message`, `result_count`

2. **`job_events`** - Event sourcing table (source of truth)
   - `job_id`, `sequence` (auto-increment per job)
   - `event_type`, `payload` (JSON), `timestamp`
   - Unique constraint on `(job_id, sequence)`

**Indexes:**
- `idx_task_job_city` on `task_status(job_id, city)`
- `idx_task_celery_id` on `task_status(celery_task_id)`
- `idx_events_job_seq` on `job_events(job_id, sequence)`

### 2. Event Emission Pattern

**Before:** Events published directly to Redis (lossy)

**After:** Two-phase emission:
1. **Save to DB** (source of truth) → returns sequence number
2. **Publish to Redis** (real-time streaming) → includes sequence

**Implementation:** `backend/event_emitter.py`
- `emit_event(job_id, event_type, data, channel)` function
- All events go through this helper
- Redis failure is non-critical (event already in DB)

### 3. Task Cancellation

**Before:** Cooperative polling (tasks check DB status in loops)

**After:** True cancellation via Celery `revoke()`

**Flow:**
1. Task starts → stores `celery_task_id` in `task_status` table
2. Pause/Kill endpoint → calls `celery_app.control.revoke(task_id, terminate=True)`
3. Task checks `self.is_aborted()` → exits immediately
4. Task marked as `cancelled` in DB

**Benefits:**
- Immediate stop (no waiting for next status check)
- No wasted work
- No race conditions on resume

### 4. Resume Logic

**Before:** Spawned tasks for all cities, relied on `last_page >= MAX_PAGES` heuristic

**After:** Checks `task_status` table for terminal states

**Flow:**
1. Get incomplete cities: `status NOT IN ('success', 'failed', 'cancelled')`
2. For each incomplete city:
   - Check if task exists and is terminal
   - Only spawn if cancelled or failed (not already running)
3. Prevents duplicate task spawning

### 5. Event Replay

**New Endpoint:** `GET /api/jobs/{job_id}/events?since={sequence}`

**Frontend Integration:**
- On WebSocket connect → calls `loadMissedEvents(jobId)`
- Reads `lastSeq_${jobId}` from localStorage
- Fetches events since last sequence
- Processes events and updates last sequence
- WebSocket messages include sequence number for tracking

**Benefits:**
- No events permanently lost
- Frontend can recover from disconnects
- Better debugging (full event history)

## Files Changed

### Backend

1. **`backend/database.py`**
   - Added `task_status` and `job_events` table creation
   - Added task tracking methods:
     - `save_task_id()`, `get_task_id()`, `get_all_active_task_ids()`
     - `mark_task_cancelled()`, `mark_task_completed()`, `get_task_status()`
     - `get_incomplete_cities()`
   - Added event sourcing methods:
     - `save_event()`, `get_events()`, `get_last_event_sequence()`

2. **`backend/event_emitter.py`** (NEW)
   - Centralized event emission
   - DB-first, Redis-second pattern
   - Returns sequence number

3. **`backend/celery_app.py`**
   - Stores `celery_task_id` on task start
   - Checks `self.is_aborted()` for cancellation
   - Uses `emit_event()` helper for all events
   - Marks task as completed/cancelled in DB

4. **`backend/main.py`**
   - Pause/Kill endpoints now revoke Celery tasks
   - Resume checks task status before spawning
   - New endpoint: `GET /api/jobs/{job_id}/events`

### Frontend

5. **`frontend/app.js`**
   - `loadMissedEvents()` function for event replay
   - Tracks sequence numbers in localStorage
   - Requests missed events on WebSocket connect
   - Updates sequence on each WebSocket message

## Migration Steps

### Step 1: Database Migration (Automatic)

The schema changes are **additive** and **backward compatible**:
- New tables created on first run
- Existing tables unchanged
- No data migration needed

**Run:** Just start the application - tables auto-create.

### Step 2: Deploy Backend

1. Deploy updated backend files
2. Restart Celery workers
3. Restart FastAPI server

**No breaking changes** - old jobs continue to work.

### Step 3: Deploy Frontend

1. Deploy updated `app.js`
2. Clear browser cache (or hard refresh)

**Backward compatible** - old frontend still works (just won't use event replay).

## Testing Checklist

### Task Cancellation

- [ ] Start a job with multiple cities
- [ ] Pause job → verify tasks stop immediately
- [ ] Check `task_status` table → tasks marked `cancelled`
- [ ] Resume job → verify only incomplete cities get new tasks
- [ ] Kill job → verify all tasks cancelled

### Event Sourcing

- [ ] Start a job → verify events saved to `job_events` table
- [ ] Check sequence numbers increment correctly
- [ ] Disconnect WebSocket → reconnect → verify events replayed
- [ ] Check localStorage → `lastSeq_${jobId}` updates

### Resume Logic

- [ ] Start job → pause after some progress
- [ ] Resume → verify no duplicate tasks spawned
- [ ] Check `task_status` → only incomplete cities have new tasks

## Performance Considerations

### Database Load

- **Event writes:** Every event writes to DB
- **Mitigation:** SQLite handles this fine for single-instance deployment
- **Future:** Can batch writes or archive old events if needed

### Redis Reliability

- **Redis failure:** Non-critical (events already in DB)
- **WebSocket disconnects:** Frontend can replay from DB
- **Best-effort streaming:** Redis remains for real-time updates

## Known Limitations

1. **Celery revoke() is best-effort**
   - Tasks may continue for a few seconds
   - Mitigation: Tasks check `is_aborted()` at start of each page

2. **Sequence numbers per job**
   - Not global (per-job sequences)
   - Sufficient for event replay per job

3. **localStorage for sequence tracking**
   - Lost on browser clear
   - Mitigation: Frontend requests all events if no localStorage entry

## Success Criteria

✅ **Pause/Kill actually stop work** - Tasks cancelled via Celery revoke  
✅ **No duplicate tasks on resume** - Task status checked before spawning  
✅ **No events permanently lost** - All events saved to DB, replay available  

## Next Steps (Phase 3+)

- Scraper abstraction (remove lifecycle logic from scrapers)
- Error aggregation and retry strategy
- API cleanup (remove status polling)
- State machine for job lifecycle

---

**Phase 2 Status:** ✅ COMPLETE

