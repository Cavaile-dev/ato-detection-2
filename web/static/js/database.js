class DatabaseManager {
    constructor() {
        this.init();
    }

    init() {
        // Setup top nav
        const sessionId = sessionStorage.getItem('sessionId');
        const userId = sessionStorage.getItem('userId');
        const username = sessionStorage.getItem('username');

        if (!sessionId || !userId) {
            window.location.href = '/';
            return;
        }
        
        const navUser = document.getElementById('navUsername');
        if (navUser && username) {
            navUser.textContent = username;
        }

        // Setup buttons
        document.getElementById('logoutBtn').addEventListener('click', () => {
            sessionStorage.clear();
            window.location.href = '/';
        });

        document.getElementById('refreshDbBtn').addEventListener('click', () => {
            this.loadSessions();
        });

        // Load data
        this.sessions = [];
        this.loadSessions();

        const searchInput = document.getElementById('dbSearch');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                const term = e.target.value.toLowerCase();
                const filtered = this.sessions.filter(s => {
                    const statusText = s.end_time ? 'completed' : 'active';
                    const searchStr = `${s.session_id} ${s.username} ${s.risk_level} ${s.start_time} ${statusText}`.toLowerCase();
                    return searchStr.includes(term);
                });
                this.renderSessions(filtered);
            });
        }
    }

    async loadSessions() {
        const tbody = document.getElementById('dbTableBody');
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Loading data...</td></tr>';

        try {
            const response = await fetch('/api/v1/sessions');
            const result = await response.json();

            if (result.success && result.data.sessions) {
                this.sessions = result.data.sessions;
                this.renderSessions(this.sessions);
            } else {
                tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Failed to load sessions.</td></tr>';
            }
        } catch (error) {
            console.error('Error loading sessions:', error);
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Error loading sessions.</td></tr>';
        }
    }

    renderSessions(sessions) {
        const tbody = document.getElementById('dbTableBody');
        
        if (sessions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No sessions found in database.</td></tr>';
            return;
        }

        tbody.innerHTML = sessions.map(s => {
            const date = new Date(s.start_time).toLocaleString();
            let riskColor = 'var(--text-muted)';
            if (s.risk_level === 'HIGH') riskColor = 'var(--danger)';
            else if (s.risk_level === 'MEDIUM') riskColor = 'var(--warning)';
            else if (s.risk_level === 'LOW') riskColor = 'var(--success)';

            const score = s.anomaly_score !== null ? parseFloat(s.anomaly_score).toFixed(3) : '—';
            const risk = s.risk_level || '—';
            
            const isActive = !s.end_time;
            const statusHtml = isActive 
                ? '<span style="color: var(--success); font-weight: 600; display: flex; align-items: center; gap: 4px;"><span style="width: 8px; height: 8px; background: var(--success); border-radius: 50%; box-shadow: 0 0 8px var(--success); animation: pulse 2s infinite;"></span> Active</span>'
                : '<span style="color: var(--text-muted);">Completed</span>';

            return `
                <tr>
                    <td class="mono">${s.session_id}</td>
                    <td>${s.username}</td>
                    <td>${date}</td>
                    <td>${s.event_count}</td>
                    <td>${statusHtml}</td>
                    <td style="color: ${riskColor}; font-weight: 600;">${risk}</td>
                    <td>${score}</td>
                    <td style="display: flex; gap: 8px;">
                        <button class="btn btn-ghost btn-sm" onclick="dbManager.showDetail('${s.session_id}')" style="padding: 4px 12px; font-size: 12px; border: 1px solid var(--border-subtle);">Detail</button>
                        ${isActive ? `<button class="btn btn-warning btn-sm" onclick="dbManager.forceEndSession('${s.session_id}')" style="padding: 4px 12px; font-size: 12px; border: 1px solid var(--warning); background: transparent; color: var(--warning);">Force End</button>` : ''}
                        <button class="btn-delete" onclick="dbManager.deleteSession('${s.session_id}')">Delete</button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    async forceEndSession(sessionId) {
        if (!confirm('Are you sure you want to force end this session? This will finalize its data and status.')) {
            return;
        }

        try {
            const response = await fetch(`/api/v1/sessions/${sessionId}/end`, {
                method: 'POST'
            });
            const result = await response.json();

            if (result.success) {
                this.loadSessions();
            } else {
                alert('Failed to force end session: ' + (result.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error force ending session:', error);
            alert('An error occurred while force ending the session.');
        }
    }

    async deleteSession(sessionId) {
        if (!confirm('Are you sure you want to delete this session? All raw events and features will be permanently deleted.')) {
            return;
        }

        try {
            const response = await fetch(`/api/v1/sessions/${sessionId}`, {
                method: 'DELETE'
            });
            const result = await response.json();

            if (result.success) {
                this.showMessage('Session deleted successfully', 'success');
                this.loadSessions();
            } else {
                this.showMessage(result.detail || 'Failed to delete session', 'error');
            }
        } catch (error) {
            console.error('Error deleting session:', error);
            this.showMessage('Error deleting session', 'error');
        }
    }

    showMessage(msg, type = 'info') {
        const container = document.getElementById('messageContainer');
        const el = document.createElement('div');
        el.className = `alert alert-${type}`;
        el.textContent = msg;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    }

    async showDetail(sessionId) {
        const s = this.sessions.find(session => session.session_id === sessionId);
        if (!s) return;

        const modal = document.getElementById('detailModal');
        const loading = document.getElementById('modalLoading');
        const body = document.getElementById('modalBody');
        
        modal.style.display = 'flex';
        loading.style.display = 'block';
        body.style.display = 'none';

        // Fetch complete replay data (which includes features)
        try {
            const response = await fetch(`/api/v1/sessions/${sessionId}/replay`);
            const result = await response.json();
            
            loading.style.display = 'none';
            body.style.display = 'block';
            
            if (result.success && result.data) {
                const data = result.data;
                const f = data.features || {};
                
                let riskColor = 'var(--text-muted)';
                if (data.risk_level === 'HIGH') riskColor = 'var(--danger)';
                else if (data.risk_level === 'MEDIUM') riskColor = 'var(--warning)';
                else if (data.risk_level === 'LOW') riskColor = 'var(--success)';

                // Overview
                document.getElementById('modalOverview').innerHTML = `
                    <div><strong>Session ID:</strong> <span class="mono">${data.session_id}</span></div>
                    <div><strong>User ID:</strong> ${s.user_id} (${s.username})</div>
                    <div><strong>Start Time:</strong> ${new Date(s.start_time).toLocaleString()}</div>
                    <div><strong>End Time:</strong> ${s.end_time ? new Date(s.end_time).toLocaleString() : 'Active/Incomplete'}</div>
                    <div><strong>Baseline:</strong> ${s.is_baseline ? 'Yes' : 'No'}</div>
                    <div><strong>Event Count:</strong> ${s.event_count || (data.events ? data.events.length : 0)}</div>
                `;

                // Risk
                document.getElementById('modalRisk').innerHTML = `
                    <div><strong>Risk Level:</strong> <span style="color: ${riskColor}; font-weight: bold;">${data.risk_level || s.risk_level || 'N/A'}</span></div>
                    <div><strong>Anomaly Score:</strong> ${data.anomaly_score !== null ? parseFloat(data.anomaly_score).toFixed(4) : (s.anomaly_score !== null ? parseFloat(s.anomaly_score).toFixed(4) : 'N/A')}</div>
                    <div><strong>Action Taken:</strong> ${s.action || 'None'}</div>
                    <div><strong>IP Address:</strong> ${s.ip_address || 'Unknown'}</div>
                `;

                // Features
                if (Object.keys(f).length > 0) {
                    document.getElementById('modalFeatures').innerHTML = Object.entries(f).map(([k, v]) => `
                        <div style="background: rgba(255,255,255,0.02); padding: 8px; border-radius: 4px; border-left: 2px solid var(--primary-color);">
                            <div style="color: var(--text-muted); font-size: 11px; margin-bottom: 4px;">${k.replace(/_/g, ' ').toUpperCase()}</div>
                            <div class="mono" style="font-weight: 600;">${typeof v === 'number' ? v.toFixed(4) : v}</div>
                        </div>
                    `).join('');
                } else {
                    document.getElementById('modalFeatures').innerHTML = `<div style="grid-column: 1/-1; color: var(--text-muted); padding: 16px;">No features extracted yet (session might still be active or insufficient events).</div>`;
                }
            } else {
                body.innerHTML = `<div style="color: var(--danger); padding: 20px;">Failed to load details: ${result.detail || 'Unknown error'}</div>`;
            }
        } catch (error) {
            loading.style.display = 'none';
            body.style.display = 'block';
            body.innerHTML = `<div style="color: var(--danger); padding: 20px;">Error connecting to server.</div>`;
        }
    }
}

// Initialize
let dbManager;
document.addEventListener('DOMContentLoaded', () => {
    dbManager = new DatabaseManager();
    
    // Setup Modal Close
    document.getElementById('closeModalBtn')?.addEventListener('click', () => {
        document.getElementById('detailModal').style.display = 'none';
    });
    
    // Close modal on click outside
    document.getElementById('detailModal')?.addEventListener('click', (e) => {
        if (e.target.id === 'detailModal') {
            e.target.style.display = 'none';
        }
    });
});
