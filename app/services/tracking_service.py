"""Open / click tracking and signed public links (click + unsubscribe)."""
import hashlib
import hmac
from urllib.parse import urlencode, urlparse

from flask import current_app

from app import db
from app.models import EmailEvent, EmailLog
from app.utils.constants import EMAIL_LOG_PROGRESSION
from app.utils.helpers import utcnow

# 1x1 transparent GIF
PIXEL_GIF = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00'
             b',\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')


def sign(*parts):
    message = '|'.join(str(p) for p in parts).encode()
    return hmac.new(current_app.config['SECRET_KEY'].encode(), message, hashlib.sha256).hexdigest()[:32]


def verify(signature, *parts):
    return bool(signature) and hmac.compare_digest(sign(*parts), str(signature))


def _base():
    return current_app.config['TRACKING_DOMAIN']


def pixel_url(email_log_id):
    return f"{_base()}/t/pixel?{urlencode({'email_log_id': email_log_id})}"


def click_url(email_log_id, url):
    query = urlencode({'email_log_id': email_log_id, 'url': url, 'sig': sign('click', email_log_id, url)})
    return f'{_base()}/t/click?{query}'


def unsubscribe_url(email_log_id):
    return f"{_base()}/u/{email_log_id}?{urlencode({'sig': sign('unsubscribe', email_log_id)})}"


def is_safe_redirect(url):
    parsed = urlparse(url or '')
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def _advance_status(email_log, status):
    current = EMAIL_LOG_PROGRESSION.get(email_log.status)
    if current is not None and EMAIL_LOG_PROGRESSION[status] > current:
        email_log.status = status


def track_email_open(email_log_id, user_agent=None, ip_address=None):
    """Record an open. Returns the EmailLog (or None if unknown)."""
    email_log = db.session.get(EmailLog, str(email_log_id))
    if email_log is None or email_log.sent_at is None:
        return None
    now = utcnow()
    first_open = email_log.opened_at is None
    email_log.open_count = (email_log.open_count or 0) + 1
    if first_open:
        email_log.opened_at = now
    _advance_status(email_log, 'opened')
    subscriber = email_log.subscriber
    subscriber.total_opens = (subscriber.total_opens or 0) + 1
    subscriber.last_opened_at = now
    if first_open and email_log.campaign is not None:
        email_log.campaign.total_opens = (email_log.campaign.total_opens or 0) + 1
    db.session.add(EmailEvent(
        business_id=email_log.business_id, email_log_id=email_log.id, campaign_id=email_log.campaign_id,
        subscriber_id=email_log.subscriber_id, event_type='open',
        user_agent=(user_agent or '')[:500], ip_address=ip_address,
    ))
    db.session.commit()

    if first_open:
        from app.services import automation_service
        automation_service.handle_event(email_log.business_id, 'email_opened', subscriber, email_log=email_log)
    return email_log


def track_email_click(email_log_id, url, user_agent=None, ip_address=None):
    """Record a click (also counts as an open if the pixel was blocked)."""
    email_log = db.session.get(EmailLog, str(email_log_id))
    if email_log is None or email_log.sent_at is None:
        return None
    now = utcnow()
    if email_log.opened_at is None:
        # Image blocking hides opens; a click proves the email was opened
        track_email_open(email_log_id, user_agent, ip_address)
    first_click = email_log.clicked_at is None
    email_log.click_count = (email_log.click_count or 0) + 1
    if first_click:
        email_log.clicked_at = now
    _advance_status(email_log, 'clicked')
    subscriber = email_log.subscriber
    subscriber.total_clicks = (subscriber.total_clicks or 0) + 1
    subscriber.last_clicked_at = now
    if first_click and email_log.campaign is not None:
        email_log.campaign.total_clicks = (email_log.campaign.total_clicks or 0) + 1
    db.session.add(EmailEvent(
        business_id=email_log.business_id, email_log_id=email_log.id, campaign_id=email_log.campaign_id,
        subscriber_id=email_log.subscriber_id, event_type='click', url=url,
        user_agent=(user_agent or '')[:500], ip_address=ip_address,
    ))
    db.session.commit()

    if first_click:
        from app.services import automation_service
        automation_service.handle_event(email_log.business_id, 'email_clicked', subscriber,
                                        email_log=email_log, url=url)
    return email_log
