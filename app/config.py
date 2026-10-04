import os
from datetime import timedelta


def _bool(name, default):
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def _database_url():
    url = os.getenv('DATABASE_URL', 'postgresql://localhost/email_marketing_dev')
    # Some hosts still hand out the deprecated "postgres://" scheme
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    AUTO_CREATE_TABLES = _bool('AUTO_CREATE_TABLES', True)

    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=int(os.getenv('JWT_EXPIRATION', 900)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(seconds=int(os.getenv('JWT_REFRESH_EXPIRATION', 7 * 24 * 3600)))

    # Email Settings
    SMTP_HOST = os.getenv('DEFAULT_SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('DEFAULT_SMTP_PORT', 587))
    SMTP_TLS = _bool('DEFAULT_SMTP_TLS', True)
    SMTP_TIMEOUT = int(os.getenv('SMTP_TIMEOUT', 30))

    # Application
    MAX_EMAIL_BATCH_SIZE = int(os.getenv('MAX_EMAIL_BATCH_SIZE', 100))
    QUEUE_PROCESSING_INTERVAL = int(os.getenv('QUEUE_PROCESSING_INTERVAL', 10))
    MAX_RETRY_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', 3))
    DAILY_EMAIL_LIMIT = int(os.getenv('DAILY_EMAIL_LIMIT', 10000))
    MAX_EMAILS_PER_MINUTE = int(os.getenv('MAX_EMAILS_PER_MINUTE', 60))
    MAX_SOFT_BOUNCES = int(os.getenv('MAX_SOFT_BOUNCES', 3))
    EMAIL_LOG_RETENTION_DAYS = int(os.getenv('EMAIL_LOG_RETENTION_DAYS', 365))

    # Background scheduler
    ENABLE_SCHEDULER = _bool('ENABLE_SCHEDULER', True)

    # Tracking
    ENABLE_TRACKING = _bool('ENABLE_TRACKING', True)
    TRACKING_DOMAIN = os.getenv('TRACKING_DOMAIN', 'http://localhost:5000').rstrip('/')

    # Reverse proxies in front of the app (1 behind nginx, 0 when exposed directly)
    TRUSTED_PROXIES = int(os.getenv('TRUSTED_PROXIES', 0))

    # API rate limiting for auth endpoints (per IP, per minute)
    AUTH_RATE_LIMIT_PER_MINUTE = int(os.getenv('AUTH_RATE_LIMIT_PER_MINUTE', 20))

    # Pagination
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv('TEST_DATABASE_URL', 'sqlite:///:memory:')
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SECRET_KEY = 'test-secret-key'
    JWT_SECRET_KEY = 'test-jwt-secret'
    ENABLE_SCHEDULER = False
    TRACKING_DOMAIN = 'http://localhost'
    MAX_EMAILS_PER_MINUTE = 10000
    AUTH_RATE_LIMIT_PER_MINUTE = 10000


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
