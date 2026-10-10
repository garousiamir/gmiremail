from flask import Blueprint, g, jsonify

from app.services import business_service, smtp_service
from app.utils.decorators import rate_limit, require_auth
from app.utils.helpers import get_json_body

bp = Blueprint('businesses', __name__, url_prefix='/api/businesses')


@bp.get('/me')
@require_auth
def get_me():
    from app.services.backup_service import is_admin
    return jsonify({**g.business.to_dict(), 'is_admin': is_admin(g.business)})


@bp.put('/me')
@require_auth
def update_me():
    business = business_service.update_business(g.business, get_json_body())
    return jsonify(business.to_dict())


@bp.delete('/me')
@require_auth
@rate_limit()
def delete_me():
    """Delete this account and all its data. Body: {"password": "...", "confirm": "DELETE"}."""
    data = get_json_body()
    business_service.delete_business(g.business, data.get('password'), data.get('confirm'))
    return jsonify({'success': True})


@bp.get('/stats')
@require_auth
def stats():
    return jsonify(business_service.get_stats(g.business))


@bp.post('/me/api-key/rotate')
@require_auth
def rotate_api_key():
    return jsonify({'api_key': business_service.rotate_api_key(g.business)})


@bp.post('/me/smtp/test')
@require_auth
def test_smtp():
    ok, message = smtp_service.test_connection(g.business)
    if not ok:
        # 'error' is what the dashboard shows; keep 'message' for API clients
        return jsonify({'success': False, 'error': message, 'message': message}), 502
    return jsonify({'success': True, 'message': message})
