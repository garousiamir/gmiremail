from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, insert

from app import db
from app.models import Business, Campaign, EmailEvent, EmailLog, Subscriber
from app.services import audience_service, email_service, segment_service, template_service
from app.utils.helpers import NotFoundError, ServiceError, new_id, parse_datetime, percentage, utcnow

INSERT_CHUNK = 1000


def _validate_variants(variants):
    if variants in (None, []):
        return []
    if not isinstance(variants, list) or not all(isinstance(v, str) and v.strip() for v in variants):
        raise ServiceError('subject_variants must be a list of non-empty strings')
    if len(variants) > 10:
        raise ServiceError('At most 10 subject variants are supported')
    for variant in variants:
        template_service.extract_variables(variant, '')  # syntax check
    return [v.strip() for v in variants]


def get_campaign(business_id, campaign_id):
    campaign = Campaign.query.filter_by(id=campaign_id, business_id=business_id).first()
    if campaign is None:
        raise NotFoundError('Campaign')
    return campaign


def list_campaigns(business_id, status=None, search=None, date_from=None, date_to=None):
    query = Campaign.query.filter_by(business_id=business_id)
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(Campaign.name.ilike(f'%{search.strip()}%'))
    # Date range over when it was sent (or created, for drafts)
    when = func.coalesce(Campaign.send_time, Campaign.scheduled_time, Campaign.created_at)
    if date_from:
        query = query.filter(when >= parse_datetime(date_from))
    if date_to:
        end = parse_datetime(date_to)
        if len(str(date_to).strip()) == 10:
            end += timedelta(days=1)
        query = query.filter(when < end)
    return query.order_by(Campaign.created_at.desc())


