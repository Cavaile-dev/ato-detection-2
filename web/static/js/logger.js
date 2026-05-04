/**
 * Behavior Logger
 * Captures mouse movements, clicks, keystrokes, scroll, and navigation events
 */

class BehaviorLogger {
    constructor() {
        this.events = [];
        this.isLogging = false;
        this.startTime = null;
        this.lastMousePosition = { x: 0, y: 0 };
        this.lastMouseTime = 0;
        this.lastKeystrokeTime = 0;
        this.lastScrollTime = 0;
        this.keyDownTime = {};
        this.scrollListenerOptions = { passive: true };

        // Throttling parameters
        this.mouseMoveThrottle = 16; // ~60fps
        this.lastMouseMoveTime = 0;

        // Bind methods
        this.handleMouseMove = this.handleMouseMove.bind(this);
        this.handleMouseClick = this.handleMouseClick.bind(this);
        this.handleScroll = this.handleScroll.bind(this);
        this.handleKeyDown = this.handleKeyDown.bind(this);
        this.handleKeyUp = this.handleKeyUp.bind(this);
        this.handleCopy = this.handleCopy.bind(this);
        this.handlePaste = this.handlePaste.bind(this);
    }

    start() {
        if (this.isLogging) return;

        this.isLogging = true;
        this.startTime = Date.now();
        this.events = [];

        // Mouse events
        document.addEventListener('mousemove', this.handleMouseMove);
        document.addEventListener('click', this.handleMouseClick);

        // Wheel events provide reliable delta values for scroll analysis.
        document.addEventListener('wheel', this.handleScroll, this.scrollListenerOptions);

        // Keyboard events
        document.addEventListener('keydown', this.handleKeyDown);
        document.addEventListener('keyup', this.handleKeyUp);

        // Copy/Paste events
        document.addEventListener('copy', this.handleCopy);
        document.addEventListener('paste', this.handlePaste);

        console.log('[BehaviorLogger] Started logging');
    }

    stop() {
        if (!this.isLogging) return;

        this.isLogging = false;

        // Remove event listeners
        document.removeEventListener('mousemove', this.handleMouseMove);
        document.removeEventListener('click', this.handleMouseClick);
        document.removeEventListener('wheel', this.handleScroll, this.scrollListenerOptions);
        document.removeEventListener('keydown', this.handleKeyDown);
        document.removeEventListener('keyup', this.handleKeyUp);
        document.removeEventListener('copy', this.handleCopy);
        document.removeEventListener('paste', this.handlePaste);

        console.log('[BehaviorLogger] Stopped logging. Total events:', this.events.length);
    }

    getEvents() {
        return [...this.events];
    }

    clearEvents() {
        this.events = [];
    }

    getEventCount() {
        return this.events.length;
    }

    // Event Handlers

    handleMouseMove(e) {
        if (!this.isLogging) return;

        const now = Date.now();

        // Throttle mouse move events
        if (now - this.lastMouseMoveTime < this.mouseMoveThrottle) {
            return;
        }
        this.lastMouseMoveTime = now;

        const currentTime = now;
        const dt = currentTime - this.lastMouseTime;

        // Calculate velocity
        const dx = e.clientX - this.lastMousePosition.x;
        const dy = e.clientY - this.lastMousePosition.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const velocity = dt > 0 ? distance / dt : 0;

        // Calculate acceleration
        let acceleration = 0;
        if (this.lastEvent && this.lastEvent.event_type === 'MOUSE_MOVE') {
            const lastVelocity = this.lastEvent.velocity || 0;
            acceleration = dt > 0 ? (velocity - lastVelocity) / dt : 0;
        }

        const event = {
            event_type: 'MOUSE_MOVE',
            timestamp: now,
            x: e.clientX,
            y: e.clientY,
            velocity: velocity,
            acceleration: acceleration,
            page_url: window.location.href,
            page_title: document.title
        };

        this.addEvent(event);

        this.lastMousePosition = { x: e.clientX, y: e.clientY };
        this.lastMouseTime = currentTime;
    }

    handleMouseClick(e) {
        if (!this.isLogging) return;

        const now = Date.now();

        // Calculate click interval
        let clickInterval = 0;
        if (this.lastClickTime) {
            clickInterval = now - this.lastClickTime;
        }
        this.lastClickTime = now;

        const event = {
            event_type: 'MOUSE_CLICK',
            timestamp: now,
            x: e.clientX,
            y: e.clientY,
            button: e.button,
            page_url: window.location.href,
            page_title: document.title
        };

        this.addEvent(event);
    }

    handleScroll(e) {
        if (!this.isLogging) return;

        const now = Date.now();

        const scrollDelta = e.deltaY;
        if (!Number.isFinite(scrollDelta) || scrollDelta === 0) {
            return;
        }

        let scrollVelocity = 0;

        if (this.lastScrollTime) {
            const dt = now - this.lastScrollTime;
            scrollVelocity = dt > 0 ? Math.abs(scrollDelta) / dt : 0;
        }
        this.lastScrollTime = now;

        const event = {
            event_type: 'MOUSE_SCROLL',
            timestamp: now,
            scroll_delta: scrollDelta,
            scroll_velocity: scrollVelocity,
            x: e.clientX,
            y: e.clientY,
            page_url: window.location.href,
            page_title: document.title
        };

        this.addEvent(event);
    }

    handleKeyDown(e) {
        if (!this.isLogging) return;

        const now = Date.now();

        // Record key down time for dwell time calculation
        this.keyDownTime[e.key] = now;

        // Calculate key interval (time since last keystroke)
        const keyInterval = this.lastKeystrokeTime ? now - this.lastKeystrokeTime : 0;
        this.lastKeystrokeTime = now;

        const event = {
            event_type: 'KEYSTROKE',
            timestamp: now,
            key: e.key,
            key_code: e.keyCode,
            key_interval: keyInterval,
            page_url: window.location.href,
            page_title: document.title
        };

        this.addEvent(event);
    }

    handleKeyUp(e) {
        if (!this.isLogging) return;

        const now = Date.now();

        // Calculate hold time (dwell time)
        let holdTime = 0;
        if (this.keyDownTime[e.key]) {
            holdTime = now - this.keyDownTime[e.key];
            delete this.keyDownTime[e.key];
        }

        // Update the last keystroke event with hold time
        const lastKeystrokeEvents = this.events.filter(
            ev => ev.event_type === 'KEYSTROKE' && ev.key === e.key
        );

        if (lastKeystrokeEvents.length > 0) {
            const lastEvent = lastKeystrokeEvents[lastKeystrokeEvents.length - 1];
            if (!lastEvent.hold_time) {
                lastEvent.hold_time = holdTime;
            }
        }
    }

    handleCopy(e) {
        if (!this.isLogging) return;

        const event = {
            event_type: 'COPY',
            timestamp: Date.now(),
            page_url: window.location.href,
            page_title: document.title
        };

        this.addEvent(event);
    }

    handlePaste(e) {
        if (!this.isLogging) return;

        const event = {
            event_type: 'PASTE',
            timestamp: Date.now(),
            page_url: window.location.href,
            page_title: document.title
        };

        this.addEvent(event);
    }

    addEvent(event) {
        this.events.push(event);
        this.lastEvent = event;
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BehaviorLogger;
}
