/**
 * Dashboard Application - Dark Theme
 * Displays real-time statistics, risk charts, and session replay
 */

class Dashboard {
    constructor() {
        this.riskChart = null;
        this.replayCanvas = null;
        this.replayCtx = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadDashboardStats();
        this.initReplayCanvas();
    }

    setupEventListeners() {
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadDashboardStats());
        document.getElementById('loadReplayBtn').addEventListener('click', () => this.loadSessionReplay());

        const trainBtn = document.getElementById('trainModelBtn');
        if (trainBtn) trainBtn.addEventListener('click', () => this.trainModel());
    }

    async loadDashboardStats() {
        try {
            const response = await fetch('/api/v1/dashboard/stats');
            const result = await response.json();

            if (result.success) {
                this.updateStats(result.data);
                this.updateRiskChart(result.data);
                this.updateTopUsers(result.data.top_users);
                this.updateRecentSessions(result.data.recent_sessions);
                this.updateModelStatus(result.data.model_trained);
            }
        } catch (error) {
            console.error('Error loading dashboard stats:', error);
            this.showMessage('Error loading dashboard stats', 'error');
        }
    }

    updateStats(stats) {
        this.animateValue('totalUsers', stats.total_users);
        this.animateValue('totalSessions', stats.total_sessions);
        document.getElementById('totalEvents').textContent = stats.total_events.toLocaleString();
        this.animateValue('activeSessions', stats.active_sessions);

        // Risk counts
        document.getElementById('lowRiskCount').textContent = stats.low_risk_sessions_today;
        document.getElementById('medRiskCount').textContent = stats.medium_risk_sessions_today;
        document.getElementById('highRiskCount').textContent = stats.high_risk_sessions_today;

        // Avg risk score
        const avgScore = stats.average_risk_score || 0;
        document.getElementById('avgRiskScore').textContent = avgScore.toFixed(3);

        // Color the gauge based on score
        const gaugeRing = document.getElementById('riskGaugeRing');
        if (gaugeRing) {
            gaugeRing.style.opacity = '1';
            const scoreEl = document.getElementById('avgRiskScore');
            if (avgScore < 0.5) {
                scoreEl.style.color = 'var(--success)';
            } else if (avgScore < 0.8) {
                scoreEl.style.color = 'var(--warning)';
            } else {
                scoreEl.style.color = 'var(--danger)';
            }
        }
    }

    animateValue(elementId, target) {
        const el = document.getElementById(elementId);
        if (!el) return;
        const current = parseInt(el.textContent) || 0;
        if (current === target) { el.textContent = target; return; }

        const duration = 600;
        const start = performance.now();
        const step = (now) => {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            el.textContent = Math.round(current + (target - current) * eased);
            if (progress < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    }

    updateModelStatus(isTrained) {
        const el = document.getElementById('modelStatus');
        if (!el) return;
        el.classList.remove('trained', 'untrained');
        if (isTrained) {
            el.classList.add('trained');
            el.innerHTML = '<span class="status-dot"></span> Model: Trained';
        } else {
            el.classList.add('untrained');
            el.innerHTML = '<span class="status-dot"></span> Model: Not Trained';
        }
    }

    updateRiskChart(stats) {
        const ctx = document.getElementById('riskChart').getContext('2d');

        const low = stats.low_risk_sessions_today;
        const med = stats.medium_risk_sessions_today;
        const high = stats.high_risk_sessions_today;
        const total = low + med + high;

        const data = {
            labels: ['Low Risk', 'Medium Risk', 'High Risk'],
            datasets: [{
                data: total > 0 ? [low, med, high] : [1, 0, 0],
                backgroundColor: [
                    'rgba(74, 222, 128, 0.8)',
                    'rgba(251, 191, 36, 0.8)',
                    'rgba(248, 113, 113, 0.8)'
                ],
                borderColor: [
                    'rgba(74, 222, 128, 1)',
                    'rgba(251, 191, 36, 1)',
                    'rgba(248, 113, 113, 1)'
                ],
                borderWidth: 2,
                hoverOffset: 8
            }]
        };

        if (this.riskChart) {
            this.riskChart.data = data;
            this.riskChart.update();
        } else {
            this.riskChart = new Chart(ctx, {
                type: 'doughnut',
                data: data,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '65%',
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            backgroundColor: 'rgba(26, 26, 40, 0.95)',
                            titleColor: '#fff',
                            bodyColor: 'rgba(255,255,255,0.7)',
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            cornerRadius: 8,
                            padding: 12
                        }
                    }
                }
            });
        }
    }

    updateTopUsers(users) {
        const container = document.getElementById('topUsers');
        if (!container) return;

        if (!users || users.length === 0) {
            container.innerHTML = '<div class="dash-user-empty">No users registered yet</div>';
            return;
        }

        container.innerHTML = users.map((user, i) => `
            <div class="dash-user-item">
                <div class="dash-user-rank ${i < 3 ? 'top' : ''}">${i + 1}</div>
                <div class="dash-user-name">${user.username}</div>
                <div class="dash-user-sessions">${user.session_count} sessions</div>
            </div>
        `).join('');
    }

    updateRecentSessions(sessions) {
        const container = document.getElementById('recentSessions');
        if (!container) return;

        if (!sessions || sessions.length === 0) {
            container.innerHTML = '<div class="dash-user-empty">No recent sessions</div>';
            return;
        }

        container.innerHTML = sessions.map((s) => {
            const date = new Date(s.start_time);
            const timeStr = date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            let riskColor = 'var(--text-muted)';
            if (s.risk_level === 'HIGH') riskColor = 'var(--danger)';
            else if (s.risk_level === 'MEDIUM') riskColor = 'var(--warning)';
            else if (s.risk_level === 'LOW') riskColor = 'var(--success)';

            return `
                <div class="dash-session-item" onclick="document.getElementById('replaySessionId').value='${s.session_id}'; document.getElementById('loadReplayBtn').click();">
                    <div class="dash-session-header">
                        <span class="dash-session-user">${s.username}</span>
                        <span class="dash-session-time">${timeStr}</span>
                    </div>
                    <div class="dash-session-details">
                        <span class="dash-session-id" title="${s.session_id}">${s.session_id.substring(0,8)}...</span>
                        <span class="dash-session-risk" style="color:${riskColor}">${s.risk_level || 'N/A'}</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    // Replay
    initReplayCanvas() {
        this.replayCanvas = document.getElementById('replayCanvas');
        if (!this.replayCanvas) return;
        this.replayCtx = this.replayCanvas.getContext('2d');

        const wrapper = this.replayCanvas.parentElement;
        this.replayCanvas.width = wrapper.offsetWidth;
        this.replayCanvas.height = 320;
        this.clearCanvas();
    }

    clearCanvas() {
        const ctx = this.replayCtx;
        const canvas = this.replayCanvas;
        ctx.fillStyle = '#13131d';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = 'rgba(255,255,255,0.2)';
        ctx.font = '14px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Enter a Session ID and click Load to see replay', canvas.width / 2, canvas.height / 2);
    }

    async loadSessionReplay() {
        const sessionId = document.getElementById('replaySessionId').value.trim();
        if (!sessionId) {
            this.showMessage('Please enter a session ID', 'warning');
            return;
        }

        try {
            this.showMessage('Loading session...', 'info');
            const response = await fetch(`/api/v1/sessions/${sessionId}/replay`);
            const result = await response.json();

            if (result.success) {
                this.displayReplay(result.data);
                this.showMessage('Session loaded', 'success');
            } else {
                this.showMessage(result.detail || result.error || 'Session not found', 'error');
            }
        } catch (error) {
            console.error('Error loading session replay:', error);
            this.showMessage('Error loading session replay', 'error');
        }
    }

    displayReplay(sessionData) {
        const events = sessionData.events || [];

        document.getElementById('replayEventCount').textContent = events.length.toLocaleString();
        document.getElementById('replayRiskLevel').textContent = sessionData.risk_level || 'N/A';
        document.getElementById('replayScore').textContent = sessionData.anomaly_score != null
            ? sessionData.anomaly_score.toFixed(3)
            : '—';

        // Color risk level
        const riskEl = document.getElementById('replayRiskLevel');
        riskEl.style.color = sessionData.risk_level === 'HIGH' ? 'var(--danger)' :
                             sessionData.risk_level === 'MEDIUM' ? 'var(--warning)' :
                             sessionData.risk_level === 'LOW' ? 'var(--success)' : 'var(--text-primary)';

        if (events.length > 0) {
            const startTime = events[0].timestamp;
            const endTime = events[events.length - 1].timestamp;
            const duration = ((endTime - startTime) / 1000).toFixed(1);
            document.getElementById('replayDuration').textContent = `${duration}s`;
        } else {
            document.getElementById('replayDuration').textContent = '0s';
        }

        // Draw trajectory
        this.drawMouseTrajectory(events);

        // Display Features
        this.renderFeatures(sessionData.features || {});
    }

    renderFeatures(features) {
        const container = document.getElementById('featuresExplorer');
        if (!container) return;

        // Show the container
        container.style.display = 'block';

        // Define categories based on config keys
        const mouseKeys = [
            'mouse_velocity_mean', 'mouse_velocity_std', 'mouse_velocity_max',
            'mouse_acceleration_mean', 'mouse_acceleration_std', 'mouse_acceleration_max',
            'mouse_jerk_mean', 'mouse_jerk_std', 'mouse_curvature_mean',
            'mouse_direction_changes', 'mouse_pause_count', 'mouse_click_interval_mean'
        ];
        const keyKeys = [
            'keystroke_dwell_time_mean', 'keystroke_dwell_time_std',
            'keystroke_flight_time_mean', 'keystroke_flight_time_std',
            'keystroke_typing_consistency', 'keystroke_error_rate',
            'keystroke_transition_entropy', 'keystroke_backspace_rate',
            'keystroke_correction_rate', 'keystroke_typing_speed'
        ];
        const tempNavKeys = [
            'temporal_time_of_day_score', 'temporal_session_duration',
            'temporal_activity_bursts', 'temporal_idle_time_ratio',
            'nav_page_transition_pattern', 'nav_time_per_page_mean',
            'nav_scroll_depth_mean', 'nav_scroll_velocity_mean'
        ];
        const crossKeys = [
            'cross_mouse_keyboard_coordination', 'cross_copy_paste_frequency'
        ];

        const renderList = (keys, elementId) => {
            const el = document.getElementById(elementId);
            if (!el) return;
            el.innerHTML = keys.map(k => {
                const label = k.replace(/^(mouse|keystroke|temporal|nav|cross)_/, '').replace(/_/g, ' ');
                const val = features[k];
                const displayVal = val !== undefined && val !== null ?
                                   (Number.isInteger(val) ? val : parseFloat(val).toFixed(3)) :
                                   '—';
                return `
                    <div class="feature-item" title="${k}: ${displayVal}">
                        <div class="feature-item-label">${label}</div>
                        <div class="feature-item-value">${displayVal}</div>
                    </div>
                `;
            }).join('');
        };

        renderList(mouseKeys, 'mouseFeaturesList');
        renderList(keyKeys, 'keyFeaturesList');
        renderList(tempNavKeys, 'temporalNavFeaturesList');
        renderList(crossKeys, 'crossFeaturesList');
    }

    drawMouseTrajectory(events) {
        const ctx = this.replayCtx;
        const canvas = this.replayCanvas;

        // Resize canvas
        const wrapper = canvas.parentElement;
        canvas.width = wrapper.offsetWidth;
        canvas.height = 320;

        ctx.fillStyle = '#13131d';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw subtle grid
        ctx.strokeStyle = 'rgba(255,255,255,0.03)';
        ctx.lineWidth = 1;
        for (let x = 0; x < canvas.width; x += 40) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
        }
        for (let y = 0; y < canvas.height; y += 40) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
        }

        const mouseEvents = events.filter(e => e.event_type === 'MOUSE_MOVE' || e.event_type === 'MOUSE_CLICK');

        if (mouseEvents.length === 0) {
            ctx.fillStyle = 'rgba(255,255,255,0.2)';
            ctx.font = '14px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('No mouse events in this session', canvas.width / 2, canvas.height / 2);
            return;
        }

        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        mouseEvents.forEach(e => {
            if (e.x != null) { minX = Math.min(minX, e.x); maxX = Math.max(maxX, e.x); }
            if (e.y != null) { minY = Math.min(minY, e.y); maxY = Math.max(maxY, e.y); }
        });

        const padding = 30;
        const width = maxX - minX + padding * 2;
        const height = maxY - minY + padding * 2;
        const scaleX = (x) => ((x - minX + padding) / width) * canvas.width;
        const scaleY = (y) => ((y - minY + padding) / height) * canvas.height;

        // Trail with gradient
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(96, 165, 250, 0.5)';
        ctx.lineWidth = 1.5;
        ctx.lineJoin = 'round';

        let started = false;
        mouseEvents.forEach(e => {
            if (e.x != null && e.y != null) {
                const x = scaleX(e.x), y = scaleY(e.y);
                if (!started) { ctx.moveTo(x, y); started = true; }
                else ctx.lineTo(x, y);
            }
        });
        ctx.stroke();

        // Clicks
        mouseEvents.forEach(e => {
            if (e.event_type === 'MOUSE_CLICK' && e.x != null) {
                const x = scaleX(e.x), y = scaleY(e.y);
                ctx.beginPath(); ctx.arc(x, y, 6, 0, 2 * Math.PI);
                ctx.fillStyle = 'rgba(248, 113, 113, 0.7)';
                ctx.fill();
                ctx.strokeStyle = 'rgba(248, 113, 113, 1)';
                ctx.lineWidth = 1.5;
                ctx.stroke();
            }
        });

        // Start / End markers
        const first = mouseEvents.find(e => e.x != null);
        const last = [...mouseEvents].reverse().find(e => e.x != null);

        if (first) {
            const sx = scaleX(first.x), sy = scaleY(first.y);
            ctx.beginPath(); ctx.arc(sx, sy, 8, 0, 2 * Math.PI);
            ctx.fillStyle = 'rgba(74, 222, 128, 0.8)'; ctx.fill();
            ctx.fillStyle = '#fff'; ctx.font = 'bold 10px Inter'; ctx.textAlign = 'center';
            ctx.fillText('S', sx, sy + 3.5);
        }
        if (last) {
            const ex = scaleX(last.x), ey = scaleY(last.y);
            ctx.beginPath(); ctx.arc(ex, ey, 8, 0, 2 * Math.PI);
            ctx.fillStyle = 'rgba(96, 165, 250, 0.8)'; ctx.fill();
            ctx.fillStyle = '#fff'; ctx.font = 'bold 10px Inter'; ctx.textAlign = 'center';
            ctx.fillText('E', ex, ey + 3.5);
        }
    }

    async trainModel() {
        const userId = sessionStorage.getItem('userId');
        if (!userId) { this.showMessage('Please login first', 'warning'); return; }

        const btn = document.getElementById('trainModelBtn');
        btn.textContent = 'Training...';
        btn.disabled = true;

        try {
            const response = await fetch('/api/v1/model/train', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: parseInt(userId), min_samples: 10 })
            });
            const result = await response.json();

            if (result.success && result.data.success) {
                this.showMessage(`Model trained with ${result.data.samples_used} samples`, 'success');
                this.loadDashboardStats();
            } else {
                this.showMessage(result.data?.detail || result.data?.message || 'Training failed', 'error');
            }
        } catch (error) {
            this.showMessage('Error training model', 'error');
        }

        btn.textContent = 'Train Model';
        btn.disabled = false;
    }

    showMessage(message, type) {
        const container = document.getElementById('messageContainer');
        if (!container) return;
        const div = document.createElement('div');
        div.className = `alert alert-${type}`;
        div.textContent = message;
        container.appendChild(div);
        setTimeout(() => div.remove(), 4000);
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new Dashboard();
});
