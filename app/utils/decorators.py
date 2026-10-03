import threading
import time
from collections import defaultdict, deque
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from app import db
from app.utils.helpers import client_ip


def create_token(business, token_type='access'):
    """Create a signed JWT for a business account."""
    if token_type == 'access':
        lifetime = current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    else:
        lifetime = current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
    now = int(time.time())
    payload = {
        'business_id': business.id,
        'email': business.account_email,
        'type': token_type,
        # token_version lets a password change / logout revoke outstanding tokens
        'ver': business.token_version or 0,
        'iat': now,
        'exp': now + int(lifetime.total_seconds()),
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')


def decode_token(token, expected_type='access'):
    payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
    if payload.get('type') != expected_type:
        raise jwt.InvalidTokenError('Wrong token type')
    return payload


def _unauthorized(message='Invalid or expired token'):
    return jsonify({'error': message}), 401


def require_auth(f):
    """Authenticate with a JWT bearer token or an X-API-Key header.

    On success sets request.business_id / request.user_email and g.business.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.models import Business

        api_key = request.headers.get('X-API-Key')
        auth_header = request.headers.get('Authorization', '')

        if api_key:
            business = Business.query.filter_by(api_key=api_key).first()
            if business is None:
                return _unauthorized('Invalid API key')
        elif auth_header:
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                return _unauthorized('Authorization header must be "Bearer <token>"')
            try:
                payload = decode_token(parts[1], 'access')
            except jwt.ExpiredSignatureError:
                return _unauthorized('Token has expired')
            except jwt.InvalidTokenError:
                return _unauthorized()
            business = db.session.get(Business, str(payload.get('business_id')))
            if business is None or payload.get('ver', 0) != (business.token_version or 0):
                return _unauthorized()
        else:
            return _unauthorized('Missing authorization header')

        request.business_id = business.id
        request.user_email = business.account_email
        g.business = business
        return f(*args, **kwargs)
    return decorated_function


class _SlidingWindowLimiter:
    """Tiny in-process rate limiter (per worker). Use a shared store such as
    Redis for strict limits across multiple gunicorn workers."""

    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key, limit, window_seconds=60):
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


_limiter = _SlidingWindowLimiter()


def rate_limit(config_key='AUTH_RATE_LIMIT_PER_MINUTE'):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            limit = current_app.config.get(config_key, 20)
            key = f'{f.__name__}:{client_ip()}'
            if not _limiter.allow(key, limit):
                return jsonify({'error': 'Too many requests, slow down'}), 429
            return f(*args, **kwargs)
        return wrapped
    return decorator
