from flask import Blueprint, jsonify, request

from app.services import campaign_service
from app.utils.decorators import require_auth
from app.utils.helpers import ServiceError, get_json_body, get_pagination, paginate

bp = Blueprint('campaigns', __name__, url_prefix='/api/campaigns')


@bp.post('')
@require_auth
def create_campaign():
    data = get_json_body()
    campaign = campaign_service.create_campaign(
        request.business_id, data.get('template_id'), data.get('segment_id'), data.get('name'),
        subject_line=data.get('subject_line'), subject_variants=data.get('subject_variants'),
    )
    if data.get('scheduled_time'):
        campaign = campaign_service.schedule_campaign(request.business_id, campaign.id, data['scheduled_time'])
    return jsonify(campaign.to_dict()), 201


@bp.get('')
@require_auth
def list_campaigns():
    page, per_page = get_pagination()
    query = campaign_service.list_campaigns(request.business_id, request.args.get('status'))
    return jsonify(paginate(query, page, per_page))


@bp.get('/<campaign_id>')
@require_auth
def get_campaign(campaign_id):
    return jsonify(campaign_service.get_campaign(request.business_id, campaign_id).to_dict())


@bp.put('/<campaign_id>')
@require_auth
def update_campaign(campaign_id):
    campaign = campaign_service.update_campaign(request.business_id, campaign_id, get_json_body())
    return jsonify(campaign.to_dict())


@bp.delete('/<campaign_id>')
@require_auth
def delete_campaign(campaign_id):
    campaign_service.delete_campaign(request.business_id, campaign_id)
    return jsonify({'success': True})


@bp.post('/<campaign_id>/send')
@require_auth
def send_campaign(campaign_id):
    data = get_json_body()
    return jsonify(campaign_service.send_campaign_now(request.business_id, campaign_id, data.get('segment_id')))


@bp.post('/<campaign_id>/schedule')
@require_auth
def schedule_campaign(campaign_id):
    scheduled_time = get_json_body().get('scheduled_time')
    if not scheduled_time:
        raise ServiceError('scheduled_time is required (ISO-8601)')
    return jsonify(campaign_service.schedule_campaign(request.business_id, campaign_id, scheduled_time).to_dict())


@bp.post('/<campaign_id>/pause')
@require_auth
def pause_campaign(campaign_id):
    return jsonify(campaign_service.pause_campaign(request.business_id, campaign_id).to_dict())


@bp.post('/<campaign_id>/resume')
@require_auth
def resume_campaign(campaign_id):
    return jsonify(campaign_service.resume_campaign(request.business_id, campaign_id).to_dict())


@bp.post('/<campaign_id>/test')
@require_auth
def send_test(campaign_id):
    data = get_json_body()
    return jsonify(campaign_service.send_test_email(request.business_id, campaign_id, data.get('emails'),
                                                    data.get('sample_data')))


@bp.get('/<campaign_id>/analytics')
@require_auth
def campaign_analytics(campaign_id):
    return jsonify(campaign_service.get_campaign_analytics(request.business_id, campaign_id))
