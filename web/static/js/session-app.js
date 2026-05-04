/**
 * Session Application
 * Manages active session, event submission, and risk assessment
 */

class SessionApp {
    constructor() {
        this.behaviorLogger = new BehaviorLogger();
        this.sessionId = null;
        this.userId = null;
        this.username = null;
        this.submitInterval = null;
        this.eventCount = 0;

        this.init();
    }

    init() {
        // Check if user is logged in
        this.sessionId = sessionStorage.getItem('sessionId');
        this.userId = sessionStorage.getItem('userId');
        this.username = sessionStorage.getItem('username');

        if (!this.sessionId || !this.userId) {
            window.location.href = '/';
            return;
        }

        // Update UI
        this.updateUI();

        // Setup event listeners
        this.setupEventListeners();

        // Start behavior logging
        this.behaviorLogger.start();

        // Start periodic event submission
        this.startPeriodicSubmission();
    }

    updateUI() {
        document.getElementById('usernameDisplay').textContent = this.username;
        document.getElementById('sessionId').textContent = this.sessionId.substring(0, 8) + '...';
        document.getElementById('trainingValidStatus').textContent = 'Pending (session active)';
    }

    setupEventListeners() {
        document.getElementById('logoutBtn').addEventListener('click', () => this.logout());
        document.getElementById('dashboardBtn').addEventListener('click', () => this.goToDashboard());
        document.getElementById('submitEventsBtn').addEventListener('click', () => this.submitEvents());
        document.getElementById('assessBtn').addEventListener('click', () => this.assessSession());
        document.getElementById('trainModelBtn').addEventListener('click', () => this.trainModel());
    }

    async submitEvents() {
        const events = this.behaviorLogger.getEvents();

        if (events.length === 0) {
            this.showMessage('No events to submit', 'warning');
            return;
        }

        try {
            const response = await fetch('/api/v1/events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    events: events
                })
            });

            const result = await response.json();

            if (result.success) {
                this.eventCount += result.data.events_processed;
                document.getElementById('eventCount').textContent = this.eventCount;

                const totalEvents = result.data.total_events || 0;
                const trainingValidStatus = document.getElementById('trainingValidStatus');
                if (trainingValidStatus) {
                    if (totalEvents >= 30) {
                        trainingValidStatus.textContent = 'Likely valid (finalized when session ends)';
                    } else {
                        trainingValidStatus.textContent = `Not yet (${30 - totalEvents} events remaining)`;
                    }
                }

                this.showMessage(`Submitted ${result.data.events_processed} events`, 'success');

                // Check if assessment was performed
                if (result.data.assessment) {
                    this.displayAssessment(result.data.assessment);
                }

                // Clear events after submission
                this.behaviorLogger.clearEvents();
            } else {
                this.showMessage(result.data?.detail || 'Failed to submit events', 'error');
            }
        } catch (error) {
            console.error('Error submitting events:', error);
            this.showMessage('Error submitting events', 'error');
        }
    }

    async assessSession() {
        try {
            this.showMessage('Assessing session...', 'info');

            const response = await fetch('/api/v1/sessions/assess', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    session_id: this.sessionId
                })
            });

            const result = await response.json();

            if (result.success) {
                this.displayAssessment(result.data);
                this.showMessage('Assessment complete', 'success');
            } else {
                this.showMessage(result.data?.detail || 'Assessment failed', 'error');
            }
        } catch (error) {
            console.error('Error assessing session:', error);
            this.showMessage('Error assessing session', 'error');
        }
    }

    displayAssessment(assessment) {
        const riskLevel = document.getElementById('riskLevel');
        riskLevel.textContent = assessment.risk_level;

        // Remove existing risk classes
        riskLevel.classList.remove('risk-low', 'risk-medium', 'risk-high');

        // Add appropriate risk class
        if (assessment.risk_level === 'LOW') {
            riskLevel.classList.add('risk-low');
        } else if (assessment.risk_level === 'MEDIUM') {
            riskLevel.classList.add('risk-medium');
        } else {
            riskLevel.classList.add('risk-high');
        }

        // Log assessment details
        console.log('Risk Assessment:', assessment);

        // Add to activity log
        this.addLogEntry(`Risk: ${assessment.risk_level} (${assessment.anomaly_score.toFixed(3)})`);

        // Show action message
        if (assessment.action === 'BLOCK_SESSION') {
            this.showMessage('HIGH RISK DETECTED: Session blocked', 'error');
        } else if (assessment.action === 'REQUIRE_MFA') {
            this.showMessage('MEDIUM RISK: Additional authentication required', 'warning');
        }
    }

    async trainModel() {
        try {
            this.showMessage('Training model...', 'info');

            const response = await fetch('/api/v1/model/train', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    scope: 'global',
                    min_samples: 10
                })
            });

            const result = await response.json();

            if (result.success && result.data.success) {
                this.showMessage(`Model trained with ${result.data.samples_used} samples`, 'success');
                this.addLogEntry(`Model trained: ${result.data.samples_used} samples`);
            } else {
                this.showMessage(result.data?.detail || 'Training failed', 'error');
            }
        } catch (error) {
            console.error('Error training model:', error);
            this.showMessage('Error training model', 'error');
        }
    }

    startPeriodicSubmission() {
        // Submit events every 10 seconds
        this.submitInterval = setInterval(() => {
            if (this.behaviorLogger.getEventCount() > 0) {
                this.submitEvents();
            }
        }, 10000);
    }

    addLogEntry(message) {
        const log = document.getElementById('activityLog');
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        const nowLabel = new Date().toLocaleTimeString('id-ID', {
            timeZone: 'Asia/Jakarta',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        entry.textContent = `[${nowLabel}] ${message}`;
        log.insertBefore(entry, log.firstChild);

        // Keep only last 50 entries
        while (log.children.length > 50) {
            log.removeChild(log.lastChild);
        }
    }

    async logout() {
        window.isInternalNavigation = true;

        // End session
        try {
            await fetch(`/api/v1/sessions/${this.sessionId}/end`, {
                method: 'POST'
            });
        } catch (error) {
            console.error('Error ending session:', error);
        }

        try {
            await fetch('/api/v1/logout', {
                method: 'POST'
            });
        } catch (error) {
            console.error('Error clearing server session:', error);
        }

        // Stop logging
        this.behaviorLogger.stop();
        clearInterval(this.submitInterval);

        // Clear session storage
        sessionStorage.clear();

        // Redirect to login
        window.location.href = '/';
    }

    goToDashboard() {
        window.location.href = '/dashboard';
    }

    showMessage(message, type) {
        const container = document.getElementById('messageContainer');
        const messageDiv = document.createElement('div');
        messageDiv.className = `alert alert-${type}`;
        messageDiv.textContent = message;
        container.appendChild(messageDiv);

        setTimeout(() => {
            messageDiv.remove();
        }, 5000);
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new SessionApp();
});
