"""
Entry Point for Real-Time Login Anomaly Detection System
"""

import sys
import logging
from pathlib import Path

# Add server directory to path
server_dir = Path(__file__).parent / "server"
sys.path.insert(0, str(server_dir))

from server.app import create_app

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Main entry point"""
    logger.info("Starting Real-Time Login Anomaly Detection System...")

    # Create Flask app
    app = create_app()

    # Run the application
    try:
        from server.config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG
        logger.info(f"Server running on http://{FLASK_HOST}:{FLASK_PORT}")
        app.run(
            host=FLASK_HOST,
            port=FLASK_PORT,
            debug=FLASK_DEBUG
        )
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
