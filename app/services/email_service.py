"""Core email pipeline: queue, render, track, send, retry, bounce."""
import html as html_lib
import logging
import re
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import formataddr, formatdate, make_msgid

from flask import current_app
from sqlalchemy import func, or_

from app import db
from app.models import Business, Campaign, EmailLog, EmailTemplate, Subscriber
from app.services import smtp_service, template_service, tracking_service
from app.utils.helpers import ServiceError, utcnow

logger = logging.getLogger(__name__)

# Long URLs in List-Unsubscribe must not be folded into RFC 2047 encoded-words
# (clients would not parse them), so allow lines up to the RFC 5322 limit.
MESSAGE_POLICY = default_policy.clone(max_line_length=998)
HREF_RE = re.compile(r'''(<a\b[^>]*?\bhref\s*=\s*)(["'])(.*?)\2''', re.IGNORECASE | re.DOTALL)
SENDING_LEASE = timedelta(minutes=10)


# ------------------------------------------------------------------ content

def rewrite_links(html, email_log_id, skip_urls=()):
    """Point every http(s) link at the click tracker."""
    def replace(match):
        raw = match.group(3)
        url = html_lib.unescape(raw).strip()
        if not tracking_service.is_safe_redirect(url) or url in skip_urls:
            return match.group(0)
        tracked = html_lib.escape(tracking_service.click_url(email_log_id, url), quote=True)
        return f'{match.group(1)}{match.group(2)}{tracked}{match.group(2)}'
    return HREF_RE.sub(replace, html)


def inject_pixel(html, email_log_id):
    pixel = (f'<img src="{html_lib.escape(tracking_service.pixel_url(email_log_id), quote=True)}" '
             'width="1" height="1" alt="" style="display:none;border:0;">')
    index = html.lower().rfind('</body>')
    if index == -1:
        return html + pixel
    return html[:index] + pixel + html[index:]


def build_content(business, subscriber, template, email_log_id, subject_override=None):
    """Render a template for one recipient with tracking + unsubscribe links."""
    unsubscribe = tracking_service.unsubscribe_url(email_log_id)
    variables = subscriber.template_context()
    variables.update({
        'unsubscribe_url': unsubscribe,
        'business_name': business.name,
        'physical_address': business.physical_address or '',
    })
    rendered = template_service.render_template(template, variables, subject_override=subject_override)
    html = rendered['html']
    text = rendered['text']

    if unsubscribe not in html:
        footer = (f'<p style="font-size:12px;color:#71717a;text-align:center;">'
                  f'{html_lib.escape(business.name)}'
                  f'{" &middot; " + html_lib.escape(business.physical_address) if business.physical_address else ""}'
                  f'<br><a href="{html_lib.escape(unsubscribe, quote=True)}">Unsubscribe</a></p>')
        index = html.lower().rfind('</body>')
        html = html[:index] + footer + html[index:] if index != -1 else html + footer
    if unsubscribe not in text:
        text = f'{text}\n\n--\n{business.name}\n{business.physical_address or ""}\nUnsubscribe: {unsubscribe}'

    if current_app.config.get('ENABLE_TRACKING', True):
        html = rewrite_links(html, email_log_id, skip_urls=(unsubscribe,))
        html = inject_pixel(html, email_log_id)

    return {'subject': rendered['subject'], 'html': html, 'text': text, 'unsubscribe_url': unsubscribe}


