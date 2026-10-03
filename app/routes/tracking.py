"""Public (unauthenticated) endpoints hit by email clients."""
import html

from flask import Blueprint, Response, abort, redirect, request

from app import db
from app.models import EmailLog
from app.services import subscriber_service, tracking_service
from app.utils.helpers import client_ip

bp = Blueprint('tracking', __name__)

NO_CACHE = {'Cache-Control': 'no-store, no-cache, must-revalidate, private', 'Pragma': 'no-cache'}


@bp.get('/t/pixel')
def open_pixel():
    email_log_id = request.args.get('email_log_id')
    if email_log_id:
        try:
            tracking_service.track_email_open(email_log_id, request.user_agent.string, client_ip())
        except Exception:  # noqa: BLE001 - never fail to serve the pixel
            db.session.rollback()
    return Response(tracking_service.PIXEL_GIF, mimetype='image/gif', headers=NO_CACHE)


@bp.get('/t/click')
def click():
    email_log_id = request.args.get('email_log_id', '')
    url = request.args.get('url', '')
    # The signature stops this endpoint from being used as an open redirect
    if not tracking_service.verify(request.args.get('sig'), 'click', email_log_id, url) \
            or not tracking_service.is_safe_redirect(url):
        abort(400, 'Invalid tracking link')
    try:
        tracking_service.track_email_click(email_log_id, url, request.user_agent.string, client_ip())
    except Exception:  # noqa: BLE001 - always redirect the reader
        db.session.rollback()
    return redirect(url, code=302)


def _page(title, body, status=200):
    page = (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>'
            '<style>body{font-family:Arial,sans-serif;max-width:480px;margin:64px auto;padding:0 16px;'
            'color:#18181b}button{padding:10px 20px;font-size:16px;cursor:pointer}</style></head>'
            f'<body>{body}</body></html>')
    return Response(page, status=status, mimetype='text/html', headers=NO_CACHE)


def _load_log(email_log_id):
    if not tracking_service.verify(request.args.get('sig'), 'unsubscribe', email_log_id):
        return None
    return db.session.get(EmailLog, email_log_id)


@bp.get('/u/<email_log_id>')
def unsubscribe_page(email_log_id):
    """Confirmation page. A GET never unsubscribes, so link scanners that
    prefetch URLs cannot unsubscribe people by accident."""
    log = _load_log(email_log_id)
    if log is None:
        return _page('Invalid link', '<h1>Invalid unsubscribe link</h1>', 400)
    business = log.business
    if log.subscriber.status == 'unsubscribed':
        return _page('Unsubscribed', f'<h1>You are unsubscribed</h1><p>{html.escape(log.recipient_email)} '
                                     f'will no longer receive emails from {html.escape(business.name)}.</p>')
    sig = html.escape(request.args.get('sig', ''), quote=True)
    return _page('Unsubscribe', (
        f'<h1>Unsubscribe</h1><p>Stop receiving emails from {html.escape(business.name)} at '
        f'<strong>{html.escape(log.recipient_email)}</strong>?</p>'
        f'<form method="post" action="?sig={sig}"><button type="submit">Unsubscribe</button></form>'))


@bp.post('/u/<email_log_id>')
def unsubscribe(email_log_id):
    """Form submit and RFC 8058 one-click (List-Unsubscribe-Post) endpoint."""
    log = _load_log(email_log_id)
    if log is None:
        return _page('Invalid link', '<h1>Invalid unsubscribe link</h1>', 400)
    subscriber_service.unsubscribe(log.subscriber, email_log=log)
    return _page('Unsubscribed', f'<h1>You have been unsubscribed</h1><p>{html.escape(log.recipient_email)} '
                                 f'will no longer receive emails from {html.escape(log.business.name)}.</p>')
