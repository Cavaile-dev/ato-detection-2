/**
 * Dashboard Application - Dark Theme
 * Displays real-time statistics, risk charts, and session replay
 */

const FEATURE_COLUMNS = [
    'mouse_velocity_mean', 'mouse_velocity_std', 'mouse_velocity_max',
    'mouse_acceleration_mean', 'mouse_acceleration_std', 'mouse_acceleration_max',
    'mouse_jerk_mean', 'mouse_jerk_std', 'mouse_curvature_mean',
    'mouse_direction_changes', 'mouse_pause_count', 'mouse_click_interval_mean',
    'keystroke_dwell_time_mean', 'keystroke_dwell_time_std', 'keystroke_flight_time_mean',
    'keystroke_flight_time_std', 'keystroke_typing_consistency', 'keystroke_error_rate',
    'keystroke_transition_entropy', 'keystroke_backspace_rate', 'keystroke_correction_rate',
    'keystroke_typing_speed', 'temporal_time_of_day_score', 'temporal_session_duration',
    'temporal_activity_bursts', 'temporal_idle_time_ratio', 'nav_page_transition_pattern',
    'nav_time_per_page_mean', 'nav_scroll_depth_mean', 'nav_scroll_velocity_mean',
    'cross_mouse_keyboard_coordination', 'cross_copy_paste_frequency'
];
const MOUSE_FEATURES = FEATURE_COLUMNS.filter((feature) => feature.startsWith('mouse_'));
const KEYBOARD_FEATURES = FEATURE_COLUMNS.filter((feature) => feature.startsWith('keystroke_'));
const APP_TIMEZONE = 'Asia/Jakarta';

