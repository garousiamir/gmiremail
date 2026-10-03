from collections import OrderedDict
from datetime import timedelta

from sqlalchemy import func, or_

from app import db
from app.models import Automation, Campaign, EmailEvent, EmailLog, Subscriber
from app.utils.helpers import NotFoundError, ServiceError, percentage, utcnow

ENGAGEMENT_WINDOW_DAYS = 90


def _window(days, maximum=365):
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise ServiceError('days must be an integer')
    return min(max(days, 1), maximum)


def _rates(sent, opens, clicks, bounces, unsubscribes):
    return {
        'open_rate': percentage(opens, sent),
        'click_rate': percentage(clicks, sent),
        'click_to_open_rate': percentage(clicks, opens),
        'bounce_rate': percentage(bounces, sent),
        'unsubscribe_rate': percentage(unsubscribes, sent),
    }


def _log_totals(*filters):
    sent, opens, clicks, bounces = db.session.query(
        func.count(EmailLog.sent_at), func.count(EmailLog.opened_at),
        func.count(EmailLog.clicked_at), func.count(EmailLog.bounced_at),
    ).filter(*filters).one()
    return sent, opens, clicks, bounces


def get_business_overview(business_id):
    from app.models import Business
    business = db.session.get(Business, business_id)
    status_counts = dict(
        db.session.query(Subscriber.status, func.count(Subscriber.id))
        .filter(Subscriber.business_id == business_id).group_by(Subscriber.status).all()
    )
    campaign_counts = dict(
        db.session.query(Campaign.status, func.count(Campaign.id))
        .filter(Campaign.business_id == business_id).group_by(Campaign.status).all()
    )
    sent, opens, clicks, bounces = _log_totals(EmailLog.business_id == business_id)
    unsubscribes = EmailEvent.query.filter_by(business_id=business_id, event_type='unsubscribe').count()
    queued = EmailLog.query.filter(EmailLog.business_id == business_id,
                                   EmailLog.status.in_(['pending', 'sending'])).count()
    return {
        'subscribers': {
            'total': sum(status_counts.values()),
            'active': status_counts.get('active', 0),
            'inactive': status_counts.get('inactive', 0),
            'bounced': status_counts.get('bounced', 0),
            'unsubscribed': status_counts.get('unsubscribed', 0),
        },
        'campaigns': {
            'total': sum(campaign_counts.values()),
            'sent': campaign_counts.get('sent', 0),
            'sending': campaign_counts.get('sending', 0),
            'scheduled': campaign_counts.get('scheduled', 0),
            'draft': campaign_counts.get('draft', 0),
            'paused': campaign_counts.get('paused', 0),
        },
        'active_automations': Automation.query.filter_by(business_id=business_id, status='active').count(),
        'emails': {
            'sent': sent, 'unique_opens': opens, 'unique_clicks': clicks, 'bounces': bounces,
            'unsubscribes': unsubscribes, 'queued': queued,
            'sent_today': business.emails_sent_today, 'daily_limit': business.daily_email_limit,
        },
        **_rates(sent, opens, clicks, bounces, unsubscribes),
    }


def _date_series(days):
    today = utcnow().date()
    return OrderedDict(((today - timedelta(days=offset)).isoformat(), None) for offset in range(days - 1, -1, -1))


