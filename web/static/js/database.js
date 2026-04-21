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
                    const searchStr = `${s.session_id} ${s.username} ${s.risk_level} ${s.start_time}`.toLowerCase();
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

            return `
                <tr>
                    <td class="mono">${s.session_id}</td>
                    <td>${s.username}</td>
                    <td>${date}</td>
                    <td>${s.event_count}</td>
                    <td style="color: ${riskColor}; font-weight: 600;">${risk}</td>
                    <td>${score}</td>
                    <td style="display: flex; gap: 8px;">
                        <button class="btn btn-ghost btn-sm" onclick="dbManager.showDetail('${s.session_id}')" style="padding: 4px 12px; font-size: 12px; border: 1px solid var(--border-subtle);">Detail</button>
                        <button class="btn-delete" onclick="dbManager.deleteSession('${s.session_id}')">Delete</button>
                    </td>
                </tr>
            `;
        }).join('');
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

    showDetail(sessionId) {
        const s = this.sessions.find(session => session.session_id === sessionId);
        if (!s) return;

        const details = `
Session ID: ${s.session_id}
User: ${s.username} (ID: ${s.user_id})
Risk Level: ${s.risk_level || 'N/A'}
Anomaly Score: ${s.anomaly_score !== null ? s.anomaly_score : 'N/A'}
Action Taken: ${s.action || 'None'}
Start Time: ${new Date(s.start_time).toLocaleString()}
End Time: ${s.end_time ? new Date(s.end_time).toLocaleString() : 'Active/Incomplete'}
Event Count: ${s.event_count}
IP Address: ${s.ip_address || 'Unknown'}
Baseline Session: ${s.is_baseline ? 'Yes' : 'No'}
        `.trim();

        alert("Session Details:\n\n" + details);
    }
}

// Initialize
let dbManager;
document.addEventListener('DOMContentLoaded', () => {
    dbManager = new DatabaseManager();
});
