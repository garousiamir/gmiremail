import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import HTTPException

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name=None, start_scheduler=None, config_overrides=None):
    """Application factory"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    from app.config import config

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))
    app.config.update(config_overrides or {})

    logging.basicConfig(
        level=logging.DEBUG if app.debug else logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    )

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    # Number of reverse proxies (nginx) in front of the app. Lets Flask see the
    # real client IP and https scheme from X-Forwarded-* headers.
    trusted_proxies = app.config.get('TRUSTED_PROXIES', 0)
    if trusted_proxies:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_proxies, x_proto=trusted_proxies,
                                x_host=trusted_proxies)

    # Register blueprints
    from app.routes import (auth, businesses, subscribers, campaigns, templates,
                            automations, segments, analytics, tracking, dashboard, admin)

    app.register_blueprint(auth.bp)
    app.register_blueprint(businesses.bp)
    app.register_blueprint(subscribers.bp)
    app.register_blueprint(campaigns.bp)
    app.register_blueprint(tracking.bp)
    app.register_blueprint(templates.bp)
    app.register_blueprint(automations.bp)
    app.register_blueprint(segments.bp)
    app.register_blueprint(analytics.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(admin.bp)

    from app.cli import register_cli
    register_cli(app)

    _register_error_handlers(app)

    @app.get('/health')
    def health():
        return jsonify({'status': 'ok'})

    # Create database tables
    if app.config.get('AUTO_CREATE_TABLES', True):
        with app.app_context():
            from app import models  # noqa: F401  (register models)
            _create_tables()

    # Initialize background tasks
    if start_scheduler is None:
        start_scheduler = app.config.get('ENABLE_SCHEDULER', False)
    if start_scheduler:
        from app.tasks.scheduled_tasks import init_scheduler
        init_scheduler(app)

    return app


def _create_tables(attempts=5):
    """create_all() that tolerates several gunicorn workers booting at once:
    a worker that loses the race sees "already exists" and simply retries."""
    import time

    from sqlalchemy.exc import DatabaseError

    for attempt in range(attempts):
        try:
            db.create_all()
            return
        except DatabaseError:
            db.session.rollback()
            if attempt == attempts - 1:
                raise
            time.sleep(0.2 * (attempt + 1))


def _register_error_handlers(app):
    from app.utils.helpers import ServiceError

    @app.errorhandler(ServiceError)
    def handle_service_error(err):
        body = {'error': err.message}
        if err.details:
            body['details'] = err.details
        return jsonify(body), err.status_code

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        return jsonify({'error': err.description or err.name}), err.code

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        db.session.rollback()
        app.logger.exception('Unhandled error')
        return jsonify({'error': 'Internal server error'}), 500
