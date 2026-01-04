// API base URL
const API_BASE = '/api';
let currentJobId = null;
let websocket = null;
let statusInterval = null;
let pingInterval = null;
let startTime = null;
let autoScrollEnabled = true;
let seenBusinesses = new Set(); // Track business duplicates frontend-side
let websocketMessageQueue = []; // Queue for messages received before loadMissedEvents completes
let isReplayingEvents = false; // Flag to track if we're replaying missed events

// Log management
const LOG_MAX_ENTRIES = 300;
let logEntries = [];
let logAutoScrollEnabled = true;

// DOM elements
const scrapeForm = document.getElementById('scrapeForm');
const statusSection = document.getElementById('statusSection');
const logSection = document.getElementById('logSection');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');
const submitBtn = document.getElementById('submitBtn');
const pauseBtn = document.getElementById('pauseBtn');
const resumeBtn = document.getElementById('resumeBtn');
const killBtn = document.getElementById('killBtn');
const downloadBtn = document.getElementById('downloadBtn');
const resetBtn = document.getElementById('resetBtn');
const resultsTableBody = document.getElementById('resultsTableBody');
const resultsCount = document.getElementById('resultsCount');
const logContainer = document.getElementById('logContainer');

// Log entry function
function addLog(message, type = 'info', meta = {}) {
    if (!logContainer) return;
    
    const timestamp = new Date().toLocaleTimeString();
    const entry = { timestamp, message, type, meta };
    logEntries.push(entry);
    
    // Keep only last LOG_MAX_ENTRIES
    if (logEntries.length > LOG_MAX_ENTRIES) {
        const removed = logEntries.shift();
        // Remove oldest DOM element if it exists
        const firstChild = logContainer.firstChild;
        if (firstChild) {
            logContainer.removeChild(firstChild);
        }
    }
    
    // Create DOM element
    const logEl = document.createElement('div');
    logEl.className = `log-entry log-${type}`;
    logEl.innerHTML = `<span class="log-time">${timestamp}</span><span class="log-msg">${escapeHtml(message)}</span>`;
    logContainer.appendChild(logEl);
    
    // Auto-scroll log to bottom (only if user hasn't scrolled up)
    const isNearBottom = logContainer.scrollHeight - logContainer.scrollTop - logContainer.clientHeight < 50;
    if (isNearBottom && logAutoScrollEnabled) {
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

// Form submission
scrapeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideError();
    
    const keyword = document.getElementById('keyword').value.trim();
    const citiesText = document.getElementById('cities').value.trim();
    const apiKey = document.getElementById('apiKey').value.trim();
    const cities = citiesText.split('\n')
        .map(city => city.trim())
        .filter(city => city.length > 0);
    
    if (!keyword) {
        showError('Please enter a search keyword');
        return;
    }
    
    if (cities.length === 0) {
        showError('Please enter at least one city');
        return;
    }
    
    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating Job...';
    
    try {
        const requestBody = {
            keyword,
            cities,
            sources: ['yellowpages']
        };
        
        // Add API key if provided
        if (apiKey) {
            requestBody.proxy_api_key = apiKey;
        }
        
        const response = await fetch(`${API_BASE}/scrape`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            let errorDetail = 'Failed to create scraping job';
            try {
                const error = await response.json();
                errorDetail = error.detail || error.message || errorDetail;
            } catch (e) {
                errorDetail = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errorDetail);
        }
        
        const data = await response.json();
        currentJobId = data.job_id;
        
        // Reset UI
        resultsTableBody.innerHTML = '';
        logContainer.innerHTML = '';
        seenBusinesses.clear();
        logEntries = [];
        startTime = Date.now();
        autoScrollEnabled = true;
        logAutoScrollEnabled = true;
        
        // Show sections
        statusSection.style.display = 'block';
        logSection.style.display = 'block';
        resultsSection.style.display = 'block';
        errorSection.style.display = 'none';
        
        // Ensure results table is visible and ready
        if (resultsTableBody) {
            resultsTableBody.innerHTML = '';
            console.log('Results table initialized and ready'); // DEBUG
        } else {
            console.error('resultsTableBody not found!'); // DEBUG
            addLog('ERROR: Results table element not found in DOM', 'error');
        }
        
        // Verify results section is visible
        if (resultsSection && resultsSection.style.display === 'none') {
            console.warn('Results section is hidden! Making visible...'); // DEBUG
            resultsSection.style.display = 'block';
        }
        
        // Log job creation
        addLog(`✓ Job created: ${currentJobId}`, 'success');
        addLog(`→ Scraping for: "${keyword}" in ${cities.length} cities`, 'info');
        addLog(`→ Cities: ${cities.join(', ')}`, 'info');
        
        // FIX: Load existing businesses FIRST (before WebSocket connects)
        // This prevents race condition where WebSocket events arrive while DB is loading
        await loadExistingBusinesses(currentJobId);
        
        // Connect WebSocket AFTER DB load completes
        updateWebSocketStatus('connecting');
        connectWebSocket(currentJobId);
        
        // Start status polling
        startStatusPolling();
        
        // Update UI
        const jobIdEl = document.getElementById('jobId');
        const jobKeywordEl = document.getElementById('jobKeyword');
        if (jobIdEl) jobIdEl.textContent = currentJobId;
        if (jobKeywordEl) jobKeywordEl.textContent = keyword;
        
        // Start elapsed time updates if status is available (async)
        setTimeout(async () => {
            try {
                const response = await fetch(`${API_BASE}/status/${currentJobId}`);
                if (response.ok) {
                    const status = await response.json();
                    if (status.started_at) {
                        startElapsedTimeUpdates(status.started_at);
                    }
                }
            } catch (e) {
                // Silent fail - will be updated via WebSocket
            }
        }, 500);
        
        // Scroll to status
        statusSection.scrollIntoView({ behavior: 'smooth' });

        // Reset button after showing confirmation
        setTimeout(() => {
            submitBtn.disabled = false;
            submitBtn.textContent = '▶ Start Scraping';
        }, 1500);

    } catch (error) {
        const errorMsg = error.message || 'An error occurred while creating the job';
        addLog(`✗ Job creation failed: ${errorMsg}`, 'error');
        showError(errorMsg);
        submitBtn.disabled = false;
        submitBtn.textContent = '▶ Start Scraping';
    }
});