def get_engagement_metrics(business_id, days=30):
    days = _window(days)
    since = utcnow() - timedelta(days=days)
    sent, opens, clicks, bounces = _log_totals(EmailLog.business_id == business_id, EmailLog.sent_at >= since)
    unsubscribes = EmailEvent.query.filter(EmailEvent.business_id == business_id,
                                           EmailEvent.event_type == 'unsubscribe',
                                           EmailEvent.created_at >= since).count()

    series = _date_series(days)
    for key in series:
        series[key] = {'date': key, 'sent': 0, 'opens': 0, 'clicks': 0}
    for sent_at, in db.session.query(EmailLog.sent_at).filter(EmailLog.business_id == business_id,
                                                              EmailLog.sent_at >= since):
        bucket = series.get(sent_at.date().isoformat())
        if bucket:
            bucket['sent'] += 1
    events = db.session.query(EmailEvent.event_type, EmailEvent.created_at).filter(
        EmailEvent.business_id == business_id, EmailEvent.created_at >= since,
        EmailEvent.event_type.in_(['open', 'click']))
    for event_type, created_at in events:
        bucket = series.get(created_at.date().isoformat())
        if bucket:
            bucket['opens' if event_type == 'open' else 'clicks'] += 1

    buckets = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
    distribution = []
    for low, high in buckets:
        count = Subscriber.query.filter(Subscriber.business_id == business_id, Subscriber.status == 'active',
                                        Subscriber.engagement_score >= low,
                                        Subscriber.engagement_score < high).count()
        distribution.append({'range': f'{low}-{min(high, 100)}', 'subscribers': count})

    hourly = [0] * 24
    for (created_at,) in db.session.query(EmailEvent.created_at).filter(
            EmailEvent.business_id == business_id, EmailEvent.event_type == 'open',
            EmailEvent.created_at >= since):
        hourly[created_at.hour] += 1

    return {
        'days': days,
        'sent': sent, 'unique_opens': opens, 'unique_clicks': clicks,
        'bounces': bounces, 'unsubscribes': unsubscribes,
        **_rates(sent, opens, clicks, bounces, unsubscribes),
        'daily': list(series.values()),
        'opens_by_hour_utc': [{'hour': h, 'opens': c} for h, c in enumerate(hourly)],
        'engagement_distribution': distribution,
    }


def get_subscriber_growth(business_id, days=30):
    days = _window(days)
    since = utcnow() - timedelta(days=days)
    series = _date_series(days)
    for key in series:
        series[key] = {'date': key, 'new_subscribers': 0, 'unsubscribes': 0, 'total': 0}

    base_total = Subscriber.query.filter(Subscriber.business_id == business_id,
                                         Subscriber.created_at < since).count()
    for (created_at,) in db.session.query(Subscriber.created_at).filter(
            Subscriber.business_id == business_id, Subscriber.created_at >= since):
        bucket = series.get(created_at.date().isoformat())
        if bucket:
            bucket['new_subscribers'] += 1
    for (unsub_at,) in db.session.query(Subscriber.unsubscribed_at).filter(
            Subscriber.business_id == business_id, Subscriber.unsubscribed_at >= since):
        bucket = series.get(unsub_at.date().isoformat())
        if bucket:
            bucket['unsubscribes'] += 1

    running = base_total
    for bucket in series.values():
        running += bucket['new_subscribers']
        bucket['total'] = running
    new_total = sum(b['new_subscribers'] for b in series.values())
    unsub_total = sum(b['unsubscribes'] for b in series.values())
    return {
        'days': days,
        'new_subscribers': new_total,
        'unsubscribes': unsub_total,
        'net_growth': new_total - unsub_total,
        'daily': list(series.values()),
    }


def get_campaign_comparison(business_id, limit=20):
    campaigns = (Campaign.query.filter(Campaign.business_id == business_id,
                                       Campaign.status.in_(['sending', 'sent', 'paused']))
                 .order_by(Campaign.send_time.desc()).limit(_window(limit, 100)).all())
    rows = []
    for campaign in campaigns:
        data = campaign.to_dict()
        data['click_to_open_rate'] = percentage(campaign.total_clicks or 0, campaign.total_opens or 0)
        data['unsubscribe_rate'] = percentage(campaign.total_unsubscribes or 0, campaign.total_sent or 0)
        rows.append(data)
    best = max(rows, key=lambda r: r['open_rate'], default=None)
    return {
        'campaigns': rows,
        'best_open_rate': {'id': best['id'], 'name': best['name'], 'open_rate': best['open_rate']} if best else None,
        'average_open_rate': round(sum(r['open_rate'] for r in rows) / len(rows), 2) if rows else 0.0,
        'average_click_rate': round(sum(r['click_rate'] for r in rows) / len(rows), 2) if rows else 0.0,
    }


def email_logs_query(business_id, filters):
    query = EmailLog.query.filter(EmailLog.business_id == business_id)
    for field in ('status', 'campaign_id', 'subscriber_id', 'automation_id'):
        if filters.get(field):
            query = query.filter(getattr(EmailLog, field) == filters[field])
    if filters.get('email'):
        query = query.filter(EmailLog.recipient_email.ilike(f"%{filters['email']}%"))
    return query.order_by(EmailLog.created_at.desc())


