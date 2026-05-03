document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const uploadBox = document.getElementById('upload-box');
    const fileInput = document.getElementById('video-upload');
    const loadingState = document.getElementById('loading-state');
    const resultsSection = document.getElementById('results-section');
    const setupSection = document.getElementById('setup-section');
    const zoneDrawingContainer = document.getElementById('zone-drawing-container');
    
    // Canvas Elements
    const canvas = document.getElementById('drawing-canvas');
    const ctx = canvas.getContext('2d');
    const previewVideo = document.getElementById('preview-video');
    const btnCompleteZone = document.getElementById('btn-complete-zone');
    const btnClearZones = document.getElementById('btn-clear-zones');
    const btnStartProcessing = document.getElementById('btn-start-processing');
    const zoneNameInput = document.getElementById('zone-name');
    const zoneRestrictedInput = document.getElementById('zone-restricted');
    const drawnZonesList = document.getElementById('drawn-zones-list');
    const btnExportPdf = document.getElementById('btn-export-pdf');
    
    // State
    let selectedFile = null;
    let customZones = [];
    let currentPoints = [];
    let charts = {};
    let analyticsData = null;

    // --- Drag & Drop ---
    uploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadBox.classList.add('dragover');
    });
    
    uploadBox.addEventListener('dragleave', () => {
        uploadBox.classList.remove('dragover');
    });
    
    uploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadBox.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelection(e.target.files[0]);
        }
    });
    
    function handleFileSelection(file) {
        if (!file.type.startsWith('video/')) {
            showToast('Please upload a valid video file.', 'error');
            return;
        }
        selectedFile = file;
        
        // Hide upload box, show drawing UI
        uploadBox.classList.add('hidden');
        zoneDrawingContainer.classList.remove('hidden');
        
        // Load video into hidden element to grab a frame
        const url = URL.createObjectURL(file);
        previewVideo.src = url;
        previewVideo.onloadeddata = () => {
            // Seek to 1 second to grab a good frame
            previewVideo.currentTime = 1;
        };
        previewVideo.onseeked = () => {
            // Setup canvas size based on video
            canvas.width = previewVideo.videoWidth;
            canvas.height = previewVideo.videoHeight;
            redrawCanvas();
        };
    }

    // --- Canvas Drawing Logic ---
    canvas.addEventListener('click', (e) => {
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        
        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;
        
        currentPoints.push([Math.round(x), Math.round(y)]);
        redrawCanvas();
    });

    btnCompleteZone.addEventListener('click', () => {
        if (currentPoints.length < 3) {
            showToast('A zone needs at least 3 points.', 'warning');
            return;
        }
        
        const name = zoneNameInput.value.trim() || `Zone ${customZones.length + 1}`;
        const isRestricted = zoneRestrictedInput.checked;
        
        customZones.push({
            name: name,
            points: currentPoints,
            is_restricted: isRestricted
        });
        
        currentPoints = [];
        zoneNameInput.value = '';
        zoneRestrictedInput.checked = false;
        updateZonesList();
        redrawCanvas();
    });

    btnClearZones.addEventListener('click', () => {
        customZones = [];
        currentPoints = [];
        updateZonesList();
        redrawCanvas();
    });

    function redrawCanvas() {
        if (!previewVideo.videoWidth) return;
        
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(previewVideo, 0, 0, canvas.width, canvas.height);
        
        // Draw saved zones
        customZones.forEach((zone, idx) => {
            drawPolygon(zone.points, 'rgba(59, 130, 246, 0.4)', '#3b82f6', zone.name);
        });
        
        // Draw current polygon
        if (currentPoints.length > 0) {
            drawPolygon(currentPoints, 'rgba(167, 139, 250, 0.4)', '#a78bfa', '', false);
        }
    }

    function drawPolygon(points, fillColor, strokeColor, label, isClosed = true) {
        if (points.length === 0) return;
        
        ctx.beginPath();
        ctx.moveTo(points[0][0], points[0][1]);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i][0], points[i][1]);
        }
        if (isClosed) ctx.closePath();
        
        ctx.fillStyle = fillColor;
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = strokeColor;
        ctx.stroke();
        
        // Draw points
        ctx.fillStyle = '#fff';
        points.forEach(p => {
            ctx.beginPath();
            ctx.arc(p[0], p[1], 4, 0, 2 * Math.PI);
            ctx.fill();
        });

        // Draw Label
        if (label) {
            const minX = Math.min(...points.map(p => p[0]));
            const minY = Math.min(...points.map(p => p[1]));
            ctx.fillStyle = '#fff';
            ctx.font = '20px Inter';
            ctx.fillText(label, minX + 10, minY + 30);
        }
    }

    function updateZonesList() {
        drawnZonesList.innerHTML = '';
        customZones.forEach(zone => {
            const li = document.createElement('li');
            li.className = 'zone-badge';
            li.innerHTML = zone.name + (zone.is_restricted ? ' <span class="badge-restricted">RESTRICTED</span>' : '');
            drawnZonesList.appendChild(li);
        });
    }

    // --- Processing ---
    btnStartProcessing.addEventListener('click', () => {
        if (!selectedFile) return;
        
        zoneDrawingContainer.classList.add('hidden');
        loadingState.classList.remove('hidden');
        
        const formData = new FormData();
        formData.append('video', selectedFile);
        
        // Send custom zones if drawn, else backend uses defaults
        if (customZones.length > 0) {
            formData.append('zones', JSON.stringify(customZones));
        }
        
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showToast('Error: ' + data.error, 'error');
                resetUpload();
                return;
            }
            analyticsData = data;
            displayResults(data);
        })
        .catch(err => {
            showToast('An error occurred during processing.', 'error');
            console.error(err);
            resetUpload();
        });
    });

    function resetUpload() {
        uploadBox.classList.remove('hidden');
        zoneDrawingContainer.classList.add('hidden');
        loadingState.classList.add('hidden');
        selectedFile = null;
        fileInput.value = '';
    }

    // --- Results & Charts ---
    function displayResults(data) {
        setupSection.classList.add('hidden');
        resultsSection.classList.remove('hidden');
        
        // Media
        document.getElementById('result-video').src = data.video_url;
        document.getElementById('result-heatmap').src = data.heatmap_url;
        
        // Dashboard Stats
        const statsGrid = document.getElementById('stats-grid');
        statsGrid.innerHTML = '';
        
        const zones = data.analytics.zones;
        
        const defaultColors = [
            'rgb(59, 130, 246)', // blue
            'rgb(167, 139, 250)', // purple
            'rgb(16, 185, 129)', // green
            'rgb(245, 158, 11)'  // yellow
        ];
        let colorIdx = 0;
        
        for (const [zoneName, stats] of Object.entries(zones)) {
            let color = defaultColors[colorIdx % defaultColors.length];
            if (stats.color_bgr) {
                color = `rgb(${stats.color_bgr[2]}, ${stats.color_bgr[1]}, ${stats.color_bgr[0]})`;
            }
            stats._displayColor = color; // Save for chart rendering later
            colorIdx++;
            
            const card = document.createElement('div');
            card.className = 'stat-card glass-panel';
            
            card.innerHTML = `
                <h4><span class="color-dot" style="background-color: ${color}"></span> ${zoneName}</h4>
                <div class="stat-row">
                    <span>Unique Visitors:</span>
                    <span class="stat-val" data-target="${stats.total_unique_visitors}">0</span>
                </div>
                <div class="stat-row">
                    <span>Entries / Exits:</span>
                    <span class="stat-val">${stats.entries} / ${stats.exits}</span>
                </div>
                <div class="stat-row">
                    <span>Avg Dwell Time:</span>
                    <span class="stat-val" data-target="${stats.average_dwell_time_sec}">0</span>s
                </div>
                <div class="stat-row">
                    <span>Peak Occupancy:</span>
                    <span class="stat-val" data-target="${stats.peak_occupancy}">0</span>
                </div>
            `;
            statsGrid.appendChild(card);
        }
        
        // Animate numbers
        document.querySelectorAll('.stat-val[data-target]').forEach(el => {
            animateValue(el, 0, parseFloat(el.getAttribute('data-target')), 1500);
        });
        
        // Transitions
        const transitionsList = document.getElementById('transitions-list');
        transitionsList.innerHTML = '';
        const transitions = data.analytics.transitions || {};
        
        if (Object.keys(transitions).length === 0) {
            transitionsList.innerHTML = '<li>No transitions recorded.</li>';
        } else {
            for (const [path, count] of Object.entries(transitions)) {
                const li = document.createElement('li');
                li.innerHTML = `${path} <span>${count}</span>`;
                transitionsList.appendChild(li);
            }
        }

        // Render Chart.js
        renderCharts(data.analytics);
        
        // Simulate real-time alerts by reading frame_log
        simulateRealTimeAlerts(data.analytics.frame_log, data.analytics.video_info.fps);
    }

    function renderCharts(analytics) {
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = 'Inter';
        
        const frameLog = analytics.frame_log || [];
        const zones = analytics.zones;
        
        // 1. Occupancy Over Time (Line)
        const occCtx = document.getElementById('occupancyChart').getContext('2d');
        
        const timeLabels = frameLog.filter((_, i) => i % Math.round(analytics.video_info.fps) === 0).map(l => l.timestamp_sec.toFixed(0) + 's');
        const datasets = [];
        
        for (const [zoneName, stats] of Object.entries(zones)) {
            const key = stats.zone_key;
            const color = stats._displayColor || 'rgb(59, 130, 246)'; // fallback if missing
            
            const dataPts = frameLog.filter((_, i) => i % Math.round(analytics.video_info.fps) === 0).map(l => l[`zone_${key}_count`]);
            
            datasets.push({
                label: zoneName.split(' - ')[0],
                data: dataPts,
                borderColor: color,
                backgroundColor: color.replace('rgb', 'rgba').replace(')', ', 0.1)'),
                fill: true,
                tension: 0.4
            });
        }
        
        charts.occupancy = new Chart(occCtx, {
            type: 'line',
            data: { labels: timeLabels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { position: 'bottom' } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                    x: { grid: { display: false } }
                }
            }
        });

        // 2. Zone Distribution (Pie)
        const distCtx = document.getElementById('distributionChart').getContext('2d');
        const distLabels = [];
        const distData = [];
        const distColors = [];
        
        for (const [zoneName, stats] of Object.entries(zones)) {
            distLabels.push(zoneName.split(' - ')[0]);
            distData.push(stats.total_unique_visitors);
            distColors.push(stats._displayColor || 'rgb(59, 130, 246)');
        }
        
        charts.distribution = new Chart(distCtx, {
            type: 'doughnut',
            data: {
                labels: distLabels,
                datasets: [{
                    data: distData,
                    backgroundColor: distColors,
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' } },
                cutout: '60%'
            }
        });

        // 3. Average Dwell Time (Bar)
        const dwellCtx = document.getElementById('dwellTimeChart').getContext('2d');
        const dwellData = [];
        
        for (const [zoneName, stats] of Object.entries(zones)) {
            dwellData.push(stats.average_dwell_time_sec);
        }

        charts.dwell = new Chart(dwellCtx, {
            type: 'bar',
            data: {
                labels: distLabels,
                datasets: [{
                    label: 'Seconds',
                    data: dwellData,
                    backgroundColor: distColors,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    function simulateRealTimeAlerts(frameLog, fps) {
        if (!frameLog || frameLog.length === 0) return;
        
        const video = document.getElementById('result-video');
        let currentFrameIndex = 0;
        let lastAlertedZones = new Set();
        let lastAlertedLoiterers = new Set();
        
        video.addEventListener('timeupdate', () => {
            const currentTime = video.currentTime;
            
            // Find frame log entry matching current time
            const targetFrame = frameLog.find(log => log.timestamp_sec >= currentTime);
            if (!targetFrame || !targetFrame.alerts) return;
            
            const alerts = targetFrame.alerts;
            
            // Overcrowding
            alerts.overcrowding.forEach(zoneKey => {
                if (!lastAlertedZones.has(zoneKey)) {
                    showToast(`⚠️ OVERCROWDING: Zone ${zoneKey} has exceeded capacity!`, 'error');
                    lastAlertedZones.add(zoneKey);
                    
                    // Reset alert after 5 seconds to allow it to fire again if needed
                    setTimeout(() => lastAlertedZones.delete(zoneKey), 5000);
                }
            });
            
            // Loitering
            alerts.loitering.forEach(tid => {
                if (!lastAlertedLoiterers.has(tid)) {
                    showToast(`⚠️ SECURITY: Person ID:${tid} is loitering!`, 'warning');
                    lastAlertedLoiterers.add(tid);
                    setTimeout(() => lastAlertedLoiterers.delete(tid), 5000);
                }
            });
            
            // Intrusion
            if (alerts.intrusion) {
                alerts.intrusion.forEach(alertData => {
                    // Assuming backend sends: [track_id, zone_key, zone_name]
                    const tid = alertData[0];
                    const zName = alertData[2];
                    const alertKey = `int-${tid}-${zName}`;
                    
                    if (!lastAlertedLoiterers.has(alertKey)) {
                        showToast(`🚨 INTRUSION: Person ID:${tid} entered restricted area: ${zName}!`, 'error');
                        lastAlertedLoiterers.add(alertKey);
                        setTimeout(() => lastAlertedLoiterers.delete(alertKey), 5000);
                    }
                });
            }
        });
    }

    function showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const icon = type === 'error' ? '🔴' : '🟡';
        toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
        
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('fadeOut');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    function animateValue(obj, start, end, duration) {
        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            obj.innerHTML = (progress * (end - start) + start).toFixed(Number.isInteger(end) ? 0 : 2);
            if (progress < 1) {
                window.requestAnimationFrame(step);
            }
        };
        window.requestAnimationFrame(step);
    }

    // PDF Export
    btnExportPdf.addEventListener('click', () => {
        const element = document.getElementById('pdf-content');
        const opt = {
            margin:       10,
            filename:     'Analytics_Report.pdf',
            image:        { type: 'jpeg', quality: 0.98 },
            html2canvas:  { scale: 2, useCORS: true, logging: false },
            jsPDF:        { unit: 'mm', format: 'a4', orientation: 'landscape' }
        };
        
        // Add a temporary solid background for PDF (glassmorphism looks bad printed)
        const originalBg = element.style.background;
        element.style.background = '#0f172a';
        
        html2pdf().set(opt).from(element).save().then(() => {
            element.style.background = originalBg;
        });
    });
});