// WebSocket connection
function connectWebSocket(jobId) {
    // Close existing connection if any
    if (websocket) {
        websocket.close();
        websocket = null;
    }
    
    // Clear existing ping interval
    if (pingInterval) {
        clearInterval(pingInterval);
        pingInterval = null;
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${jobId}`;
    
    // FIX Bug 1: Initialize queue flag BEFORE creating WebSocket to prevent race condition
    // Messages can arrive immediately after WebSocket creation, before onopen fires
    isReplayingEvents = true;
    websocketMessageQueue = [];
    
    websocket = new WebSocket(wsUrl);
    
    websocket.onopen = async () => {
        addLog('✓ WebSocket connected', 'success');
        updateWebSocketStatus('connected');
        
        // Queue flag already set above to prevent race condition
        
        // PHASE 2: Request missed events on connect
        // Note: This is safe because loadExistingBusinesses() already completed
        // and populated seenBusinesses, so replay won't create duplicates
        try {
            await loadMissedEvents(jobId);
        } catch (e) {
            addLog(`⚠ Error loading missed events: ${e.message}`, 'warning');
        } finally {
            // Now process queued messages
            isReplayingEvents = false;
            const queuedMessages = websocketMessageQueue.slice(); // Copy array
            websocketMessageQueue = []; // Clear queue
            
            // FIX Bug 1 & 2: Track sequence numbers FIRST (before processing) to prevent event loss
            // This ensures sequences are persisted even if message processing fails
            const lastSeqKey = `lastSeq_${jobId}`;
            let maxQueuedSeq = parseInt(localStorage.getItem(lastSeqKey) || '0', 10);
            
            // First pass: Find maximum sequence number in queued messages
            for (const message of queuedMessages) {
                if (message.sequence !== undefined && message.sequence > maxQueuedSeq) {
                    maxQueuedSeq = message.sequence;
                }
            }
            
            // FIX Bug 1: Process messages first, then save sequence only for successfully processed messages
            // This ensures we don't skip messages if processing fails
            let maxProcessedSeq = parseInt(localStorage.getItem(lastSeqKey) || '0', 10);
            
            // Process all queued messages and track sequences only for successful processing
            for (const message of queuedMessages) {
                try {
                    handleWebSocketMessage(message);
                    // Only update sequence if processing succeeded
                    if (message.sequence !== undefined && message.sequence > maxProcessedSeq) {
                        maxProcessedSeq = message.sequence;
                    }
                } catch (e) {
                    // If processing fails, don't update sequence - allow retry on reconnect
                    addLog(`✗ Failed to process queued message (seq ${message.sequence || '?'}): ${e.message}`, 'error');
                    console.error('Queued message processing failed, sequence not saved:', e, message);
                    // Continue processing other messages
                }
            }
            
            // Save maximum successfully processed sequence
            if (maxProcessedSeq > parseInt(localStorage.getItem(lastSeqKey) || '0', 10)) {
                localStorage.setItem(lastSeqKey, maxProcessedSeq.toString());
            }
            
            if (queuedMessages.length > 0) {
                addLog(`Processed ${queuedMessages.length} queued WebSocket messages (max seq: ${maxQueuedSeq})`, 'info');
            }
        }
        
        // Send ping every 30 seconds to keep connection alive
        pingInterval = setInterval(() => {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                try {
                    websocket.send('ping');
                } catch (e) {
                    addLog(`✗ Failed to send ping: ${e.message}`, 'error');
                }
            }
        }, 30000);
    };
    
    websocket.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            console.log('WebSocket message received:', message.type, message); // DEBUG
            
            // FIX Bug 3: Queue messages if we're still replaying missed events
            // Sequence tracking must happen AFTER replay check to prevent race condition
            if (isReplayingEvents) {
                websocketMessageQueue.push(message);
                console.log(`Queued WebSocket message (${websocketMessageQueue.length} in queue)`, message.type);
            } else {
                // Process immediately if replay is complete
                // FIX Bug 1: Only save sequence AFTER successful message processing
                // This ensures we don't skip messages if processing fails
                try {
                    handleWebSocketMessage(message);
                    
                    // PHASE 2: Track sequence number for event replay (AFTER successful processing)
                    // FIX Bug 1: Only update sequence after message processing succeeds
                    if (message.sequence !== undefined) {
                        const lastSeqKey = `lastSeq_${jobId}`;
                        const currentSeq = parseInt(localStorage.getItem(lastSeqKey) || '0', 10);
                        if (message.sequence > currentSeq) {
                            localStorage.setItem(lastSeqKey, message.sequence.toString());
                        }
                    }
                } catch (e) {
                    // If processing fails, don't save sequence - allow retry on reconnect
                    addLog(`✗ Failed to process message (seq ${message.sequence || '?'}): ${e.message}`, 'error');
                    console.error('Message processing failed, sequence not saved:', e, message);
                    // Re-throw to be caught by outer try-catch
                    throw e;
                }
            }
        } catch (e) {
            addLog(`✗ Failed to parse WebSocket message: ${e.message}`, 'error');
            const rawData = event.data ? String(event.data).substring(0, 100) : 'No data';
            addLog(`Raw message: ${rawData}`, 'error');
            console.error('WebSocket parse error:', e, event.data); // DEBUG
        }
    };
    
    websocket.onerror = (error) => {
        addLog('✗ WebSocket error occurred', 'error');
        updateWebSocketStatus('error');
        console.error('WebSocket error:', error);
    };
    
    websocket.onclose = (event) => {
        // Clear ping interval
        if (pingInterval) {
            clearInterval(pingInterval);
            pingInterval = null;
        }
        
        const reason = event.reason || 'Connection closed';
        const code = event.code || 'Unknown';
        addLog(`⚠ WebSocket disconnected (code: ${code}, reason: ${reason})`, 'warning');
        updateWebSocketStatus('disconnected');
        
        // Reconnect after 3 seconds (only if job is still active)
        setTimeout(() => {
            if (currentJobId && currentJobId === jobId) {
                addLog('↻ Attempting to reconnect WebSocket...', 'info');
                updateWebSocketStatus('connecting');
                connectWebSocket(currentJobId);
            }
        }, 3000);
    };
}

// Handle WebSocket messages
function handleWebSocketMessage(message) {
    if (!message || typeof message !== 'object') {
        addLog('⚠ Received invalid WebSocket message', 'warning');
        return;
    }
    
    try {
        switch (message.type) {
            case 'business':
                handleBusinessEvent(message);
                break;
            case 'extraction_stats':
                handleExtractionStats(message);
                break;
            case 'status':
                if (message.data) {
                    updateStatusDisplay(message.data);
                    const status = message.data.status?.toUpperCase() || 'UNKNOWN';
                    addLog(`Status: ${status}`, 'info');
                } else {
                    addLog('⚠ Status event missing data', 'warning');
                }
                break;
            case 'progress':
                if (message.data) {
                    updateProgress(message.data);
                    if (message.data.city) {
                        addLog(`Processing: ${message.data.city} (Page ${message.data.page || '?'})`, 'info');
                    }
                }
                break;
            case 'warning':
                handleWarningEvent(message);
                break;
            case 'error':
                handleErrorEvent(message);
                break;
            case 'pong':
                // Keep alive - silent
                break;
            default:
                addLog(`Event [${message.type || 'unknown'}]: ${JSON.stringify(message.data || {})}`, 'info');
        }
    } catch (e) {
        addLog(`✗ Error handling WebSocket message: ${e.message}`, 'error');
        console.error('Error handling WebSocket message:', e, message);
    }
}

// Handle business event
function handleBusinessEvent(message) {
    console.log('Business event received:', message); // DEBUG
    
    const data = message.data;
    if (!data || !data.name) {
        addLog('⚠ Received invalid business event', 'warning');
        console.warn('Invalid business event:', message); // DEBUG
        return;
    }
    
    const businessKey = `${data.name}|${data.website || ''}|${data.city || ''}`;
    
    // FIX: Show ALL businesses live, even if duplicate within same job
    // Each job run is independent - show all parsed results
    const isNew = !seenBusinesses.has(businessKey);
    if (isNew) {
        seenBusinesses.add(businessKey);
    }
    
    // DEBUG: Log before adding
    console.log('Adding business to table:', data);
    
    // Always add to table for live visibility
    addBusinessRow(data);
    updateBusinessCount();
    
    // Log business (mark if duplicate)
    const websiteInfo = data.website ? ` | ${data.website}` : '';
    const cityInfo = data.city ? ` (${data.city})` : '';
    const duplicateTag = isNew ? '' : ' [duplicate]';
    addLog(`✓ Business: ${data.name}${cityInfo}${websiteInfo}${duplicateTag}`, isNew ? 'success' : 'info');
}

// Handle extraction stats
function handleExtractionStats(message) {
    const stats = message.data;
    const city = message.city || message.data?.city || 'Unknown';
    const total = stats.total_businesses || 0;
    const withWebsite = stats.with_website || 0;
    addLog(`Stats [${city}]: ${total} businesses found, ${withWebsite} with websites`, 'info');
    
    if (total === 0) {
        addLog(`⚠ No businesses found for ${city}`, 'warning');
    }
}

// Handle warning events
function handleWarningEvent(message) {
    const data = message.data || {};
    const msg = data.message || data.reason || 'Warning received';
    const city = data.city ? ` [${data.city}]` : '';
    addLog(`⚠ WARNING${city}: ${msg}`, 'warning');
}

// Handle error events
function handleErrorEvent(message) {
    const data = message.data || {};
    const msg = data.message || data.error || 'Error occurred';
    const city = data.city ? ` [${data.city}]` : '';
    addLog(`✗ ERROR${city}: ${msg}`, 'error');
}

// Add business row to table
function addBusinessRow(business) {
    if (!resultsTableBody) {
        addLog('⚠ Results table not available', 'warning');
        console.error('resultsTableBody is null!'); // DEBUG
        return;
    }
    
    if (!business || !business.name) {
        addLog('⚠ Invalid business data received', 'warning');
        console.warn('Invalid business data:', business); // DEBUG
        return;
    }
    
    try {
        console.log('Creating row for business:', business.name); // DEBUG
        
        const row = document.createElement('tr');
        row.className = business.duplicate ? 'duplicate-row' : 'new-row';
        
        // Add highlight animation for new rows
        if (!business.duplicate) {
            row.style.animation = 'fadeIn 0.3s ease-in';
        }
        
        const websiteCell = business.website 
            ? `<a href="${business.website}" target="_blank" rel="noopener">${escapeHtml(business.website)}</a>`
            : '<span style="color: #666;">-</span>';
        
        row.innerHTML = `
            <td>${escapeHtml(business.name || 'Unknown')}</td>
            <td>${websiteCell}</td>
            <td>${escapeHtml(business.city || '-')}</td>
            <td>${business.page || '-'}</td>
            <td><span class="status-badge ${business.status || 'new'}">${business.status || 'new'}</span></td>
        `;
        
        resultsTableBody.appendChild(row);
        console.log('Row added to table. Total rows:', resultsTableBody.children.length); // DEBUG
        
        // Auto-scroll to bottom if enabled
        if (autoScrollEnabled) {
            const tableContainer = resultsTableBody.closest('.table-container');
            if (tableContainer) {
                tableContainer.scrollTop = tableContainer.scrollHeight;
            }
        }
    } catch (e) {
        addLog(`✗ Error adding business row: ${e.message}`, 'error');
        console.error('Error adding business row:', e, business);
    }
}

// Update business count
function updateBusinessCount() {
    if (!resultsTableBody || !resultsCount) {
        console.warn('Cannot update business count - elements not found'); // DEBUG
        return;
    }
    const count = resultsTableBody.children.length;
    resultsCount.textContent = `(${count} businesses)`;
    console.log(`Business count updated: ${count}`); // DEBUG
    
    // Ensure results section is visible when we have businesses
    if (count > 0 && resultsSection && resultsSection.style.display === 'none') {
        console.log('Making results section visible - businesses found'); // DEBUG
        resultsSection.style.display = 'block';
    }
}

// Update status display
function updateStatusDisplay(status) {
    if (!status) {
        addLog('⚠ Received null status update', 'warning');
        return;
    }
    
    const statusEl = document.getElementById('jobStatus');
    if (statusEl && status.status) {
        statusEl.textContent = status.status.toUpperCase();
        statusEl.className = `value status-badge ${status.status.toLowerCase()}`;
    }
    
    const businessCountEl = document.getElementById('businessCount');
    if (businessCountEl) {
        businessCountEl.textContent = status.business_count || 0;
    }
    
    const progress = status.progress || 0;
    const progressEl = document.getElementById('jobProgress');
    const progressBarEl = document.getElementById('progressBar');
    if (progressEl) {
        progressEl.textContent = `${Math.round(progress)}%`;
    }
    if (progressBarEl) {
        progressBarEl.style.width = `${progress}%`;
    }
    
    // Update button visibility based on status
    if (status.status) {
        showControlButtons(status.status.toLowerCase());
    }
    
    // Update elapsed time
    if (status.started_at) {
        updateElapsedTime(status.started_at);
        // Start/restart elapsed time updates if job is running
        if (status.status && (status.status.toLowerCase() === 'running' || status.status.toLowerCase() === 'paused')) {
            startElapsedTimeUpdates(status.started_at);
        } else {
            stopElapsedTimeUpdates();
        }
    }
}

// Control button visibility
function showControlButtons(status) {
    // Use inline-block for better alignment
    pauseBtn.style.display = status === 'running' ? 'inline-block' : 'none';
    resumeBtn.style.display = status === 'paused' ? 'inline-block' : 'none';
    killBtn.style.display = (status === 'running' || status === 'paused') ? 'inline-block' : 'none';
    downloadBtn.style.display = (status === 'completed' || status === 'killed') ? 'inline-block' : 'none';
    resetBtn.style.display = (status === 'completed' || status === 'killed' || status === 'error') ? 'inline-block' : 'none';
}

function hideControlButtons() {
    pauseBtn.style.display = 'none';
    resumeBtn.style.display = 'none';
    killBtn.style.display = 'none';
    downloadBtn.style.display = 'none';
    resetBtn.style.display = 'none';
}

// Update progress
function updateProgress(progress) {
    if (!progress) return;
    
    const cityEl = document.getElementById('currentCity');
    if (cityEl && progress.city) {
        cityEl.textContent = progress.city;
    }
    
    const pageEl = document.getElementById('currentPage');
    if (pageEl && progress.page) {
        pageEl.textContent = progress.page;
    }
    
    const businessCountEl = document.getElementById('businessCount');
    if (businessCountEl && progress.businesses_count !== undefined) {
        businessCountEl.textContent = progress.businesses_count;
    }
}

// Control buttons
pauseBtn.addEventListener('click', async () => {
    try {
        addLog('→ Pausing job...', 'info');
        const response = await fetch(`${API_BASE}/job/${currentJobId}/pause`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to pause job');
        addLog('✓ Job paused', 'success');
        // Status will update via WebSocket
    } catch (error) {
        addLog(`✗ Failed to pause job: ${error.message}`, 'error');
        showError('Failed to pause job: ' + error.message);
    }
});

resumeBtn.addEventListener('click', async () => {
    try {
        addLog('→ Resuming job...', 'info');
        const response = await fetch(`${API_BASE}/job/${currentJobId}/resume`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to resume job');
        addLog('✓ Job resumed', 'success');
        // Status will update via WebSocket
    } catch (error) {
        addLog(`✗ Failed to resume job: ${error.message}`, 'error');
        showError('Failed to resume job: ' + error.message);
    }
});

killBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to kill this job? This action cannot be undone.')) {
        return;
    }
    
    try {
        addLog('→ Stopping job...', 'warning');
        const response = await fetch(`${API_BASE}/job/${currentJobId}/kill`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to kill job');
        addLog('✓ Job stopped', 'warning');
        // Status will update via WebSocket
    } catch (error) {
        addLog(`✗ Failed to stop job: ${error.message}`, 'error');
        showError('Failed to kill job: ' + error.message);
    }
});

downloadBtn.addEventListener('click', () => {
    if (currentJobId) {
        window.location.href = `${API_BASE}/download/${currentJobId}`;
    }
});

resetBtn.addEventListener('click', async () => {
    if (!confirm('Reset will clear all data and form. Continue?')) {
        return;
    }
    
    // Log reset
    addLog('Resetting job...', 'info');
    
    // Clear current job
    currentJobId = null;
    
    // Clear UI
    document.getElementById('keyword').value = '';
    document.getElementById('cities').value = '';
    document.getElementById('apiKey').value = '';
    resultsTableBody.innerHTML = '';
    logContainer.innerHTML = '';
    seenBusinesses.clear();
    logEntries = [];
    updateBusinessCount();
    
    // Hide sections
    statusSection.style.display = 'none';
    logSection.style.display = 'none';
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';
    
    // Close WebSocket
    if (websocket) {
        websocket.close();
        websocket = null;
    }
    
    // Clear ping interval
    if (pingInterval) {
        clearInterval(pingInterval);
        pingInterval = null;
    }
    
    updateWebSocketStatus('disconnected');
    
    // Clear intervals
    if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
    }
    
    stopElapsedTimeUpdates();
    
    // Reset button visibility
    hideControlButtons();
    
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
});

// Status polling (fallback if WebSocket fails)
function startStatusPolling() {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
    
    statusInterval = setInterval(async () => {
        if (currentJobId) {
            try {
                const response = await fetch(`${API_BASE}/status/${currentJobId}`);
                if (response.ok) {
                    const status = await response.json();
                    updateStatusDisplay(status);
                } else {
                    addLog(`⚠ Status poll failed: HTTP ${response.status}`, 'warning');
                }
            } catch (error) {
                addLog(`✗ Network error polling status: ${error.message}`, 'error');
                console.error('Error polling status:', error);
            }
        }
    }, 2000);
}

// Update elapsed time
function updateElapsedTime(startedAt) {
    if (!startedAt) return;
    
    try {
        const start = new Date(startedAt).getTime();
        if (isNaN(start)) {
            addLog(`⚠ Invalid start time: ${startedAt}`, 'warning');
            return;
        }
        
        const now = Date.now();
        const elapsed = Math.floor((now - start) / 1000);
        
        if (elapsed < 0) {
            return; // Don't show negative time
        }
        
        const hours = Math.floor(elapsed / 3600);
        const minutes = Math.floor((elapsed % 3600) / 60);
        const seconds = elapsed % 60;
        
        const timeString = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        const elapsedTimeEl = document.getElementById('elapsedTime');
        if (elapsedTimeEl) {
            elapsedTimeEl.textContent = timeString;
        }
    } catch (e) {
        addLog(`✗ Error updating elapsed time: ${e.message}`, 'error');
    }
}

// Update elapsed time every second (only when job is running)
let elapsedTimeInterval = null;
function startElapsedTimeUpdates(startedAt) {
    if (elapsedTimeInterval) {
        clearInterval(elapsedTimeInterval);
    }
    
    if (!startedAt) return;
    
    elapsedTimeInterval = setInterval(() => {
        const statusEl = document.getElementById('jobStatus');
        if (statusEl) {
            const status = statusEl.textContent;
            if (status === 'RUNNING' || status === 'PAUSED') {
                updateElapsedTime(startedAt);
            } else {
                // Stop updating if job is not running/paused
                if (elapsedTimeInterval) {
                    clearInterval(elapsedTimeInterval);
                    elapsedTimeInterval = null;
                }
            }
        }
    }, 1000);
}

function stopElapsedTimeUpdates() {
    if (elapsedTimeInterval) {
        clearInterval(elapsedTimeInterval);
        elapsedTimeInterval = null;
    }
}

// Error handling
function showError(message) {
    if (!errorSection) return;
    
    errorSection.style.display = 'block';
    const errorMsgEl = document.getElementById('errorMessage');
    if (errorMsgEl) {
        errorMsgEl.textContent = message || 'An unknown error occurred';
    }
    addLog(`Error: ${message || 'Unknown error'}`, 'error');
    errorSection.scrollIntoView({ behavior: 'smooth' });
}

function hideError() {
    if (errorSection) {
        errorSection.style.display = 'none';
    }
}

// Update WebSocket status indicator
function updateWebSocketStatus(status) {
    const wsStatusEl = document.getElementById('wsStatus');
    if (!wsStatusEl) return;
    
    const statusMap = {
        'connected': { text: 'Connected', class: 'ws-connected' },
        'disconnected': { text: 'Disconnected', class: 'ws-disconnected' },
        'connecting': { text: 'Connecting...', class: 'ws-connecting' },
        'error': { text: 'Error', class: 'ws-error' }
    };
    
    const statusInfo = statusMap[status] || { text: 'Unknown', class: '' };
    wsStatusEl.textContent = statusInfo.text;
    wsStatusEl.className = `value ${statusInfo.class}`;
}

// Load existing businesses from database
async function loadExistingBusinesses(jobId) {
    if (!jobId) return;
    
    try {
        // Fetch businesses as JSON
        const response = await fetch(`${API_BASE}/businesses/${jobId}`);
        if (response.ok) {
            const data = await response.json();
            const businesses = data.businesses || [];
            const count = data.count || 0;
            
            if (count > 0) {
                addLog(`Loading ${count} existing businesses from database...`, 'info');
                
                // FIX: Mark all businesses as seen FIRST (before adding to table)
                // This prevents race condition if WebSocket connects during this loop
                const businessKeys = [];
                for (const business of businesses) {
                    const businessKey = `${business.name}|${business.website || ''}|${business.city || ''}`;
                    businessKeys.push({ key: businessKey, business });
                    // Mark as seen immediately to prevent duplicates
                    seenBusinesses.add(businessKey);
                }
                
                // Now add to table (all keys already in seenBusinesses)
                for (const { business } of businessKeys) {
                    addBusinessRow({
                        name: business.name,
                        website: business.website,
                        city: business.city,
                        page: '-', // Unknown from DB
                        status: 'new',
                        duplicate: false
                    });
                }
                
                updateBusinessCount();
                addLog(`Loaded ${count} businesses into results table`, 'success');
            } else {
                // No businesses yet - still mark as loaded to prevent race condition
                addLog('No existing businesses found', 'info');
            }
        } else if (response.status === 404) {
            // No businesses yet, that's fine
            console.debug('No businesses found yet for job');
        }
    } catch (e) {
        console.debug('Could not load existing businesses:', e);
        // Non-critical, but log for debugging
        addLog(`⚠ Could not load existing businesses: ${e.message}`, 'warning');
    }
}

// PHASE 2: Load missed events from database (event replay)
async function loadMissedEvents(jobId) {
    if (!jobId) return;
    
    try {
        // Get last seen sequence from localStorage
        const lastSeqKey = `lastSeq_${jobId}`;
        const lastSeq = parseInt(localStorage.getItem(lastSeqKey) || '0', 10);
        
        // Fetch events since last sequence
        const response = await fetch(`${API_BASE}/jobs/${jobId}/events?since=${lastSeq}`);
        if (response.ok) {
            const data = await response.json();
            const events = data.events || [];
            const count = data.count || 0;
            
            if (count > 0) {
                addLog(`Replaying ${count} missed events...`, 'info');
                
                let maxProcessedSeq = lastSeq;
                
                // FIX Bug 2: Process events and track sequence only for successfully processed events
                // This ensures failed events can be retried on next reconnect
                for (const event of events) {
                    try {
                        // Handle event based on type
                        // Business events will be deduplicated by handleBusinessEvent()
                        handleWebSocketMessage({
                            type: event.type,
                            job_id: jobId,
                            data: event.data,
                            sequence: event.sequence
                        });
                        
                        // Only advance sequence if processing succeeded
                        if (event.sequence > maxProcessedSeq) {
                            maxProcessedSeq = event.sequence;
                        }
                    } catch (e) {
                        // If processing fails, don't advance sequence - allow retry on reconnect
                        addLog(`✗ Failed to replay event (seq ${event.sequence || '?'}): ${e.message}`, 'error');
                        console.error('Event replay failed, sequence not advanced:', e, event);
                        // Continue processing other events
                    }
                }
                
                // Save last successfully processed sequence
                if (maxProcessedSeq > lastSeq) {
                    localStorage.setItem(lastSeqKey, maxProcessedSeq.toString());
                    addLog(`Replayed ${count} events (seq ${lastSeq} → ${maxProcessedSeq})`, 'success');
                } else {
                    addLog(`Replayed ${count} events (no sequence advancement)`, 'warning');
                }
            }
        } else if (response.status === 404) {
            // No events yet, that's fine
            console.debug('No events found for job');
        }
    } catch (e) {
        console.debug('Could not load missed events:', e);
        // Non-critical, continue
    }
}

// Utility functions
function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Table scroll handler (disable auto-scroll if user scrolls up)
const tableContainer = document.querySelector('.table-container');
if (tableContainer) {
    let lastScrollTop = 0;
    tableContainer.addEventListener('scroll', () => {
        const scrollTop = tableContainer.scrollTop;
        const scrollHeight = tableContainer.scrollHeight;
        const clientHeight = tableContainer.clientHeight;
        
        // If user scrolls up, disable auto-scroll
        if (scrollTop < lastScrollTop) {
            autoScrollEnabled = false;
        }
        
        // If user scrolls to bottom, re-enable auto-scroll
        if (scrollTop + clientHeight >= scrollHeight - 10) {
            autoScrollEnabled = true;
        }
        
        lastScrollTop = scrollTop;
    });
}

// Log container scroll handler
if (logContainer) {
    let logLastScrollTop = 0;
    
    logContainer.addEventListener('scroll', () => {
        const scrollTop = logContainer.scrollTop;
        const scrollHeight = logContainer.scrollHeight;
        const clientHeight = logContainer.clientHeight;
        
        // If user scrolls up, disable auto-scroll
        if (scrollTop < logLastScrollTop) {
            logAutoScrollEnabled = false;
        }
        
        // If user scrolls to bottom, re-enable auto-scroll
        if (scrollTop + clientHeight >= scrollHeight - 10) {
            logAutoScrollEnabled = true;
        }
        
        logLastScrollTop = scrollTop;
    });
}
