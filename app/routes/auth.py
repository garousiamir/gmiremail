import jwt
from flask import Blueprint, g, jsonify

from app import db
from app.models import Business
from app.services import business_service
from app.utils.decorators import create_token, decode_token, rate_limit, require_auth
from app.utils.helpers import ServiceError, get_json_body

bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def _token_response(business, status=200):
    return jsonify({
        'access_token': create_token(business, 'access'),
        'refresh_token': create_token(business, 'refresh'),
        'token_type': 'Bearer',
        'business': business.to_dict(),
    }), status


@bp.post('/register')
@rate_limit()
def register():
    business = business_service.register_business(get_json_body())
    return _token_response(business, 201)


@bp.post('/login')
@rate_limit()
def login():
    data = get_json_body()
    business = business_service.authenticate(data.get('email'), data.get('password'))
    return _token_response(business)


@bp.post('/refresh')
@rate_limit()
def refresh():
    token = get_json_body().get('refresh_token')
    if not token:
        raise ServiceError('refresh_token is required')
    try:
        payload = decode_token(token, 'refresh')
    except jwt.ExpiredSignatureError:
        raise ServiceError('Refresh token has expired', 401)
    except jwt.InvalidTokenError:
        raise ServiceError('Invalid refresh token', 401)
    business = db.session.get(Business, str(payload.get('business_id')))
    if business is None or payload.get('ver', 0) != (business.token_version or 0):
        raise ServiceError('Invalid refresh token', 401)
    return jsonify({'access_token': create_token(business, 'access'), 'token_type': 'Bearer'})


@bp.post('/logout')
@require_auth
def logout():
    """Revoke every outstanding access/refresh token for this account."""
    business_service.revoke_tokens(g.business)
    return jsonify({'success': True})
