from flask import Blueprint, Response, jsonify, request

from app.services import analytics_service, subscriber_service
from app.utils.decorators import require_auth
from app.utils.helpers import ServiceError, get_json_body, get_pagination, paginate, utcnow

bp = Blueprint('subscribers', __name__, url_prefix='/api/subscribers')


def _filters(source):
    return {key: source.get(key) for key in ('status', 'search', 'tag', 'segment_id', 'sort') if source.get(key)}


@bp.post('')
@require_auth
def create_subscriber():
    data = get_json_body()
    subscriber = subscriber_service.add_subscriber(
        request.business_id, data.get('email'), data.get('first_name'), data.get('last_name'),
        data.get('custom_fields'), tags=data.get('tags'), status=data.get('status', 'active'),
    )
    return jsonify(subscriber.to_dict()), 201


@bp.post('/bulk')
@require_auth
def bulk_import():
    """Accepts a JSON body {"subscribers": [...]} , a multipart "file" CSV
    upload, or a raw text/csv body."""
    options = request.args
    raw_csv = None
    records = None
    if 'file' in request.files:
        raw_csv = request.files['file'].read().decode('utf-8-sig', errors='replace')
        options = request.form
    elif request.mimetype == 'text/csv':
        raw_csv = request.get_data(as_text=True)
    else:
        data = get_json_body()
        records = data.get('subscribers')
        options = data
    rows = subscriber_service.parse_import_payload(raw_csv=raw_csv, records=records)

    def flag(name):
        value = options.get(name, False)
        return value if isinstance(value, bool) else str(value).lower() in ('1', 'true', 'yes')

    result = subscriber_service.bulk_import(
        request.business_id, rows, update_existing=flag('update_existing'),
        trigger_automations=flag('trigger_automations'),
    )
    return jsonify(result), 201


@bp.get('')
@require_auth
def list_subscribers():
    page, per_page = get_pagination()
    query = subscriber_service.get_subscribers(request.business_id, _filters(request.args))
    return jsonify(paginate(query, page, per_page))


@bp.get('/<subscriber_id>')
@require_auth
def get_subscriber(subscriber_id):
    return jsonify(subscriber_service.get_subscriber(request.business_id, subscriber_id).to_dict())


@bp.get('/<subscriber_id>/activity')
@require_auth
def subscriber_activity(subscriber_id):
    return jsonify(analytics_service.subscriber_activity(request.business_id, subscriber_id))


@bp.put('/<subscriber_id>')
@require_auth
def update_subscriber(subscriber_id):
    subscriber = subscriber_service.update_subscriber(request.business_id, subscriber_id, get_json_body())
    return jsonify(subscriber.to_dict())


@bp.delete('/<subscriber_id>')
@require_auth
def delete_subscriber(subscriber_id):
    subscriber_service.delete_subscriber(request.business_id, subscriber_id)
    return jsonify({'success': True})


@bp.put('/<subscriber_id>/status')
@require_auth
def change_status(subscriber_id):
    status = get_json_body().get('status')
    if not status:
        raise ServiceError('status is required')
    subscriber = subscriber_service.change_status(request.business_id, subscriber_id, status)
    return jsonify(subscriber.to_dict())


@bp.post('/export')
@require_auth
def export_subscribers():
    data = get_json_body()
    fmt = data.get('format', 'csv')
    if fmt not in ('csv', 'json'):
        raise ServiceError('format must be "csv" or "json"')
    result = subscriber_service.export_subscribers(request.business_id, _filters(data), format=fmt)
    if fmt == 'json':
        return jsonify({'subscribers': result, 'total': len(result)})
    filename = f'subscribers-{utcnow():%Y%m%d-%H%M%S}.csv'
    return Response(result, mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})