def create_campaign(business_id, template_id, segment_id, name, subject_line=None, subject_variants=None,
                    audience=None):
    if not name:
        raise ServiceError('Campaign name is required')
    if not template_id:
        raise ServiceError('template_id is required')
    template_service.get_template(business_id, template_id)
    if segment_id:
        segment_service.get_segment(business_id, segment_id)
    if subject_line:
        template_service.extract_variables(subject_line, '')
    campaign = Campaign(
        business_id=business_id, template_id=template_id, segment_id=segment_id or None, name=name,
        subject_line=subject_line or None, subject_variants=_validate_variants(subject_variants), status='draft',
        audience=audience_service.validate_audience(business_id, audience),
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def update_campaign(business_id, campaign_id, data):
    campaign = get_campaign(business_id, campaign_id)
    content_fields = {'template_id', 'segment_id', 'subject_line', 'subject_variants', 'audience'}
    if content_fields & set(data) and campaign.status not in ('draft', 'scheduled'):
        raise ServiceError(f'Cannot change the content of a {campaign.status} campaign', 409)
    if 'name' in data:
        if not data['name']:
            raise ServiceError('Campaign name is required')
        campaign.name = data['name']
    if 'template_id' in data:
        template_service.get_template(business_id, data['template_id'])
        campaign.template_id = data['template_id']
    if 'segment_id' in data:
        if data['segment_id']:
            segment_service.get_segment(business_id, data['segment_id'])
        campaign.segment_id = data['segment_id'] or None
    if 'subject_line' in data:
        if data['subject_line']:
            template_service.extract_variables(data['subject_line'], '')
        campaign.subject_line = data['subject_line'] or None
    if 'subject_variants' in data:
        campaign.subject_variants = _validate_variants(data['subject_variants'])
    if 'audience' in data:
        campaign.audience = audience_service.validate_audience(business_id, data['audience'])
    if 'scheduled_time' in data:
        if campaign.status not in ('draft', 'scheduled'):
            raise ServiceError('Only draft or scheduled campaigns can be rescheduled', 409)
        if data['scheduled_time']:
            return schedule_campaign(business_id, campaign_id, data['scheduled_time'])
        campaign.scheduled_time = None
        campaign.status = 'draft'
    db.session.commit()
    return campaign


def delete_campaign(business_id, campaign_id):
    campaign = get_campaign(business_id, campaign_id)
    if campaign.status == 'sending':
        raise ServiceError('Pause the campaign before deleting it', 409)
    EmailEvent.query.filter_by(campaign_id=campaign.id).delete(synchronize_session=False)
    EmailLog.query.filter_by(campaign_id=campaign.id).delete(synchronize_session=False)
    db.session.delete(campaign)
    db.session.commit()


def create_email_logs_from_segment(campaign, segment_id=None):
    """Queue one pending email log per active recipient. Idempotent."""
    if campaign.audience and not segment_id:
        recipients = audience_service.audience_query(campaign.business_id, campaign.audience)
    else:
        rules = None
        segment_id = segment_id or campaign.segment_id
        if segment_id:
            rules = segment_service.get_segment(campaign.business_id, segment_id).filter_rules
        recipients = segment_service.subscribers_query(campaign.business_id, rules, only_active=True)
    already = db.select(EmailLog.subscriber_id).where(EmailLog.campaign_id == campaign.id)
    recipients = recipients.filter(Subscriber.id.notin_(already)).order_by(Subscriber.created_at)

    template = campaign.template
    variants = campaign.subject_variants or []
    base_subject = campaign.subject_line or template.subject_line
    now = utcnow()
    rows, queued = [], 0
    for index, (subscriber_id, email) in enumerate(recipients.with_entities(Subscriber.id, Subscriber.email)
                                                   .all()):
        variant_index = index % len(variants) if variants else None
        rows.append({
            'id': new_id(), 'business_id': campaign.business_id, 'campaign_id': campaign.id,
            'template_id': template.id, 'subscriber_id': subscriber_id, 'recipient_email': email,
            'subject_line': variants[variant_index] if variants else base_subject,
            'subject_variant': variant_index, 'status': 'pending', 'attempts': 0,
            'open_count': 0, 'click_count': 0, 'next_attempt_at': now, 'created_at': now, 'updated_at': now,
        })
        if len(rows) >= INSERT_CHUNK:
            db.session.execute(insert(EmailLog), rows)
            queued += len(rows)
            rows = []
    if rows:
        db.session.execute(insert(EmailLog), rows)
        queued += len(rows)
    return queued


def _start_sending(campaign, segment_id=None):
    if segment_id:
        campaign.segment_id = segment_id
    queued = create_email_logs_from_segment(campaign, segment_id)
    campaign.total_recipients = EmailLog.query.filter_by(campaign_id=campaign.id).count()
    campaign.status = 'sending'
    campaign.send_time = campaign.send_time or utcnow()
    db.session.commit()
    if queued == 0:
        email_service.finalize_campaign_if_done(campaign.id)
    return queued


def send_campaign_now(business_id, campaign_id, segment_id=None):
    campaign = get_campaign(business_id, campaign_id)
    if campaign.status not in ('draft', 'scheduled'):
        raise ServiceError(f'Campaign is already {campaign.status}', 409)
    if segment_id:
        segment_service.get_segment(business_id, segment_id)
    business = db.session.get(Business, business_id)
    if business.remaining_daily_quota <= 0:
        raise ServiceError('Daily email limit reached; try again tomorrow or schedule the campaign', 429)
    queued = _start_sending(campaign, segment_id)
    return {
        'success': True,
        'campaign_id': campaign.id,
        'recipients_queued': queued,
        'daily_limit_remaining': business.remaining_daily_quota,
        'message': 'Campaign queued for sending' if queued else 'No active subscribers matched; nothing to send',
    }


def schedule_campaign(business_id, campaign_id, scheduled_time):
    campaign = get_campaign(business_id, campaign_id)
    if campaign.status not in ('draft', 'scheduled'):
        raise ServiceError(f'Cannot schedule a {campaign.status} campaign', 409)
    when = parse_datetime(scheduled_time)
    if when is None:
        raise ServiceError('scheduled_time is required')
    if when <= utcnow():
        raise ServiceError('scheduled_time must be in the future')
    campaign.scheduled_time = when
    campaign.status = 'scheduled'
    db.session.commit()
    return campaign


def dispatch_due_campaigns():
    """Start scheduled campaigns whose time has come (background job)."""
    due = Campaign.query.filter(Campaign.status == 'scheduled', Campaign.scheduled_time <= utcnow()).all()
    started = 0
    for campaign in due:
        _start_sending(campaign)
        started += 1
    return started


def pause_campaign(business_id, campaign_id):
    campaign = get_campaign(business_id, campaign_id)
    if campaign.status not in ('sending', 'scheduled'):
        raise ServiceError(f'Cannot pause a {campaign.status} campaign', 409)
    campaign.status = 'paused'
    db.session.commit()
    return campaign


def resume_campaign(business_id, campaign_id):
    campaign = get_campaign(business_id, campaign_id)
    if campaign.status != 'paused':
        raise ServiceError('Campaign is not paused', 409)
    if campaign.send_time is None:
        # Paused before it ever started sending
        if campaign.scheduled_time and campaign.scheduled_time > utcnow():
            campaign.status = 'scheduled'
            db.session.commit()
            return campaign
        _start_sending(campaign)
        return campaign
    campaign.status = 'sending'
    db.session.commit()
    email_service.finalize_campaign_if_done(campaign.id)
    return campaign


def retry_failed(business_id, campaign_id):
    """Put this campaign's failed emails back in the queue (e.g. after fixing SMTP)."""
    campaign = get_campaign(business_id, campaign_id)
    if campaign.status in ('draft', 'scheduled'):
        raise ServiceError('This campaign has not been sent yet', 409)
    requeued = EmailLog.query.filter(EmailLog.campaign_id == campaign.id, EmailLog.status == 'failed').update(
        {'status': 'pending', 'attempts': 0, 'error_message': None, 'next_attempt_at': utcnow()},
        synchronize_session=False)
    if not requeued:
        raise ServiceError('There are no failed emails to retry', 409)
    if campaign.status == 'sent':
        campaign.status = 'sending'
        campaign.completed_at = None
    db.session.commit()
    return {'requeued': requeued, 'campaign': campaign.to_dict()}


def reset_campaign(business_id, campaign_id, restore_bounced=False):
    """Erase a campaign's sending history and stats and make it a draft again.

    Use when emails were "sent" but never delivered (e.g. a blocked or broken
    SMTP server). Unsubscribes are never undone. With restore_bounced, subscribers
    this campaign marked as bounced are made active again.
    """
    campaign = get_campaign(business_id, campaign_id)
    if campaign.status == 'sending':
        raise ServiceError('Pause the campaign before resetting it', 409)
    if campaign.status == 'draft' and not campaign.send_time:
        raise ServiceError('This campaign has not been sent yet', 409)

    restored = 0
    if restore_bounced:
        bounced = db.select(EmailLog.subscriber_id).where(
            EmailLog.campaign_id == campaign.id, EmailLog.bounced_at.isnot(None))
        restored = Subscriber.query.filter(
            Subscriber.business_id == business_id, Subscriber.status == 'bounced',
            Subscriber.id.in_(bounced),
        ).update({'status': 'active', 'bounce_count': 0}, synchronize_session=False)

    EmailEvent.query.filter_by(campaign_id=campaign.id).delete(synchronize_session=False)
    EmailLog.query.filter_by(campaign_id=campaign.id).delete(synchronize_session=False)
    campaign.status = 'draft'
    campaign.scheduled_time = None
    campaign.send_time = None
    campaign.completed_at = None
    campaign.total_recipients = campaign.total_sent = campaign.total_opens = 0
    campaign.total_clicks = campaign.total_bounces = campaign.total_unsubscribes = 0
    db.session.commit()
    return {'campaign': campaign.to_dict(), 'restored_subscribers': restored}


def duplicate_campaign(business_id, campaign_id):
    """Copy a campaign (content, audience, A/B subjects) into a new draft."""
    source = get_campaign(business_id, campaign_id)
    copy = Campaign(
        business_id=business_id, template_id=source.template_id, segment_id=source.segment_id,
        name=f'{source.name} (copy)'[:255], subject_line=source.subject_line,
        subject_variants=list(source.subject_variants or []), status='draft',
        audience=dict(source.audience) if source.audience else None,
    )
    db.session.add(copy)
    db.session.commit()
    return copy


def recalculate_campaign_totals(campaign):
    """Rebuild counters from the email logs (source of truth)."""
    stats = db.session.query(
        func.count(EmailLog.id),
        func.count(EmailLog.sent_at),
        func.count(EmailLog.opened_at),
        func.count(EmailLog.clicked_at),
        func.count(EmailLog.bounced_at),
    ).filter(EmailLog.campaign_id == campaign.id).one()
    campaign.total_recipients, campaign.total_sent, campaign.total_opens, \
        campaign.total_clicks, campaign.total_bounces = stats
    campaign.total_unsubscribes = EmailEvent.query.filter_by(
        campaign_id=campaign.id, event_type='unsubscribe').count()
    return campaign


def get_campaign_analytics(business_id, campaign_id):
    campaign = get_campaign(business_id, campaign_id)
    recalculate_campaign_totals(campaign)
    db.session.commit()

    status_counts = dict(
        db.session.query(EmailLog.status, func.count(EmailLog.id))
        .filter(EmailLog.campaign_id == campaign.id).group_by(EmailLog.status).all()
    )
    sent = campaign.total_sent or 0
    opens = campaign.total_opens or 0
    clicks = campaign.total_clicks or 0
    total_open_events = db.session.query(func.coalesce(func.sum(EmailLog.open_count), 0)) \
        .filter(EmailLog.campaign_id == campaign.id).scalar()
    total_click_events = db.session.query(func.coalesce(func.sum(EmailLog.click_count), 0)) \
        .filter(EmailLog.campaign_id == campaign.id).scalar()

    top_links = [
        {'url': url, 'clicks': total, 'unique_clicks': unique}
        for url, total, unique in db.session.query(
            EmailEvent.url, func.count(EmailEvent.id), func.count(func.distinct(EmailEvent.email_log_id)))
        .filter(EmailEvent.campaign_id == campaign.id, EmailEvent.event_type == 'click')
        .group_by(EmailEvent.url).order_by(func.count(EmailEvent.id).desc()).limit(10)
    ]

    # Engagement timing: opens / clicks per hour after the send started
    timeline = defaultdict(lambda: {'opens': 0, 'clicks': 0})
    if campaign.send_time:
        events = db.session.query(EmailEvent.event_type, EmailEvent.created_at).filter(
            EmailEvent.campaign_id == campaign.id, EmailEvent.event_type.in_(['open', 'click']))
        for event_type, created_at in events:
            hour = max(int((created_at - campaign.send_time).total_seconds() // 3600), 0)
            timeline[hour]['opens' if event_type == 'open' else 'clicks'] += 1

    variants = []
    for index, subject in enumerate(campaign.subject_variants or []):
        v_sent, v_opens, v_clicks = db.session.query(
            func.count(EmailLog.sent_at), func.count(EmailLog.opened_at), func.count(EmailLog.clicked_at),
        ).filter(EmailLog.campaign_id == campaign.id, EmailLog.subject_variant == index).one()
        variants.append({
            'variant': index, 'subject_line': subject, 'sent': v_sent, 'unique_opens': v_opens,
            'unique_clicks': v_clicks, 'open_rate': percentage(v_opens, v_sent),
            'click_rate': percentage(v_clicks, v_sent),
        })
    winner = max(variants, key=lambda v: (v['open_rate'], v['click_rate']), default=None)

    return {
        'campaign': campaign.to_dict(),
        'recipients': campaign.total_recipients,
        'sent': sent,
        'pending': status_counts.get('pending', 0) + status_counts.get('sending', 0),
        'failed': status_counts.get('failed', 0),
        'bounces': campaign.total_bounces,
        'unsubscribes': campaign.total_unsubscribes,
        'unique_opens': opens,
        'unique_clicks': clicks,
        'total_opens': total_open_events,
        'total_clicks': total_click_events,
        'open_rate': percentage(opens, sent),
        'click_rate': percentage(clicks, sent),
        'click_to_open_rate': percentage(clicks, opens),
        'bounce_rate': percentage(campaign.total_bounces or 0, sent),
        'unsubscribe_rate': percentage(campaign.total_unsubscribes or 0, sent),
        'status_breakdown': status_counts,
        'top_links': top_links,
        'engagement_timeline': [{'hour_after_send': h, **timeline[h]} for h in sorted(timeline)],
        'ab_test': {'variants': variants, 'leader': winner} if variants else None,
    }


def send_test_email(business_id, campaign_id, emails, sample_data=None):
    from app.utils.validators import normalize_email
    campaign = get_campaign(business_id, campaign_id)
    if not isinstance(emails, list) or not emails or len(emails) > 5:
        raise ServiceError('Provide 1-5 addresses in "emails"')
    rendered = template_service.preview_template(business_id, campaign.template_id, sample_data)
    subject = rendered['subject']
    if campaign.subject_line:
        subject = template_service.render_string(campaign.subject_line, {
            **template_service.DEFAULT_SAMPLE_DATA, **(sample_data or {})})
    sent = []
    for email in emails:
        email = normalize_email(email)
        email_service.send_email(business_id, email, f'[TEST] {subject}', rendered['html'], rendered['text'])
        sent.append(email)
    return {'sent_to': sent}

