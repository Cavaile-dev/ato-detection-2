"""
Flask API Application
REST API for Real-Time Login Anomaly Detection System
"""

import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template
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
    LOG_FILE
)
from server.database import db
from server.pipeline import pipeline
from server.schemas import (
    LoginRequest,
    SessionStartRequest,
    EventsSubmitRequest,
    TrainModelRequest,
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


def success_response(data):
    """Create success response"""
    return jsonify({
        'success': True,
        'data': data,
        'timestamp': datetime.utcnow().isoformat()
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
            "baseline_completed": bool,
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

        response_data = {
            'user_id': user['id'],
            'username': user['username'],
            'baseline_completed': bool(user.get('baseline_completed', 0)),
            'baseline_count': user.get('baseline_count', 0),
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
            "is_baseline": bool
        }
    }
    """
    try:
        session_id = pipeline.start_session(
            user_id=data.user_id,
            ip_address=data.ip_address or request.remote_addr,
            device_fingerprint=data.device_fingerprint,
            user_agent=request.headers.get('User-Agent')
        )

        session_state = pipeline.get_session(session_id)

        response_data = {
            'session_id': session_id,
            'is_baseline': session_state.is_baseline if session_state else True
        }

        return success_response(response_data)

    except Exception as e:
        logger.error(f"Session start error: {e}")
        return jsonify(ErrorResponse(
            error="Session Start Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/events', methods=['POST'])
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


@app.route('/api/v1/model/train', methods=['POST'])
@validate_request(TrainModelRequest)
def train_model(data: TrainModelRequest):
    """
    Train the anomaly detection model

    Request:
    {
        "user_id": int (optional),
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
        result = pipeline.train_model(user_id=data.user_id)

        if result['success']:
            logger.info(f"Model trained successfully with {result['samples_used']} samples")

        return success_response(result)

    except Exception as e:
        logger.error(f"Model training error: {e}")
        return jsonify(ErrorResponse(
            error="Model Training Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/dashboard/stats', methods=['GET'])
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
        stats['active_sessions'] = len(pipeline.get_active_sessions())
        stats['model_trained'] = pipeline.ensemble_model.is_model_trained()

        return success_response(stats)

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return jsonify(ErrorResponse(
            error="Dashboard Stats Error",
            detail=str(e)
        ).model_dump()), 500


@app.route('/api/v1/sessions/<session_id>/replay', methods=['GET'])
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


@app.route('/api/v1/sessions', methods=['GET'])
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
        'model_loaded': pipeline.ensemble_model.is_model_trained(),
        'active_sessions': len(pipeline.get_active_sessions())
    })


# ==================== Startup ====================

def create_app():
    """Create and configure Flask app"""
    # Load model if available
    pipeline.load_model()

    logger.info("Flask application initialized")

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG
    )
