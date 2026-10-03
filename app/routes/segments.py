from flask import Blueprint, jsonify, request

from app.services import segment_service
from app.utils.decorators import require_auth
from app.utils.helpers import get_json_body, get_pagination, paginate

bp = Blueprint('segments', __name__, url_prefix='/api/segments')


@bp.post('')
@require_auth
def create_segment():
    data = get_json_body()
    segment = segment_service.create_segment(request.business_id, data.get('name'), data.get('filter_rules'),
                                             data.get('description'))
    return jsonify(segment.to_dict()), 201


@bp.get('')
@require_auth
def list_segments():
    page, per_page = get_pagination()
    return jsonify(paginate(segment_service.list_segments(request.business_id), page, per_page))


@bp.post('/preview')
@require_auth
def preview_segment():
    """Count + sample subscribers for unsaved filter rules."""
    return jsonify(segment_service.preview_rules(request.business_id, get_json_body().get('filter_rules')))


@bp.get('/<segment_id>')
@require_auth
def get_segment(segment_id):
    return jsonify(segment_service.get_segment(request.business_id, segment_id).to_dict())


@bp.get('/<segment_id>/subscribers')
@require_auth
def segment_subscribers(segment_id):
    page, per_page = get_pagination()
    query = segment_service.get_segment_subscribers(request.business_id, segment_id)
    return jsonify(paginate(query, page, per_page))


@bp.put('/<segment_id>')
@require_auth
def update_segment(segment_id):
    segment = segment_service.update_segment(request.business_id, segment_id, get_json_body())
    return jsonify(segment.to_dict())


@bp.delete('/<segment_id>')
@require_auth
def delete_segment(segment_id):
    segment_service.delete_segment(request.business_id, segment_id)
    return jsonify({'success': True})


@bp.get('/<segment_id>/count')
@require_auth
def count_segment(segment_id):
    return jsonify(segment_service.count_segment(request.business_id, segment_id))
