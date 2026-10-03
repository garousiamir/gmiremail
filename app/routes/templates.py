from flask import Blueprint, jsonify, request

from app.services import template_service
from app.utils.decorators import require_auth
from app.utils.helpers import get_json_body, get_pagination, paginate

bp = Blueprint('templates', __name__, url_prefix='/api/templates')


@bp.post('')
@require_auth
def create_template():
    data = get_json_body()
    template = template_service.create_template(
        request.business_id, data.get('name'), data.get('subject_line'), data.get('html_content'),
        text=data.get('text_content'), preview_text=data.get('preview_text'),
        variables=data.get('template_variables'),
    )
    return jsonify(template.to_dict()), 201


@bp.get('')
@require_auth
def list_templates():
    page, per_page = get_pagination()
    query = template_service.list_templates(request.business_id, request.args.get('search'))
    return jsonify(paginate(query, page, per_page, lambda t: t.to_dict(include_content=False)))


@bp.get('/library')
@require_auth
def template_library():
    return jsonify({'templates': template_service.library()})


@bp.post('/library/<key>')
@require_auth
def create_from_library(key):
    template = template_service.create_from_library(request.business_id, key, get_json_body().get('name'))
    return jsonify(template.to_dict()), 201


@bp.get('/<template_id>')
@require_auth
def get_template(template_id):
    return jsonify(template_service.get_template(request.business_id, template_id).to_dict())


@bp.put('/<template_id>')
@require_auth
def update_template(template_id):
    template = template_service.update_template(request.business_id, template_id, get_json_body())
    return jsonify(template.to_dict())


@bp.delete('/<template_id>')
@require_auth
def delete_template(template_id):
    template_service.delete_template(request.business_id, template_id)
    return jsonify({'success': True})


@bp.post('/<template_id>/preview')
@require_auth
def preview_template(template_id):
    data = get_json_body()
    sample = data.get('sample_data', data)
    return jsonify(template_service.preview_template(request.business_id, template_id, sample))
