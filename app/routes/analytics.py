from flask import Blueprint, jsonify, request

from app.services import analytics_service
from app.utils.decorators import require_auth
from app.utils.helpers import get_pagination, paginate

bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')


@bp.get('/overview')
@require_auth
def overview():
    return jsonify(analytics_service.get_business_overview(request.business_id))


@bp.get('/engagement')
@require_auth
def engagement():
    return jsonify(analytics_service.get_engagement_metrics(request.business_id, request.args.get('days', 30)))


@bp.get('/subscribers')
@require_auth
def subscriber_growth():
    return jsonify(analytics_service.get_subscriber_growth(request.business_id, request.args.get('days', 30)))


@bp.get('/campaigns')
@require_auth
def campaigns():
    return jsonify(analytics_service.get_campaign_comparison(request.business_id, request.args.get('limit', 20)))


@bp.get('/email-logs')
@require_auth
def email_logs():
    page, per_page = get_pagination()
    query = analytics_service.email_logs_query(request.business_id, request.args)
    return jsonify(paginate(query, page, per_page))
