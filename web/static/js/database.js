const APP_TIMEZONE = 'Asia/Jakarta';

function formatJakartaDateTime(value) {
    if (!value) return 'N/A';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleString('id-ID', {
        timeZone: APP_TIMEZONE,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

class DatabaseManager {
    constructor() {
        this.sessions = [];
        this.users = [];
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
        if (!window.shopApp) {
            document.getElementById('logoutBtn').addEventListener('click', () => this.logout());
        }

        document.getElementById('refreshDbBtn').addEventListener('click', () => {
            this.loadSessions();
        });

        document.getElementById('deleteDbBtn').addEventListener('click', () => {
            this.deleteDatabase();
        });
        document.getElementById('deleteUserBtn')?.addEventListener('click', () => {
            this.deleteSelectedUser();
        });

        const searchInput = document.getElementById('dbSearch');
        const trainingValidityFilter = document.getElementById('trainingValidityFilter');
        const userFilter = document.getElementById('userFilter');
        const clearFiltersBtn = document.getElementById('clearFiltersBtn');

        searchInput?.addEventListener('input', () => this.applyFilters());
        trainingValidityFilter?.addEventListener('change', () => this.applyFilters());
        userFilter?.addEventListener('change', () => this.applyFilters());
        clearFiltersBtn?.addEventListener('click', () => this.clearFilters());

        // Load data
        this.loadUsers();
        this.loadSessions();
    }

    async loadUsers() {
        try {
            const response = await fetch('/api/v1/users');
            const result = await response.json();

            if (result.success && result.data?.users) {
                this.users = result.data.users;
                this.refreshUserFilterOptions();
                this.refreshDeleteUserOptions();
            }
        } catch (error) {
            console.error('Error loading users:', error);
        }
    }

    async loadSessions() {
        const tbody = document.getElementById('dbTableBody');
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Loading data...</td></tr>';

        try {
            const response = await fetch('/api/v1/sessions');
            const result = await response.json();

            if (result.success && result.data.sessions) {
                this.sessions = result.data.sessions;
                this.refreshUserFilterOptions();
                this.applyFilters();
            } else {
                tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Failed to load sessions.</td></tr>';
            }
        } catch (error) {
            console.error('Error loading sessions:', error);
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Error loading sessions.</td></tr>';
        }
    }

    isTrainingValidSession(session) {
        return session.is_baseline === true || session.is_baseline === 1 || session.is_baseline === '1';
    }

    refreshUserFilterOptions() {
        const userFilter = document.getElementById('userFilter');
        if (!userFilter) return;

        const previousValue = userFilter.value || 'all';
        const uniqueUsers = new Map();

        if (this.users.length > 0) {
            this.users.forEach((u) => {
                const id = String(u.id);
                uniqueUsers.set(id, {
                    id: id,
                    username: u.username || `User ${id}`
                });
            });
        } else {
            this.sessions.forEach((s) => {
                const id = String(s.user_id);
                if (!uniqueUsers.has(id)) {
                    uniqueUsers.set(id, {
                        id: id,
                        username: s.username || `User ${id}`
                    });
                }
            });
        }

        const sortedUsers = Array.from(uniqueUsers.values())
            .sort((a, b) => a.username.localeCompare(b.username));

        userFilter.innerHTML = [
            '<option value="all">All users</option>',
            ...sortedUsers.map((u) => `<option value="${u.id}">${u.username}</option>`)
        ].join('');

        if (Array.from(userFilter.options).some((opt) => opt.value === previousValue)) {
            userFilter.value = previousValue;
        } else {
            userFilter.value = 'all';
        }
    }

    refreshDeleteUserOptions() {
        const deleteUserSelect = document.getElementById('deleteUserSelect');
        if (!deleteUserSelect) return;

        const previousValue = deleteUserSelect.value || '';
        const sortedUsers = [...this.users].sort((a, b) => {
            const nameA = (a.username || '').toLowerCase();
            const nameB = (b.username || '').toLowerCase();
            return nameA.localeCompare(nameB);
        });

        deleteUserSelect.innerHTML = [
            '<option value="">Select user to delete</option>',
            ...sortedUsers.map((u) => (
                `<option value="${u.id}">${u.username} (ID ${u.id}, ${u.total_sessions || 0} sessions)</option>`
            ))
        ].join('');

        if (Array.from(deleteUserSelect.options).some((opt) => opt.value === previousValue)) {
            deleteUserSelect.value = previousValue;
        }
    }

    applyFilters() {
        const searchTerm = (document.getElementById('dbSearch')?.value || '').trim().toLowerCase();
        const trainingValidityFilter = document.getElementById('trainingValidityFilter')?.value || 'all';
        const userFilter = document.getElementById('userFilter')?.value || 'all';

        const filtered = this.sessions.filter((s) => {
            const isTrainingValid = this.isTrainingValidSession(s);

            if (trainingValidityFilter === 'train_valid' && !isTrainingValid) return false;
            if (trainingValidityFilter === 'non_train_valid' && isTrainingValid) return false;

            if (userFilter !== 'all' && String(s.user_id) !== userFilter) return false;

            if (!searchTerm) return true;
            const statusText = s.end_time ? 'completed' : 'active';
            const trainValidityText = isTrainingValid ? 'train-valid' : 'not-train-valid';
            const searchStr = `${s.session_id} ${s.username} ${s.user_id} ${s.risk_level} ${s.start_time} ${statusText} ${trainValidityText}`.toLowerCase();
            return searchStr.includes(searchTerm);
        });

        this.renderSessions(filtered);
        this.updateFilterHint(filtered.length, trainingValidityFilter, userFilter);
    }

    updateFilterHint(count, trainingValidityFilter, userFilter) {
        const hint = document.getElementById('dbFilterHint');
        if (!hint) return;

        const trainingValidityLabel = trainingValidityFilter === 'train_valid'
            ? 'train-valid only'
            : trainingValidityFilter === 'non_train_valid'
                ? 'not train-valid only'
                : 'all training statuses';

        let userLabel = 'all users';
        if (userFilter !== 'all') {
            const selectedOption = document.querySelector(`#userFilter option[value="${userFilter}"]`);
            userLabel = selectedOption ? selectedOption.textContent : `user ${userFilter}`;
        }

        hint.textContent = `Showing ${count} session(s) - ${trainingValidityLabel} - ${userLabel}`;
    }

    clearFilters() {
        const searchInput = document.getElementById('dbSearch');
        const trainingValidityFilter = document.getElementById('trainingValidityFilter');
        const userFilter = document.getElementById('userFilter');

        if (searchInput) searchInput.value = '';
        if (trainingValidityFilter) trainingValidityFilter.value = 'all';
        if (userFilter) userFilter.value = 'all';

        this.applyFilters();
    }

    renderSessions(sessions) {
        const tbody = document.getElementById('dbTableBody');
        
        if (sessions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No sessions found with current filters.</td></tr>';
            return;
        }

        tbody.innerHTML = sessions.map(s => {
            const date = formatJakartaDateTime(s.start_time);
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
            const response = await fetch(`/api/v1/sessions/${sessionId}/force-end`, {
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

    async logout() {
        const currentSessionId = sessionStorage.getItem('sessionId');

        try {
            if (currentSessionId) {
                await fetch(`/api/v1/sessions/${currentSessionId}/end`, {
                    method: 'POST'
                });
            }
        } catch (error) {
            console.error('Error ending session during logout:', error);
        }

        try {
            await fetch('/api/v1/logout', { method: 'POST' });
        } catch (error) {
            console.error('Error clearing server logout state:', error);
        }

        sessionStorage.clear();
        window.location.href = '/';
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

    async deleteDatabase() {
        const firstConfirm = confirm(
            'This will permanently delete ALL users, sessions, events, features, and model metadata. Continue?'
        );
        if (!firstConfirm) return;

        const typed = prompt('Type DELETE to confirm full database reset:');
        if (typed !== 'DELETE') {
            this.showMessage('Database reset cancelled', 'info');
            return;
        }

        try {
            const response = await fetch('/api/v1/database/reset', {
                method: 'POST'
            });
            const result = await response.json();

            if (result.success) {
                this.showMessage('Database reset successful. Redirecting to login...', 'success');
                setTimeout(() => {
                    sessionStorage.clear();
                    window.location.href = '/';
                }, 1200);
            } else {
                this.showMessage(result.detail || 'Failed to reset database', 'error');
            }
        } catch (error) {
            console.error('Error resetting database:', error);
            this.showMessage('Error resetting database', 'error');
        }
    }

    async deleteSelectedUser() {
        const deleteUserSelect = document.getElementById('deleteUserSelect');
        const selectedUserId = deleteUserSelect?.value;
        if (!selectedUserId) {
            this.showMessage('Please select a user first', 'warning');
            return;
        }

        const user = this.users.find((u) => String(u.id) === String(selectedUserId));
        const username = user?.username || `User ${selectedUserId}`;

        const firstConfirm = confirm(
            `Delete user "${username}" and ALL related sessions/events/features/models?`
        );
        if (!firstConfirm) return;

        const typed = prompt(`Type ${username} to confirm user deletion:`);
        if (typed !== username) {
            this.showMessage('User deletion cancelled', 'info');
            return;
        }

        try {
            const response = await fetch(`/api/v1/users/${selectedUserId}`, {
                method: 'DELETE'
            });
            const result = await response.json();

            if (!result.success) {
                this.showMessage(result.detail || 'Failed to delete user', 'error');
                return;
            }

            const data = result.data || {};
            const summary = [
                `Deleted user ${data.username || username}.`,
                `${data.sessions_deleted || 0} session(s),`,
                `${data.events_deleted || 0} event(s),`,
                `${data.features_deleted || 0} feature row(s),`,
                `${data.models_deleted || 0} model metadata row(s).`
            ].join(' ');

            if (data.logged_out) {
                this.showMessage(`${summary} Redirecting to login...`, 'success');
                setTimeout(() => {
                    sessionStorage.clear();
                    window.location.href = '/';
                }, 1200);
                return;
            }

            this.showMessage(summary, 'success');
            await this.loadUsers();
            await this.loadSessions();
        } catch (error) {
            console.error('Error deleting user:', error);
            this.showMessage('Error deleting user', 'error');
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
                    <div><strong>Start Time:</strong> ${formatJakartaDateTime(s.start_time)}</div>
                    <div><strong>End Time:</strong> ${s.end_time ? formatJakartaDateTime(s.end_time) : 'Active/Incomplete'}</div>
                    <div><strong>Valid for Training:</strong> ${s.is_baseline ? 'Yes' : 'No'}</div>
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
