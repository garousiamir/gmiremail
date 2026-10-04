"""Server-owner endpoints (full backups)."""
import os

from flask import Blueprint, g, jsonify, send_file

from app.services import backup_service
from app.utils.decorators import rate_limit, require_auth
from app.utils.helpers import ServiceError, get_json_body

bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def _require_admin():
    if not backup_service.is_admin(g.business):
        raise ServiceError('Only the server owner can do this', 403)


@bp.get('/backup')
@require_auth
def backup_info():
    _require_admin()
    return jsonify({'counts': backup_service.summary()})


@bp.post('/backup')
@require_auth
@rate_limit()
def download_backup():
    """Stream a full backup. Requires the account password again."""
    _require_admin()
    if not g.business.check_password(get_json_body().get('password') or ''):
        raise ServiceError('Password is incorrect', 403)
    path, _ = backup_service.create_backup_tempfile()
    response = send_file(path, mimetype='application/gzip', as_attachment=True,
                         download_name=backup_service.backup_filename(), max_age=0)
    response.headers['Cache-Control'] = 'no-store'
    response.call_on_close(lambda: os.path.exists(path) and os.unlink(path))
    return response
