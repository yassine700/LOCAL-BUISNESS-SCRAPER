// API base URL
const API_BASE = '/api';
let currentJobId = null;
let websocket = null;
let statusInterval = null;
let startTime = null;
let autoScrollEnabled = true;

// DOM elements
const scrapeForm = document.getElementById('scrapeForm');
const statusSection = document.getElementById('statusSection');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');
const submitBtn = document.getElementById('submitBtn');
const pauseBtn = document.getElementById('pauseBtn');
const resumeBtn = document.getElementById('resumeBtn');
const killBtn = document.getElementById('killBtn');
const downloadBtn = document.getElementById('downloadBtn');
const resultsTableBody = document.getElementById('resultsTableBody');
const resultsCount = document.getElementById('resultsCount');

// Form submission
scrapeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideError();
    
    const keyword = document.getElementById('keyword').value.trim();
    const citiesText = document.getElementById('cities').value.trim();
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
        const response = await fetch(`${API_BASE}/scrape`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                keyword,
                cities,
                sources: ['yellowpages']
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create scraping job');
        }
        
        const data = await response.json();
        currentJobId = data.job_id;
        
        // Reset UI
        resultsTableBody.innerHTML = '';
        startTime = Date.now();
        autoScrollEnabled = true;
        
        // Show sections
        statusSection.style.display = 'block';
        resultsSection.style.display = 'block';
        errorSection.style.display = 'none';
        
        // Connect WebSocket
        connectWebSocket(currentJobId);
        
        // Start status polling
        startStatusPolling();
        
        // Update UI
        document.getElementById('jobId').textContent = currentJobId;
        document.getElementById('jobKeyword').textContent = keyword;
        
        // Scroll to status
        statusSection.scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        showError(error.message || 'An error occurred while creating the job');
        submitBtn.disabled = false;
        submitBtn.textContent = '▶ Start Scraping';
    }
});

// WebSocket connection
function connectWebSocket(jobId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${jobId}`;
    
    websocket = new WebSocket(wsUrl);
    
    websocket.onopen = () => {
        console.log('WebSocket connected');
    };
    
    websocket.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        }
    };
    
    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    websocket.onclose = () => {
        console.log('WebSocket disconnected');
        // Reconnect after 3 seconds
        setTimeout(() => {
            if (currentJobId) {
                connectWebSocket(currentJobId);
            }
        }, 3000);
    };
    
    // Send ping every 30 seconds to keep connection alive
    setInterval(() => {
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send('ping');
        }
    }, 30000);
}

// Handle WebSocket messages
function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'business':
            addBusinessRow(message.data);
            updateBusinessCount();
            break;
        case 'status':
            updateStatusDisplay(message.data);
            break;
        case 'progress':
            updateProgress(message.data);
            break;
        case 'pong':
            // Keep alive
            break;
    }
}

// Add business row to table
function addBusinessRow(business) {
    const row = document.createElement('tr');
    row.className = business.duplicate ? 'duplicate-row' : 'new-row';
    
    const websiteCell = business.website 
        ? `<a href="${business.website}" target="_blank" rel="noopener">${business.website}</a>`
        : '<span style="color: #666;">-</span>';
    
    row.innerHTML = `
        <td>${escapeHtml(business.name)}</td>
        <td>${websiteCell}</td>
        <td>${escapeHtml(business.city)}</td>
        <td>${escapeHtml(business.state)}</td>
        <td>${business.page}</td>
        <td><span class="status-badge ${business.status}">${business.status}</span></td>
    `;
    
    resultsTableBody.appendChild(row);
    
    // Auto-scroll to bottom if enabled
    if (autoScrollEnabled) {
        resultsTableBody.parentElement.scrollTop = resultsTableBody.parentElement.scrollHeight;
    }
}

// Update business count
function updateBusinessCount() {
    const count = resultsTableBody.children.length;
    resultsCount.textContent = `(${count} businesses)`;
}

// Update status display
function updateStatusDisplay(status) {
    document.getElementById('jobStatus').textContent = status.status.toUpperCase();
    document.getElementById('jobStatus').className = `value status-badge ${status.status.toLowerCase()}`;
    
    document.getElementById('businessCount').textContent = status.business_count || 0;
    
    const progress = status.progress || 0;
    document.getElementById('jobProgress').textContent = `${Math.round(progress)}%`;
    document.getElementById('progressBar').style.width = `${progress}%`;
    
    // Update button visibility based on status
    const statusLower = status.status.toLowerCase();
    pauseBtn.style.display = statusLower === 'running' ? 'inline-block' : 'none';
    resumeBtn.style.display = statusLower === 'paused' ? 'inline-block' : 'none';
    killBtn.style.display = (statusLower === 'running' || statusLower === 'paused') ? 'inline-block' : 'none';
    downloadBtn.style.display = (statusLower === 'completed' || statusLower === 'killed') ? 'inline-block' : 'none';
    
    // Update elapsed time
    if (status.started_at) {
        updateElapsedTime(status.started_at);
    }
}

// Update progress
function updateProgress(progress) {
    if (progress.city) {
        document.getElementById('currentCity').textContent = progress.city;
    }
    if (progress.page) {
        document.getElementById('currentPage').textContent = progress.page;
    }
    if (progress.businesses_count !== undefined) {
        document.getElementById('businessCount').textContent = progress.businesses_count;
    }
}

// Control buttons
pauseBtn.addEventListener('click', async () => {
    try {
        const response = await fetch(`${API_BASE}/job/${currentJobId}/pause`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to pause job');
        // Status will update via WebSocket
    } catch (error) {
        showError('Failed to pause job: ' + error.message);
    }
});

resumeBtn.addEventListener('click', async () => {
    try {
        const response = await fetch(`${API_BASE}/job/${currentJobId}/resume`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to resume job');
        // Status will update via WebSocket
    } catch (error) {
        showError('Failed to resume job: ' + error.message);
    }
});

killBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to kill this job? This action cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/job/${currentJobId}/kill`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to kill job');
        // Status will update via WebSocket
    } catch (error) {
        showError('Failed to kill job: ' + error.message);
    }
});

downloadBtn.addEventListener('click', () => {
    if (currentJobId) {
        window.location.href = `${API_BASE}/download/${currentJobId}`;
    }
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
                }
            } catch (error) {
                console.error('Error polling status:', error);
            }
        }
    }, 2000);
}

// Update elapsed time
function updateElapsedTime(startedAt) {
    const start = new Date(startedAt).getTime();
    const now = Date.now();
    const elapsed = Math.floor((now - start) / 1000);
    
    const hours = Math.floor(elapsed / 3600);
    const minutes = Math.floor((elapsed % 3600) / 60);
    const seconds = elapsed % 60;
    
    const timeString = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    document.getElementById('elapsedTime').textContent = timeString;
}

// Update elapsed time every second
setInterval(() => {
    const statusEl = document.getElementById('jobStatus');
    if (statusEl && statusEl.textContent === 'RUNNING') {
        const startedAt = document.getElementById('jobId').dataset.startedAt;
        if (startedAt) {
            updateElapsedTime(startedAt);
        }
    }
}, 1000);

// Error handling
function showError(message) {
    errorSection.style.display = 'block';
    document.getElementById('errorMessage').textContent = message;
    errorSection.scrollIntoView({ behavior: 'smooth' });
}

function hideError() {
    errorSection.style.display = 'none';
}

// Utility functions
function escapeHtml(text) {
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