function formatJakartaTime(value) {
    if (!value) return 'N/A';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleTimeString('id-ID', {
        timeZone: APP_TIMEZONE,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

class Dashboard {
    constructor() {
        this.riskChart = null;
        this.replayCanvas = null;
        this.replayCtx = null;
        this.users = [];
        this.modelOptions = [];
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.initTrainingConfigurator();
        this.loadReassessModelOptions();
        this.loadDashboardStats();
        this.initReplayCanvas();
    }

    setupEventListeners() {
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadDashboardStats());
        document.getElementById('loadReplayBtn').addEventListener('click', () => this.loadSessionReplay());
        document.getElementById('reassessBtn')?.addEventListener('click', () => this.reassessSession());

        const trainBtn = document.getElementById('trainModelBtn');
        if (trainBtn) trainBtn.addEventListener('click', () => this.openTrainModal());
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
            if (avgScore < 0) {
                scoreEl.style.color = 'var(--danger)';
            } else if (avgScore <= 0.5) {
                scoreEl.style.color = 'var(--warning)';
            } else {
                scoreEl.style.color = 'var(--success)';
            }
        }

        const legend = document.querySelector('.risk-gauge-legend');
        if (legend) {
            legend.innerHTML = `
                <span class="legend-item"><span class="risk-dot risk-dot-low"></span> > 0.5 Low</span>
                <span class="legend-item"><span class="risk-dot risk-dot-medium"></span> 0.0 to 0.5 Medium</span>
                <span class="legend-item"><span class="risk-dot risk-dot-high"></span> < 0.0 High</span>
            `;
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
            const timeStr = formatJakartaTime(s.start_time);
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

    initTrainingConfigurator() {
        this.renderFeatureOptions();
        this.updateSelectedFeatureCount();

        document.getElementById('closeTrainModalBtn')?.addEventListener('click', () => this.closeTrainModal());
        document.getElementById('cancelTrainBtn')?.addEventListener('click', () => this.closeTrainModal());
        document.getElementById('confirmTrainBtn')?.addEventListener('click', () => this.trainModelFromConfig());

        document.getElementById('trainScopeSelect')?.addEventListener('change', () => this.handleScopeChange());
        document.getElementById('selectAllFeaturesBtn')?.addEventListener('click', () => this.setAllFeatures(true));
        document.getElementById('clearAllFeaturesBtn')?.addEventListener('click', () => this.setAllFeatures(false));
        document.getElementById('presetMouseOnlyBtn')?.addEventListener('click', () => this.applyFeaturePreset('mouse'));
        document.getElementById('presetKeyboardOnlyBtn')?.addEventListener('click', () => this.applyFeaturePreset('keyboard'));
        document.getElementById('trainFeatureList')?.addEventListener('change', () => this.updateSelectedFeatureCount());

        const modal = document.getElementById('trainConfigModal');
        modal?.addEventListener('click', (e) => {
            if (e.target === modal) this.closeTrainModal();
        });
    }

    async openTrainModal() {
        await this.loadUsersForTraining();
        this.handleScopeChange();
        this.updateSelectedFeatureCount();
        const modal = document.getElementById('trainConfigModal');
        if (modal) modal.style.display = 'flex';
    }

    closeTrainModal() {
        const modal = document.getElementById('trainConfigModal');
        if (modal) modal.style.display = 'none';
    }

    renderFeatureOptions() {
        const container = document.getElementById('trainFeatureList');
        if (!container) return;

        container.innerHTML = FEATURE_COLUMNS.map((feature) => `
            <label class="feature-checkbox">
                <input type="checkbox" class="train-feature-checkbox" value="${feature}" checked>
                <span>${feature}</span>
            </label>
        `).join('');
    }

    updateSelectedFeatureCount() {
        const selectedCount = document.querySelectorAll('.train-feature-checkbox:checked').length;
        const totalCount = FEATURE_COLUMNS.length;
        const el = document.getElementById('selectedFeatureCount');
        if (el) el.textContent = `${selectedCount}/${totalCount} selected`;
    }

    setAllFeatures(checked) {
        document.querySelectorAll('.train-feature-checkbox').forEach((cb) => {
            cb.checked = checked;
        });
        this.updateSelectedFeatureCount();
    }

    applyFeaturePreset(preset) {
        const target = new Set(
            preset === 'mouse'
                ? MOUSE_FEATURES
                : preset === 'keyboard'
                    ? KEYBOARD_FEATURES
                    : FEATURE_COLUMNS
        );

        document.querySelectorAll('.train-feature-checkbox').forEach((cb) => {
            cb.checked = target.has(cb.value);
        });

        this.updateSelectedFeatureCount();
    }

    handleScopeChange() {
        const scope = document.getElementById('trainScopeSelect')?.value || 'global';
        const userWrap = document.getElementById('trainUserWrap');
        if (userWrap) userWrap.style.display = scope === 'personal' ? 'block' : 'none';
    }

    async loadUsersForTraining() {
        const select = document.getElementById('trainUserSelect');
        if (!select) return;

        try {
            const response = await fetch('/api/v1/users');
            const result = await response.json();
            this.users = result.success && result.data?.users ? result.data.users : [];

            if (this.users.length === 0) {
                select.innerHTML = '<option value="">No users available</option>';
                return;
            }

            select.innerHTML = this.users.map((u) => (
                `<option value="${u.id}">${u.username} (valid train: ${u.train_valid_sessions ?? 0})</option>`
            )).join('');
        } catch (error) {
            console.error('Error loading users:', error);
            select.innerHTML = '<option value="">Failed to load users</option>';
        }
    }

    async loadReassessModelOptions() {
        const select = document.getElementById('reassessModelSelect');
        if (!select) return;

        const previousValue = select.value;

        try {
            const response = await fetch('/api/v1/models/options');
            const result = await response.json();

            const options = result.success && result.data?.options
                ? result.data.options
                : [{ value: 'global', label: 'Global Model', scope: 'global', user_id: null }];

            this.modelOptions = options;
            select.innerHTML = options.map((opt) => (
                `<option value="${opt.value}">${opt.label}</option>`
            )).join('');

            if (previousValue && options.some((opt) => opt.value === previousValue)) {
                select.value = previousValue;
            } else {
                select.value = 'global';
            }
        } catch (error) {
            console.error('Error loading model options:', error);
            select.innerHTML = '<option value="global">Global Model</option>';
            select.value = 'global';
        }
    }

    buildReassessPayload() {
        const select = document.getElementById('reassessModelSelect');
        const value = select?.value || 'global';

        if (value === 'global') {
            return { model_scope: 'global' };
        }

        if (value.startsWith('personal:')) {
            const userId = parseInt(value.split(':')[1], 10);
            return { model_scope: 'personal', model_user_id: userId };
        }

        return { model_scope: 'global' };
    }

    getRiskLevelRank(level) {
        const rank = { LOW: 1, MEDIUM: 2, HIGH: 3 };
        return rank[level] || 0;
    }

    buildReassessNotification(previousRisk, newRisk, modelLabel) {
        if (!newRisk && !previousRisk) {
            return {
                text: `Risk reassessed using ${modelLabel} and saved to database`,
                type: 'success'
            };
        }

        if (!previousRisk && newRisk) {
            return {
                text: `Risk set to ${newRisk} (${modelLabel})`,
                type: 'success'
            };
        }

        if (!newRisk) {
            return {
                text: `Risk reassessed using ${modelLabel} and saved to database`,
                type: 'success'
            };
        }

        if (previousRisk === newRisk) {
            return {
                text: `Risk unchanged: ${newRisk} (${modelLabel})`,
                type: 'info'
            };
        }

        const isRiskIncreasing = this.getRiskLevelRank(newRisk) > this.getRiskLevelRank(previousRisk);
        return {
            text: `Risk changed: ${previousRisk} -> ${newRisk} (${modelLabel})`,
            type: isRiskIncreasing ? 'warning' : 'success'
        };
    }

    resetRiskChangeIndicator() {
        const container = document.getElementById('riskChangeIndicator');
        const badgeEl = document.getElementById('riskChangeBadge');
        const textEl = document.getElementById('riskChangeText');
        if (!container || !badgeEl || !textEl) return;

        container.style.display = 'none';
        container.classList.remove('risk-change-up', 'risk-change-down', 'risk-change-same');
        container.classList.add('risk-change-neutral');
        badgeEl.textContent = 'UNCHANGED';
        textEl.textContent = '';
    }

    updateRiskChangeIndicator(previousRisk, newRisk, modelLabel) {
        const container = document.getElementById('riskChangeIndicator');
        const badgeEl = document.getElementById('riskChangeBadge');
        const textEl = document.getElementById('riskChangeText');
        if (!container || !badgeEl || !textEl) return;

        const clearClasses = () => {
            container.classList.remove('risk-change-up', 'risk-change-down', 'risk-change-same', 'risk-change-neutral');
        };

        if (!previousRisk && !newRisk) {
            this.resetRiskChangeIndicator();
            return;
        }

        container.style.display = 'flex';

        if (!previousRisk && newRisk) {
            clearClasses();
            container.classList.add('risk-change-same');
            badgeEl.textContent = 'RISK SET';
            textEl.textContent = `Risk sekarang ${newRisk} (model: ${modelLabel}).`;
            return;
        }

        if (previousRisk === newRisk) {
            clearClasses();
            container.classList.add('risk-change-same');
            badgeEl.textContent = 'UNCHANGED';
            textEl.textContent = `Risk tetap ${newRisk} setelah reassessment (${modelLabel}).`;
            return;
        }

        const isRiskIncreasing = this.getRiskLevelRank(newRisk) > this.getRiskLevelRank(previousRisk);
        clearClasses();
        container.classList.add(isRiskIncreasing ? 'risk-change-up' : 'risk-change-down');
        badgeEl.textContent = isRiskIncreasing ? 'RISK UP' : 'RISK DOWN';
        textEl.textContent = `Risk berubah ${previousRisk} -> ${newRisk} menggunakan ${modelLabel}.`;
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

    async loadSessionReplay(options = {}) {
        const { silent = false, preserveRiskIndicator = false } = options;
        const sessionId = document.getElementById('replaySessionId').value.trim();

        if (!preserveRiskIndicator) {
            this.resetRiskChangeIndicator();
        }

        if (!sessionId) {
            if (!silent) this.showMessage('Please enter a session ID', 'warning');
            return;
        }

        try {
            if (!silent) this.showMessage('Loading session...', 'info');
            const response = await fetch(`/api/v1/sessions/${sessionId}/replay`);
            const result = await response.json();

            if (result.success) {
                this.displayReplay(result.data);
                if (!silent) this.showMessage('Session loaded', 'success');
            } else {
                this.showMessage(result.detail || result.error || 'Session not found', 'error');
            }
        } catch (error) {
            console.error('Error loading session replay:', error);
            this.showMessage('Error loading session replay', 'error');
        }
    }

    async reassessSession() {
        const sessionId = document.getElementById('replaySessionId').value.trim();
        if (!sessionId) {
            this.showMessage('Enter a session ID first', 'warning');
            return;
        }

        const payload = this.buildReassessPayload();
        const btn = document.getElementById('reassessBtn');
        const modelSelect = document.getElementById('reassessModelSelect');
        const selectedLabel = modelSelect?.options?.[modelSelect.selectedIndex]?.text || payload.model_scope;

        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Predicting...';
        }

        try {
            const response = await fetch(`/api/v1/sessions/${sessionId}/reassess`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();

            if (result.success) {
                const data = result.data || {};
                const previousRisk = data.previous_risk_level || null;
                const newRisk = data.new_risk_level || data.assessment?.risk_level || null;
                const notification = this.buildReassessNotification(previousRisk, newRisk, selectedLabel);
                this.showMessage(notification.text, notification.type);
                this.updateRiskChangeIndicator(previousRisk, newRisk, selectedLabel);
                await this.loadSessionReplay({ silent: true, preserveRiskIndicator: true });
                this.loadDashboardStats();
            } else {
                this.showMessage(result.detail || result.error || 'Reassessment failed', 'error');
            }
        } catch (error) {
            console.error('Error reassessing session:', error);
            this.showMessage('Error reassessing session', 'error');
        }

        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Predict Risk Again';
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

    async trainModelFromConfig() {
        const scope = document.getElementById('trainScopeSelect')?.value || 'global';
        const selectedFeatures = Array.from(document.querySelectorAll('.train-feature-checkbox:checked'))
            .map((el) => el.value);

        if (selectedFeatures.length === 0) {
            this.showMessage('Select at least one feature', 'warning');
            return;
        }

        const minSamplesRaw = document.getElementById('trainMinSamples')?.value || '10';
        const minSamples = Math.max(1, parseInt(minSamplesRaw, 10) || 10);

        let userId = null;
        if (scope === 'personal') {
            const selectedUser = document.getElementById('trainUserSelect')?.value;
            if (!selectedUser) {
                this.showMessage('Please select a user for personal model training', 'warning');
                return;
            }
            userId = parseInt(selectedUser, 10);
        }

        const trainBtn = document.getElementById('trainModelBtn');
        const confirmBtn = document.getElementById('confirmTrainBtn');
        if (trainBtn) {
            trainBtn.textContent = 'Training...';
            trainBtn.disabled = true;
        }
        if (confirmBtn) {
            confirmBtn.textContent = 'Training...';
            confirmBtn.disabled = true;
        }

        try {
            const payload = {
                scope: scope,
                user_id: userId,
                selected_features: selectedFeatures,
                min_samples: minSamples
            };

            const response = await fetch('/api/v1/model/train', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();

            if (result.success && result.data.success) {
                this.showMessage(
                    `${scope === 'global' ? 'Global' : 'Personal'} model trained with ${result.data.samples_used} samples and ${result.data.feature_count} features`,
                    'success'
                );
                this.closeTrainModal();
                this.loadReassessModelOptions();
                this.loadDashboardStats();
            } else {
                this.showMessage(result.data?.detail || result.data?.message || 'Training failed', 'error');
            }
        } catch (error) {
            console.error('Error training model:', error);
            this.showMessage('Error training model', 'error');
        }

        if (trainBtn) {
            trainBtn.textContent = 'Train Model';
            trainBtn.disabled = false;
        }
        if (confirmBtn) {
            confirmBtn.textContent = 'Start Training';
            confirmBtn.disabled = false;
        }
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
