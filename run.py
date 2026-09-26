"""
NEXUS IoT - Entry Point
Usage:
  Development: python run.py
  Production:  gunicorn -w 4 -b 0.0.0.0:5000 run:app
"""
import os
import signal
import sys
import logging

from app import create_app, config, logger

app = create_app()


def _signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down...")
    from app.background import stop_background_tasks
    stop_background_tasks()
    sys.exit(0)


if __name__ == '__main__':
    # Signal handler hanya di main process
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
    except ValueError:
        pass

    logger.info("=" * 60)
    logger.info("NEXUS IoT starting (dev mode)...")
    logger.info(f"   Host    : {config.HOST}")
    logger.info(f"   Port    : {config.PORT}")
    logger.info(f"   Debug   : {config.DEBUG}")
    logger.info(f"   Database: {config.DB_PATH}")
    logger.info(f"   URL     : http://{config.HOST}:{config.PORT}")
    logger.info("=" * 60)

    try:
        app.run(
            host=config.HOST,
            port=config.PORT,
            debug=config.DEBUG,
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
        from app.background import stop_background_tasks
        stop_background_tasks()