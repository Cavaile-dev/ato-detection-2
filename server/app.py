"""
Flask API Application
REST API for Real-Time Login Anomaly Detection System
"""

import logging
from flask import Flask, request, jsonify, render_template, session as flask_session, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from server.config import (
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    CORS_ORIGINS,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_FILE,
    SESSION_SECRET_KEY,
    SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE
)
from server.database import db
from server.pipeline import pipeline
from server.time_utils import now_in_app_tz_iso
from server.schemas import (
    LoginRequest,
    SessionStartRequest,
    EventsSubmitRequest,
    TrainModelRequest,
    SessionReassessRequest,
    UserResponse,
    SessionResponse,
    RiskAssessmentResponse,
    DashboardStatsResponse,
    ErrorResponse
)

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__,
            template_folder='../web/templates',
            static_folder='../web/static')
app.config.update(
    SECRET_KEY=SESSION_SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SAMESITE=SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE
)

# Enable CORS
CORS(app, resources={
    r"/api/*": {
        "origins": CORS_ORIGINS,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})


# Error handlers
@app.errorhandler(400)
def bad_request(error):
    return jsonify(ErrorResponse(
        error="Bad Request",
        detail=str(error)
    ).model_dump()), 400


@app.errorhandler(404)
def not_found(error):
    return jsonify(ErrorResponse(
        error="Not Found",
        detail="The requested resource was not found"
    ).model_dump()), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify(ErrorResponse(
        error="Internal Server Error",
        detail="An unexpected error occurred"
    ).model_dump()), 500


# Helper functions
def validate_request(schema_class):
    """Decorator to validate request against schema"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                data = request.get_json()
                validated = schema_class(**data)
                request.validated_data = validated
                return f(validated, *args, **kwargs)
            except Exception as e:
                logger.error(f"Validation error in {request.path}: {e}")
                return jsonify(ErrorResponse(
                    error="Validation Error",
                    detail=str(e)
                ).model_dump()), 400
        return wrapper
    return decorator


def _resolve_auth_context(require_active_session: bool = True):
    """Resolve authenticated user/session from Flask session cookie."""
    user_id = flask_session.get('user_id')
    current_session_id = flask_session.get('session_id')

    if not user_id:
        return None, (
            "Authentication Required",
            "Please sign in to continue.",
            401
        )

    user = db.get_user_by_id(int(user_id))
    if not user:
        flask_session.clear()
        return None, (
            "Authentication Required",
            "User session is no longer valid. Please sign in again.",
            401
        )

    session_record = None
    if current_session_id:
        session_record = db.get_session(current_session_id)
        if session_record and int(session_record.get('user_id')) != int(user_id):
            session_record = None

    if require_active_session:
        if not session_record or session_record.get('end_time') is not None:
            flask_session.clear()
            return None, (
                "Authentication Required",
                "Your session has expired. Please sign in again.",
                401
            )

    return {
        'user': user,
        'user_id': int(user_id),
        'session_id': current_session_id,
        'session': session_record
    }, None


def require_api_auth(active_session: bool = True):
    """Decorator for API routes that require authenticated access."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            context, error = _resolve_auth_context(require_active_session=active_session)
            if error:
                error_name, detail, status_code = error
                return jsonify(ErrorResponse(
                    error=error_name,
                    detail=detail
                ).model_dump()), status_code

            g.auth_context = context
            return f(*args, **kwargs)
        return wrapper
    return decorator


def current_session_only(session_id: str):
    """Ensure the requested session matches the authenticated active session."""
    auth_context = getattr(g, 'auth_context', None) or {}
    current_session_id = auth_context.get('session_id')
    if current_session_id == session_id:
        return None

    return jsonify(ErrorResponse(
        error="Forbidden",
        detail="This operation is only allowed for your active authenticated session."
    ).model_dump()), 403


def success_response(data):
    """Create success response"""
    return jsonify({
        'success': True,
        'data': data,
        'timestamp': now_in_app_tz_iso()
    })


# ==================== HTML Routes ====================

@app.route('/')
def index():
    """Serve login page"""
    return render_template('login.html')


@app.route('/shop')
def shop_page():
    """Serve e-commerce shop homepage"""
    return render_template('shop.html')


@app.route('/cart')
def cart_page():
    """Serve cart review page"""
    return render_template('cart.html')


@app.route('/checkout')
def checkout_page():
    """Serve checkout/payment page"""
    return render_template('checkout.html')


@app.route('/wallet')
def wallet_page():
    """Serve wallet page"""
    return render_template('wallet.html')


@app.route('/dashboard')
def dashboard():
    """Serve dashboard page"""
    return render_template('dashboard.html')


@app.route('/session')
def session_page():
    """Serve session page"""
    return render_template('session.html')

@app.route('/database')
def database_page():
    """Serve database manager page"""
    return render_template('database.html')


# ==================== API Routes ====================

@app.route('/api/v1/login', methods=['POST'])
@validate_request(LoginRequest)
def login(data: LoginRequest):
    """
    User login endpoint

    Request:
    {
        "username": "string",
        "password": "string"
    }

    Response:
    {
        "success": true,
        "data": {
            "user_id": int,
            "username": "string",
            "train_valid_sessions": int,
            "session_id": "string"
        }
    }
    """
    try:
        # Get user from database
        user = db.get_user_by_username(data.username)

        if not user:
            return jsonify(ErrorResponse(
                error="Authentication Failed",
                detail="Invalid username or password"
            ).model_dump()), 401

        # Check password
        if not check_password_hash(user['password_hash'], data.password):
            return jsonify(ErrorResponse(
                error="Authentication Failed",
                detail="Invalid username or password"
            ).model_dump()), 401

        # Start session
        session_id = pipeline.start_session(
            user_id=user['id'],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            device_fingerprint=request.headers.get('X-Device-Fingerprint')
        )

        flask_session.clear()
        flask_session['user_id'] = int(user['id'])
        flask_session['session_id'] = session_id
        flask_session['username'] = user['username']

        response_data = {
            'user_id': user['id'],
            'username': user['username'],
            'train_valid_sessions': db.get_user_training_valid_session_count(user['id']),
            'session_id': session_id
        }

        logger.info(f"User {data.username} logged in successfully")

        return success_response(response_data)

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify(ErrorResponse(
            error="Login Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/register', methods=['POST'])
@validate_request(LoginRequest)
def register(data: LoginRequest):
    """
    User registration endpoint

    Request:
    {
        "username": "string",
        "password": "string"
    }

    Response:
    {
        "success": true,
        "data": {
            "user_id": int,
            "username": "string"
        }
    }
    """
    try:
        # Check if user exists
        existing_user = db.get_user_by_username(data.username)
        if existing_user:
            return jsonify(ErrorResponse(
                error="Registration Failed",
                detail="Username already exists"
            ).model_dump()), 400

        # Create user
        password_hash = generate_password_hash(data.password)
        user_id = db.create_user(data.username, password_hash)

        response_data = {
            'user_id': user_id,
            'username': data.username
        }

        logger.info(f"New user registered: {data.username}")

        return success_response(response_data)

    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify(ErrorResponse(
            error="Registration Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/sessions/start', methods=['POST'])
@require_api_auth(active_session=False)
@validate_request(SessionStartRequest)
def start_session(data: SessionStartRequest):
    """
    Start a new session

    Request:
    {
        "user_id": int,
        "ip_address": "string" (optional),
        "device_fingerprint": "string" (optional)
    }

    Response:
    {
        "success": true,
        "data": {
            "session_id": "string",
            "is_training_valid": bool
        }
    }
    """
    try:
        auth_user_id = g.auth_context['user_id']
        if int(data.user_id) != int(auth_user_id):
            return jsonify(ErrorResponse(
                error="Forbidden",
                detail="You can only start a session for the authenticated user."
            ).model_dump()), 403

        session_id = pipeline.start_session(
            user_id=data.user_id,
            ip_address=data.ip_address or request.remote_addr,
            device_fingerprint=data.device_fingerprint,
            user_agent=request.headers.get('User-Agent')
        )
        flask_session['session_id'] = session_id

        session_state = pipeline.get_session(session_id)

        response_data = {
            'session_id': session_id,
            # Backward-compatible key: is_baseline now means "valid for training".
            'is_baseline': session_state.is_baseline if session_state else False,
            'is_training_valid': session_state.is_baseline if session_state else False
        }

        return success_response(response_data)

    except Exception as e:
        logger.error(f"Session start error: {e}")
        return jsonify(ErrorResponse(
            error="Session Start Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/events', methods=['POST'])
@require_api_auth()
@validate_request(EventsSubmitRequest)
def submit_events(data: EventsSubmitRequest):
    """
    Submit behavioral events for a session

    Request:
    {
        "session_id": "string",
        "events": [
            {
                "event_type": "MOUSE_MOVE",
                "timestamp": 1234567890,
                "x": 100,
                "y": 200,
                ...
            }
        ]
    }

    Response:
    {
        "success": true,
        "data": {
            "session_id": "string",
            "events_processed": int,
            "total_events": int,
            "assessment": { ... }  // If assessment was performed
        }
    }
    """
    try:
        mismatch_response = current_session_only(data.session_id)
        if mismatch_response:
            return mismatch_response

        # Convert events to dict format
        events_dict = [event.model_dump() for event in data.events]

        # Process events
        result = pipeline.process_events(data.session_id, events_dict)

        return success_response(result)

    except ValueError as e:
        return jsonify(ErrorResponse(
            error="Processing Error",
            detail=str(e)
        ).model_dump()), 404

    except Exception as e:
        logger.error(f"Event processing error: {e}")
        return jsonify(ErrorResponse(
            error="Event Processing Error",
            detail=str(e)
        ).model_dump()), 500

@app.route('/api/v1/sessions/assess', methods=['POST'])
@require_api_auth()
def assess_session():
    """
    Force risk assessment for a session

    Request:
    {
        "session_id": "string"
    }

    Response:
    {
        "success": true,
        "data": {
            "anomaly_score": float,
            "risk_level": "string",
            "action": "string",
            "reasons": ["string"],
            ...
        }
    }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        if not session_id:
            return jsonify(ErrorResponse(
                error="Validation Error",
                detail="session_id is required"
            ).model_dump()), 400

        mismatch_response = current_session_only(session_id)
        if mismatch_response:
            return mismatch_response

        assessment = pipeline.force_assessment(session_id)

        if not assessment:
            return jsonify(ErrorResponse(
                error="Assessment Error",
                detail="Could not perform assessment. Model may not be trained or insufficient events."
            ).model_dump()), 400

        return success_response(assessment)

    except Exception as e:
        logger.error(f"Assessment error: {e}")
        return jsonify(ErrorResponse(
            error="Assessment Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/sessions/<session_id>/end', methods=['POST'])
@require_api_auth()
def end_session(session_id: str):
    """
    End a session and perform final assessment

    Response:
    {
        "success": true,
        "data": {
            "assessment": { ... }  // Final assessment if applicable
        }
    }
    """
    try:
        if not db.get_session(session_id):
            return jsonify(ErrorResponse(
                error="Not Found",
                detail="Session not found"
            ).model_dump()), 404

        mismatch_response = current_session_only(session_id)
        if mismatch_response:
            return mismatch_response

        assessment = pipeline.end_session(session_id)

        response_data = {}
        if assessment:
            response_data['assessment'] = assessment

        return success_response(response_data)

    except Exception as e:
        logger.error(f"Session end error: {e}")
        return jsonify(ErrorResponse(
            error="Session End Error",
            detail=str(e)
        ).model_dump()), 500

@app.route('/api/v1/sessions/beacon_end', methods=['POST'])
@require_api_auth(active_session=False)
def beacon_end():
    """Handle browser close via navigator.sendBeacon"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"success": False}), 400
            
        session_id = data.get('session_id')
        events = data.get('events', [])
        
        if not session_id:
            return jsonify({"success": False}), 400

        auth_session_id = g.auth_context.get('session_id')
        if auth_session_id != session_id:
            return jsonify({"success": False}), 403
            
        if events:
            # Re-use the pipeline process_events to save raw events
            pipeline.process_events(session_id, events)
            
        # End the session
        pipeline.end_session(session_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Beacon end error: {e}")
        return jsonify({"success": False}), 500


@app.route('/api/v1/sessions/<session_id>/force-end', methods=['POST'])
@require_api_auth(active_session=False)
def force_end_session(session_id: str):
    """Allow an authenticated operator to finalize any session from the database UI."""
    try:
        if not db.get_session(session_id):
            return jsonify(ErrorResponse(
                error="Not Found",
                detail="Session not found"
            ).model_dump()), 404

        assessment = pipeline.end_session(session_id)
        response_data = {}
        if assessment:
            response_data['assessment'] = assessment
        return success_response(response_data)
    except Exception as e:
        logger.error(f"Force end session error: {e}")
        return jsonify(ErrorResponse(
            error="Session End Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/logout', methods=['POST'])
def logout():
    """Clear the authenticated browser session."""
    flask_session.clear()
    return success_response({'logged_out': True})



@app.route('/api/v1/model/train', methods=['POST'])
@require_api_auth(active_session=False)
@validate_request(TrainModelRequest)
def train_model(data: TrainModelRequest):
    """
    Train the anomaly detection model

    Request:
    {
        "scope": "global|personal",
        "user_id": int (required when scope=personal),
        "selected_features": ["feature_name_1", "..."] (optional),
        "min_samples": int (default: 10)
    }

    Response:
    {
        "success": true,
        "data": {
            "success": bool,
            "message": "string",
            "samples_used": int,
            "model_version": "string",
            "metrics": { ... }
        }
    }
    """
    try:
        if data.scope == 'personal' and not data.user_id:
            return jsonify(ErrorResponse(
                error="Validation Error",
                detail="user_id is required when scope is personal"
            ).model_dump()), 400

        result = pipeline.train_model(
            scope=data.scope,
            user_id=data.user_id,
            selected_features=data.selected_features,
            min_samples=data.min_samples
        )

        if result['success']:
            logger.info(f"Model trained successfully with {result['samples_used']} samples")

        return success_response(result)

    except Exception as e:
        logger.error(f"Model training error: {e}")
        return jsonify(ErrorResponse(
            error="Model Training Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/users', methods=['GET'])
@require_api_auth(active_session=False)
def get_users():
    """Get users for personal model training selection."""
    try:
        users = db.get_all_users()
        return success_response({'users': users})
    except Exception as e:
        logger.error(f"Get users error: {e}")
        return jsonify(ErrorResponse(
            error="Database Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/users/<int:user_id>', methods=['DELETE'])
@require_api_auth(active_session=False)
def delete_user(user_id: int):
    """Delete a user and all related data."""
    try:
        deletion_summary = db.delete_user_and_related(user_id)
        if not deletion_summary:
            return jsonify(ErrorResponse(
                error="Not Found",
                detail="User not found"
            ).model_dump()), 404

        runtime_cleanup = pipeline.remove_user_runtime_state(
            user_id=user_id,
            remove_model_artifacts=True
        )

        response_data = {
            **deletion_summary,
            **runtime_cleanup
        }

        deleted_current_user = int(g.auth_context['user_id']) == int(user_id)
        response_data['logged_out'] = deleted_current_user
        if deleted_current_user:
            flask_session.clear()

        return success_response(response_data)
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return jsonify(ErrorResponse(
            error="Database Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/models/options', methods=['GET'])
@require_api_auth(active_session=False)
def get_model_options():
    """Get model options for reassessment (global + available personal models)."""
    try:
        users = db.get_all_users()
        options = [{
            'value': 'global',
            'label': 'Global Model',
            'scope': 'global',
            'user_id': None
        }]

        for user in users:
            user_id = int(user['id'])
            if pipeline.has_personal_model(user_id):
                options.append({
                    'value': f'personal:{user_id}',
                    'label': f"Personal Model - {user['username']}",
                    'scope': 'personal',
                    'user_id': user_id
                })

        return success_response({'options': options})
    except Exception as e:
        logger.error(f"Get model options error: {e}")
        return jsonify(ErrorResponse(
            error="Model Options Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/dashboard/stats', methods=['GET'])
@require_api_auth(active_session=False)
def get_dashboard_stats():
    """
    Get dashboard statistics

    Response:
    {
        "success": true,
        "data": {
            "total_users": int,
            "total_sessions": int,
            "total_events": int,
            "active_sessions": int,
            "high_risk_sessions_today": int,
            "medium_risk_sessions_today": int,
            "low_risk_sessions_today": int,
            "average_risk_score": float,
            "model_trained": bool,
            "top_users": [ ... ]
        }
    }
    """
    try:
        stats = db.get_dashboard_stats()
        stats['model_trained'] = pipeline.has_any_trained_model()

        return success_response(stats)

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return jsonify(ErrorResponse(
            error="Dashboard Stats Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/sessions/<session_id>/replay', methods=['GET'])
@require_api_auth(active_session=False)
def get_session_replay(session_id: str):
    """
    Get session data for replay visualization

    Response:
    {
        "success": true,
        "data": {
            "session_id": "string",
            "events": [ ... ],
            "features": { ... },
            "anomaly_score": float,
            "risk_level": "string"
        }
    }
    """
    try:
        # Get session from database
        session = db.get_session(session_id)
        if not session:
            return jsonify(ErrorResponse(
                error="Not Found",
                detail="Session not found"
            ).model_dump()), 404

        # Get events
        events = db.get_session_events(session_id)

        # Get features
        features = db.get_session_features(session_id)

        response_data = {
            'session_id': session_id,
            'user_id': session['user_id'],
            'start_time': session['start_time'],
            'end_time': session.get('end_time'),
            'events': events,
            'features': features or {},
            'anomaly_score': session.get('anomaly_score'),
            'risk_level': session.get('risk_level')
        }

        return success_response(response_data)

    except Exception as e:
        logger.error(f"Session replay error: {e}")
        return jsonify(ErrorResponse(
            error="Session Replay Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/sessions/<session_id>/reassess', methods=['POST'])
@require_api_auth(active_session=False)
@validate_request(SessionReassessRequest)
def reassess_session(data: SessionReassessRequest, session_id: str):
    """
    Reassess an existing session using selected model and persist result to DB.
    """
    try:
        if data.scope == 'personal' and not data.user_id:
            return jsonify(ErrorResponse(
                error="Validation Error",
                detail="model_user_id is required when model_scope is personal"
            ).model_dump()), 400

        result = pipeline.reassess_session(
            session_id=session_id,
            model_scope=data.scope,
            model_user_id=data.user_id,
            persist=True
        )
        return success_response(result)

    except ValueError as e:
        detail = str(e)
        status_code = 404 if "not found" in detail.lower() else 400
        return jsonify(ErrorResponse(
            error="Reassessment Error",
            detail=detail
        ).model_dump()), status_code

    except Exception as e:
        logger.error(f"Session reassessment error: {e}")
        return jsonify(ErrorResponse(
            error="Session Reassessment Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/sessions', methods=['GET'])
@require_api_auth(active_session=False)
def get_all_sessions():
    """Get all sessions from the database"""
    try:
        sessions = db.get_all_sessions_detailed()
        return success_response({'sessions': sessions})
    except Exception as e:
        logger.error(f"Get all sessions error: {e}")
        return jsonify(ErrorResponse(
            error="Database Error",
            detail=str(e)
        ).model_dump()), 500

@app.route('/api/v1/sessions/<session_id>', methods=['DELETE'])
@require_api_auth(active_session=False)
def delete_session(session_id):
    """Delete a session from the database"""
    try:
        success = db.delete_session(session_id)
        if success:
            return success_response({'deleted': True})
        else:
            return jsonify(ErrorResponse(
                error="Not Found",
                detail="Session not found"
            ).model_dump()), 404
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        return jsonify(ErrorResponse(
            error="Database Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/database/reset', methods=['POST'])
@require_api_auth(active_session=False)
def reset_database():
    """Delete all records from application database."""
    try:
        db.reset_database()
        pipeline.reset_runtime(remove_model_artifacts=True)
        flask_session.clear()
        return success_response({'reset': True})
    except Exception as e:
        logger.error(f"Database reset error: {e}")
        return jsonify(ErrorResponse(
            error="Database Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """
    Health check endpoint

    Response:
    {
        "success": true,
        "data": {
            "status": "healthy",
            "model_loaded": bool,
            "active_sessions": int
        }
    }
    """
    return success_response({
        'status': 'healthy',
        'model_loaded': pipeline.has_any_trained_model(),
        'active_sessions': db.get_active_session_count()
    })


# ==================== Startup ====================

def create_app():
    """Create and configure Flask app"""
    # Load model if available
    pipeline.load_model()
    restored_sessions = pipeline.restore_active_sessions()

    logger.info(f"Flask application initialized (restored {restored_sessions} active session(s))")

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG
    )
