from flask import Blueprint, jsonify, request

from app.services import automation_service
from app.utils.decorators import require_auth
from app.utils.helpers import get_json_body, get_pagination, paginate

bp = Blueprint('automations', __name__, url_prefix='/api/automations')


@bp.post('')
@require_auth
def create_automation():
    data = get_json_body()
    automation = automation_service.create_automation(
        request.business_id, data.get('name'), data.get('trigger_type'), data.get('workflow'),
        trigger_value=data.get('trigger_value'), status=data.get('status', 'active'),
    )
    return jsonify(automation.to_dict()), 201


@bp.get('')
@require_auth
def list_automations():
    page, per_page = get_pagination()
    query = automation_service.list_automations(request.business_id, request.args.get('status'),
                                                request.args.get('trigger_type'))
    return jsonify(paginate(query, page, per_page))


@bp.post('/events')
@require_auth
def fire_event():
    """Fire a custom event for a subscriber: {"event", "subscriber_id"|"email"}."""
    data = get_json_body()
    return jsonify(automation_service.fire_custom_event(
        request.business_id, data.get('event'), data.get('subscriber_id'), data.get('email')))


@bp.get('/<automation_id>')
@require_auth
def get_automation(automation_id):
    automation = automation_service.get_automation(request.business_id, automation_id)
    return jsonify(automation.to_dict(include_stats=True))


@bp.get('/<automation_id>/instances')
@require_auth
def list_instances(automation_id):
    page, per_page = get_pagination()
    query = automation_service.list_instances(request.business_id, automation_id, request.args.get('status'))
    return jsonify(paginate(query, page, per_page))


@bp.put('/<automation_id>')
@require_auth
def update_automation(automation_id):
    automation = automation_service.update_automation(request.business_id, automation_id, get_json_body())
    return jsonify(automation.to_dict())


@bp.delete('/<automation_id>')
@require_auth
def delete_automation(automation_id):
    automation_service.delete_automation(request.business_id, automation_id)
    return jsonify({'success': True})


@bp.post('/<automation_id>/activate')
@require_auth
def activate(automation_id):
    return jsonify(automation_service.set_status(request.business_id, automation_id, 'active').to_dict())


@bp.post('/<automation_id>/deactivate')
@require_auth
def deactivate(automation_id):
    return jsonify(automation_service.set_status(request.business_id, automation_id, 'inactive').to_dict())