def calculate_campaign_metrics(campaign_id):
    from app.services.campaign_service import recalculate_campaign_totals
    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFoundError('Campaign')
    recalculate_campaign_totals(campaign)
    db.session.commit()
    return campaign.to_dict()


def calculate_engagement_score(subscriber_id, commit=True):
    """0-100 score: 40% open rate + 40% click rate (last 90 days) + recency bonus."""
    subscriber = db.session.get(Subscriber, subscriber_id) if isinstance(subscriber_id, str) else subscriber_id
    if subscriber is None:
        raise NotFoundError('Subscriber')
    now = utcnow()
    since = now - timedelta(days=ENGAGEMENT_WINDOW_DAYS)
    sent, opens, clicks, _ = _log_totals(EmailLog.subscriber_id == subscriber.id, EmailLog.sent_at >= since)
    score = 0.0
    if sent:
        score += 40 * min(opens / sent, 1) + 40 * min(clicks / sent, 1)
    last = max(filter(None, [subscriber.last_opened_at, subscriber.last_clicked_at]), default=None)
    if last:
        age = (now - last).days
        score += 20 if age <= 7 else 10 if age <= 30 else 5 if age <= ENGAGEMENT_WINDOW_DAYS else 0
    subscriber.engagement_score = round(min(score, 100.0), 2)
    if commit:
        db.session.commit()
    return subscriber.engagement_score


def subscriber_activity(business_id, subscriber_id, limit=50):
    subscriber = Subscriber.query.filter_by(id=subscriber_id, business_id=business_id).first()
    if subscriber is None:
        raise NotFoundError('Subscriber')
    logs = (EmailLog.query.filter_by(subscriber_id=subscriber.id)
            .order_by(EmailLog.created_at.desc()).limit(limit).all())
    events = (EmailEvent.query.filter_by(subscriber_id=subscriber.id)
              .order_by(EmailEvent.created_at.desc()).limit(limit).all())
    sent, opens, clicks, bounces = _log_totals(EmailLog.subscriber_id == subscriber.id)
    return {
        'subscriber': subscriber.to_dict(),
        'stats': {'emails_received': sent, 'unique_opens': opens, 'unique_clicks': clicks, 'bounces': bounces,
                  'open_rate': percentage(opens, sent), 'click_rate': percentage(clicks, sent)},
        'recent_emails': [log.to_dict() for log in logs],
        'recent_events': [event.to_dict() for event in events],
    }


def calculate_analytics(since_minutes=15, full=False):
    """Background job: refresh campaign counters and engagement scores."""
    since = utcnow() - timedelta(minutes=since_minutes)
    if full:
        campaign_ids = [c.id for c in Campaign.query.filter(Campaign.status.in_(['sending', 'sent', 'paused']))]
        subscriber_ids = [s.id for s in Subscriber.query.with_entities(Subscriber.id)]
    else:
        campaign_ids = {c.id for c in Campaign.query.filter(Campaign.status.in_(['sending', 'paused']))}
        campaign_ids |= {row[0] for row in db.session.query(EmailEvent.campaign_id).filter(
            EmailEvent.created_at >= since, EmailEvent.campaign_id.isnot(None)).distinct()}
        subscriber_ids = {row[0] for row in db.session.query(EmailEvent.subscriber_id).filter(
            EmailEvent.created_at >= since).distinct()}
        subscriber_ids |= {row[0] for row in db.session.query(EmailLog.subscriber_id).filter(
            or_(EmailLog.sent_at >= since, EmailLog.bounced_at >= since)).distinct()}

    from app.services.campaign_service import recalculate_campaign_totals
    for campaign_id in campaign_ids:
        campaign = db.session.get(Campaign, campaign_id)
        if campaign:
            recalculate_campaign_totals(campaign)
    db.session.commit()

    for index, subscriber_id in enumerate(subscriber_ids):
        subscriber = db.session.get(Subscriber, subscriber_id)
        if subscriber:
            calculate_engagement_score(subscriber, commit=False)
        if index % 500 == 499:
            db.session.commit()
    db.session.commit()
    return {'campaigns': len(campaign_ids), 'subscribers': len(subscriber_ids)}