def build_message(business, recipient, subject, html, text, unsubscribe_url=None, email_log_id=None):
    message = EmailMessage(policy=MESSAGE_POLICY)
    message['From'] = formataddr((business.email_from_name or business.name, business.email_from))
    message['To'] = recipient
    message['Subject'] = subject
    message['Date'] = formatdate(localtime=False, usegmt=True)
    message['Message-ID'] = make_msgid(domain=business.sender_domain or None)
    if email_log_id:
        message['X-Email-Log-ID'] = email_log_id
    if unsubscribe_url:
        mailto = f'mailto:unsubscribe@{business.sender_domain}?subject=unsubscribe-{email_log_id}'
        message['List-Unsubscribe'] = f'<{unsubscribe_url}>, <{mailto}>'
        message['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
    message.set_content(text or template_service.html_to_text(html))
    message.add_alternative(html, subtype='html')
    return message


def send_email(business_id, recipient_email, subject, html, text=None, from_email=None, from_name=None):
    """Send a one-off email immediately (e.g. test sends). Not tracked."""
    business = db.session.get(Business, business_id)
    if business is None:
        raise ServiceError('Business not found', 404)
    if business.remaining_daily_quota <= 0:
        raise ServiceError('Daily email limit reached', 429)
    message = build_message(business, recipient_email, subject, html, text)
    if from_email:
        message.replace_header('From', formataddr((from_name or business.email_from_name or '', from_email)))
    try:
        conn = smtp_service.connect_for_business(business)
    except smtp_service.SMTPConnectionError as exc:
        hint = smtp_service.explain_smtp_error(str(exc), business.smtp_host, business.smtp_port)
        raise ServiceError(f'{exc}' + (f' -> {hint}' if hint else ''), 502)
    try:
        conn.send_message(message)
    except Exception as exc:  # noqa: BLE001 - surface SMTP errors to the caller
        raise ServiceError(f'Sending failed: {exc}', 502)
    finally:
        try:
            conn.quit()
        except Exception:  # noqa: BLE001
            pass
    _increment_daily_count(business.id)
    db.session.commit()
    return message['Message-ID']


# -------------------------------------------------------------------- queue

def queue_email(business_id, subscriber, template, campaign=None, automation_id=None,
                subject=None, subject_variant=None, send_at=None):
    """Create a pending email log. The queue processor sends it later."""
    log = EmailLog(
        business_id=business_id, campaign_id=campaign.id if campaign else None,
        automation_id=automation_id, template_id=template.id, subscriber_id=subscriber.id,
        recipient_email=subscriber.email, subject_line=subject or template.subject_line,
        subject_variant=subject_variant, status='pending', next_attempt_at=send_at or utcnow(),
    )
    db.session.add(log)
    return log


def _increment_daily_count(business_id, amount=1):
    Business.query.filter_by(id=business_id).update(
        {Business.emails_sent_today: func.coalesce(Business.emails_sent_today, 0) + amount},
        synchronize_session=False,
    )


def _claim_batch(limit):
    """Atomically move due pending logs to 'sending' so concurrent workers
    never send the same message twice."""
    now = utcnow()
    query = (
        db.session.query(EmailLog.id)
        .outerjoin(Campaign, EmailLog.campaign_id == Campaign.id)
        .filter(EmailLog.status == 'pending', EmailLog.next_attempt_at <= now)
        .filter(or_(EmailLog.campaign_id.is_(None), Campaign.status == 'sending'))
        .order_by(EmailLog.next_attempt_at, EmailLog.created_at)
        .limit(limit)
    )
    if db.engine.dialect.name == 'postgresql':
        query = query.with_for_update(skip_locked=True, of=EmailLog)
    ids = [row.id for row in query.all()]
    if not ids:
        db.session.commit()
        return []
    EmailLog.query.filter(EmailLog.id.in_(ids), EmailLog.status == 'pending').update(
        {'status': 'sending', 'next_attempt_at': now + SENDING_LEASE}, synchronize_session=False)
    db.session.commit()
    return EmailLog.query.filter(EmailLog.id.in_(ids), EmailLog.status == 'sending').all()


def release_stale_claims():
    """Return logs stuck in 'sending' (worker crashed) to the queue."""
    count = EmailLog.query.filter(EmailLog.status == 'sending', EmailLog.next_attempt_at <= utcnow()).update(
        {'status': 'pending'}, synchronize_session=False)
    db.session.commit()
    return count


def _sent_last_minute(business_id):
    return EmailLog.query.filter(EmailLog.business_id == business_id,
                                 EmailLog.sent_at >= utcnow() - timedelta(minutes=1)).count()


def _retry_later(log, message, attempts_exhausted_status='failed'):
    max_attempts = current_app.config['MAX_RETRY_ATTEMPTS']
    log.error_message = message
    if log.attempts >= max_attempts:
        log.status = attempts_exhausted_status
        log.next_attempt_at = None
    else:
        log.status = 'pending'
        # Exponential backoff: 1, 2, 4, ... minutes
        log.next_attempt_at = utcnow() + timedelta(minutes=2 ** (log.attempts - 1))


def process_email_queue(pool=None, batch_size=None):
    """Send due emails. Returns a summary dict. Runs inside an app context."""
    release_stale_claims()
    batch_size = batch_size or current_app.config['MAX_EMAIL_BATCH_SIZE']
    logs = _claim_batch(batch_size)
    summary = {'claimed': len(logs), 'sent': 0, 'bounced': 0, 'retry': 0, 'failed': 0, 'deferred': 0}
    if not logs:
        return summary

    own_pool = pool is None
    pool = pool or smtp_service.SMTPConnectionPool()
    per_minute = current_app.config['MAX_EMAILS_PER_MINUTE']
    touched_campaigns = set()
    try:
        by_business = {}
        for log in logs:
            by_business.setdefault(log.business_id, []).append(log)

        for business_id, business_logs in by_business.items():
            business = db.session.get(Business, business_id)
            allowance = min(business.remaining_daily_quota, max(per_minute - _sent_last_minute(business_id), 0))
            sendable, deferred = business_logs[:allowance], business_logs[allowance:]
            for log in deferred:
                # Over the daily / per-minute limit: put back, try again later
                log.status = 'pending'
                log.next_attempt_at = utcnow() + timedelta(minutes=1)
                summary['deferred'] += 1
            db.session.commit()

            for log in sendable:
                if log.campaign_id:
                    touched_campaigns.add(log.campaign_id)
                outcome = _send_one(pool, business, log)
                summary[outcome] += 1
                db.session.commit()
                if outcome == 'retry' and log.error_message and log.error_message.startswith('connection:'):
                    # Server unreachable: don't hammer it with the rest of the batch
                    for remaining in sendable[sendable.index(log) + 1:]:
                        remaining.status = 'pending'
                        remaining.next_attempt_at = log.next_attempt_at
                        summary['deferred'] += 1
                    db.session.commit()
                    break
    finally:
        if own_pool:
            pool.close_all()

    for campaign_id in touched_campaigns:
        finalize_campaign_if_done(campaign_id)
    return summary


def _send_one(pool, business, log):
    subscriber = log.subscriber
    if subscriber is None or subscriber.status != 'active':
        log.status = 'failed'
        log.error_message = f'Subscriber is {subscriber.status if subscriber else "deleted"}'
        log.next_attempt_at = None
        return 'failed'
    template = db.session.get(EmailTemplate, log.template_id) if log.template_id else None
    if template is None:
        log.status = 'failed'
        log.error_message = 'Template no longer exists'
        log.next_attempt_at = None
        return 'failed'

    log.attempts = (log.attempts or 0) + 1
    try:
        content = build_content(business, subscriber, template, log.id, subject_override=log.subject_line)
    except ServiceError as exc:
        log.status = 'failed'
        log.error_message = f'{exc.message}: {exc.details}'
        log.next_attempt_at = None
        return 'failed'
    message = build_message(business, log.recipient_email, content['subject'], content['html'],
                            content['text'], content['unsubscribe_url'], log.id)

    try:
        conn = pool.get(business)
        refused = conn.send_message(message)
        if refused and log.recipient_email in refused:
            code, reason = refused[log.recipient_email]
            raise smtplib.SMTPRecipientsRefused({log.recipient_email: (code, reason)})
    except Exception as exc:  # noqa: BLE001 - classify every SMTP failure
        kind, detail = smtp_service.classify_smtp_error(exc)
        if kind == 'connection':
            pool.discard(business.id)
            _retry_later(log, f'connection: {detail}')
            return 'retry' if log.status == 'pending' else 'failed'
        if kind == 'hard':
            handle_bounce(log, detail, bounce_type='hard', commit=False)
            return 'bounced'
        _retry_later(log, detail, attempts_exhausted_status='bounced')
        if log.status == 'bounced':
            handle_bounce(log, detail, bounce_type='soft', commit=False)
            return 'bounced'
        return 'retry'

    now = utcnow()
    log.status = 'sent'
    log.sent_at = now
    log.subject_line = content['subject']
    log.message_id = message['Message-ID']
    log.error_message = None
    log.next_attempt_at = None
    _increment_daily_count(business.id)
    if log.campaign is not None:
        log.campaign.total_sent = (log.campaign.total_sent or 0) + 1
    return 'sent'


def handle_bounce(email_log, reason, bounce_type='hard', commit=True):
    """Record a bounce and update the subscriber.

    Hard bounces deactivate the subscriber immediately; soft bounces do so
    after MAX_SOFT_BOUNCES.
    """
    if isinstance(email_log, str):
        email_log = db.session.get(EmailLog, email_log)
        if email_log is None:
            raise ServiceError('Email log not found', 404)
    already_bounced = email_log.bounced_at is not None
    email_log.status = 'bounced'
    email_log.bounce_type = bounce_type
    email_log.bounced_at = email_log.bounced_at or utcnow()
    email_log.error_message = reason
    email_log.next_attempt_at = None

    if not already_bounced:
        subscriber = db.session.get(Subscriber, email_log.subscriber_id)
        if subscriber is not None:
            subscriber.bounce_count = (subscriber.bounce_count or 0) + 1
            if bounce_type == 'hard' or subscriber.bounce_count >= current_app.config['MAX_SOFT_BOUNCES']:
                if subscriber.status == 'active':
                    from app.services.subscriber_service import _apply_status
                    _apply_status(subscriber, 'bounced')
        if email_log.campaign is not None:
            email_log.campaign.total_bounces = (email_log.campaign.total_bounces or 0) + 1
    if commit:
        db.session.commit()
    return email_log


def finalize_campaign_if_done(campaign_id):
    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None or campaign.status != 'sending':
        return False
    remaining = EmailLog.query.filter(EmailLog.campaign_id == campaign_id,
                                      EmailLog.status.in_(['pending', 'sending'])).count()
    if remaining:
        return False
    campaign.status = 'sent'
    campaign.completed_at = utcnow()
    db.session.commit()
    return True
