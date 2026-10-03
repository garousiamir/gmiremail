from datetime import timedelta
from urllib.parse import parse_qs, urlparse
import re

from app import db
from app.models import Business, Campaign, EmailLog, Subscriber
from app.services import campaign_service, email_service
from app.utils.helpers import utcnow
from tests.conftest import add_subscriber, create_template


def _setup_campaign(client, auth, emails, **extra):
    template = create_template(client, auth)
    for email in emails:
        add_subscriber(client, auth, email, first_name=email.split('@')[0].title())
    response = client.post('/api/campaigns', json={'name': 'Launch', 'template_id': template['id'], **extra},
                           headers=auth)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _html(message):
    return message.get_body(('html',)).get_content()


def test_send_campaign_and_track(client, auth, outbox):
    campaign = _setup_campaign(client, auth, ['ann@example.com', 'bob@example.com'])
    response = client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth)
    assert response.status_code == 200
    assert response.get_json()['recipients_queued'] == 2

    # Sending twice is rejected
    assert client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth).status_code == 409

    summary = email_service.process_email_queue()
    assert summary['sent'] == 2
    assert len(outbox) == 2
    message = next(m for m in outbox if m['To'] == 'ann@example.com')
    assert message['Subject'] == 'Hello Ann'
    assert 'List-Unsubscribe' in message and message['List-Unsubscribe-Post'] == 'List-Unsubscribe=One-Click'
    # Header must stay a plain <url> list on the wire, not an RFC 2047 encoded-word
    assert '=?' not in message.as_string().split('List-Unsubscribe:', 1)[1].split('\n', 1)[0]
    html = _html(message)
    assert '/t/pixel?email_log_id=' in html
    assert 'Unsubscribe' in html and '1 Main St' in html

    assert db.session.get(Campaign, campaign['id']).status == 'sent'
    assert db.session.get(Business, db.session.get(Campaign, campaign['id']).business_id).emails_sent_today == 2

    # Open tracking pixel
    pixel = re.search(r'src="([^"]*/t/pixel[^"]*)"', html).group(1).replace('&amp;', '&')
    response = client.get(urlparse(pixel).path + '?' + urlparse(pixel).query)
    assert response.status_code == 200 and response.mimetype == 'image/gif'

    # Click tracking: redirects to the original URL (entities decoded)
    link = re.search(r'href="([^"]*/t/click[^"]*)"', html).group(1).replace('&amp;', '&')
    parsed = urlparse(link)
    response = client.get(parsed.path + '?' + parsed.query)
    assert response.status_code == 302
    assert response.headers['Location'] == 'https://example.com/page?a=1&b=2'

    # Tampered click link is rejected (no open redirect)
    params = parse_qs(parsed.query)
    response = client.get('/t/click', query_string={'email_log_id': params['email_log_id'][0],
                                                     'url': 'https://evil.test', 'sig': params['sig'][0]})
    assert response.status_code == 400

    analytics = client.get(f"/api/campaigns/{campaign['id']}/analytics", headers=auth).get_json()
    assert analytics['sent'] == 2
    assert analytics['unique_opens'] == 1
    assert analytics['unique_clicks'] == 1
    assert analytics['open_rate'] == 50.0
    assert analytics['top_links'][0]['url'] == 'https://example.com/page?a=1&b=2'

    log = EmailLog.query.filter_by(recipient_email='ann@example.com').one()
    assert log.status == 'clicked'
    assert db.session.get(Subscriber, log.subscriber_id).total_clicks == 1


def test_unsubscribe_flow(client, auth, outbox):
    campaign = _setup_campaign(client, auth, ['ann@example.com'])
    client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth)
    email_service.process_email_queue()
    unsubscribe_url = re.search(r'<(http[^>]*/u/[^>]*)>', outbox[0]['List-Unsubscribe']).group(1)
    parsed = urlparse(unsubscribe_url)
    path = parsed.path + '?' + parsed.query

    # GET only shows a confirmation page
    response = client.get(path)
    assert response.status_code == 200 and b'<form' in response.data
    assert Subscriber.query.one().status == 'active'

    response = client.post(path)
    assert response.status_code == 200
    subscriber = Subscriber.query.one()
    assert subscriber.status == 'unsubscribed'
    assert db.session.get(Campaign, campaign['id']).total_unsubscribes == 1

    # Bad signature
    assert client.post(parsed.path + '?sig=nope').status_code == 400


def test_bounces_and_retries(client, auth, outbox, app):
    campaign = _setup_campaign(client, auth, ['hard@example.com', 'soft@example.com', 'ok@example.com'])
    client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth)
    summary = email_service.process_email_queue()
    assert summary == {'claimed': 3, 'sent': 1, 'bounced': 1, 'retry': 1, 'failed': 0, 'deferred': 0}

    hard = Subscriber.query.filter_by(email='hard@example.com').one()
    assert hard.status == 'bounced'
    soft_log = EmailLog.query.filter_by(recipient_email='soft@example.com').one()
    assert soft_log.status == 'pending' and soft_log.next_attempt_at > utcnow()
    assert db.session.get(Campaign, campaign['id']).status == 'sending'

    # Exhaust retries
    for _ in range(app.config['MAX_RETRY_ATTEMPTS']):
        soft_log.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        email_service.process_email_queue()
    soft_log = EmailLog.query.filter_by(recipient_email='soft@example.com').one()
    assert soft_log.status == 'bounced' and soft_log.bounce_type == 'soft'
    assert db.session.get(Campaign, campaign['id']).status == 'sent'


def test_daily_limit_defers_sending(client, auth, outbox):
    client.put('/api/businesses/me', json={'daily_email_limit': 1}, headers=auth)
    campaign = _setup_campaign(client, auth, ['a@example.com', 'b@example.com'])
    client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth)
    summary = email_service.process_email_queue()
    assert summary['sent'] == 1 and summary['deferred'] == 1
    assert len(outbox) == 1

    # Limit reached: new sends are refused up front
    other = client.post('/api/campaigns', json={'name': 'Second', 'template_id': campaign['template_id']},
                        headers=auth).get_json()
    assert client.post(f"/api/campaigns/{other['id']}/send", json={}, headers=auth).status_code == 429


def test_pause_resume(client, auth, outbox):
    campaign = _setup_campaign(client, auth, ['a@example.com'])
    client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth)
    assert client.post(f"/api/campaigns/{campaign['id']}/pause", headers=auth).get_json()['status'] == 'paused'
    assert email_service.process_email_queue()['claimed'] == 0
    assert client.post(f"/api/campaigns/{campaign['id']}/resume", headers=auth).get_json()['status'] == 'sending'
    assert email_service.process_email_queue()['sent'] == 1


def test_schedule_and_dispatch(client, auth, outbox):
    campaign = _setup_campaign(client, auth, ['a@example.com'])
    past = (utcnow() - timedelta(hours=1)).isoformat() + 'Z'
    assert client.post(f"/api/campaigns/{campaign['id']}/schedule", json={'scheduled_time': past},
                       headers=auth).status_code == 400
    future = (utcnow() + timedelta(hours=1)).isoformat() + 'Z'
    response = client.post(f"/api/campaigns/{campaign['id']}/schedule", json={'scheduled_time': future},
                           headers=auth)
    assert response.get_json()['status'] == 'scheduled'
    assert campaign_service.dispatch_due_campaigns() == 0

    row = db.session.get(Campaign, campaign['id'])
    row.scheduled_time = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert campaign_service.dispatch_due_campaigns() == 1
    assert email_service.process_email_queue()['sent'] == 1


def test_segment_targeting_and_ab_variants(client, auth, outbox):
    template = create_template(client, auth)
    for i in range(4):
        add_subscriber(client, auth, f'pro{i}@example.com', custom_fields={'plan': 'pro'})
    add_subscriber(client, auth, 'free@example.com', custom_fields={'plan': 'free'})
    add_subscriber(client, auth, 'gone@example.com', custom_fields={'plan': 'pro'}, status='unsubscribed')
    segment = client.post('/api/segments', headers=auth, json={
        'name': 'Pro', 'filter_rules': {'rules': [{'field': 'plan', 'operator': 'equals', 'value': 'pro'}]}}
    ).get_json()
    campaign = client.post('/api/campaigns', headers=auth, json={
        'name': 'AB', 'template_id': template['id'], 'segment_id': segment['id'],
        'subject_variants': ['Subject A {{ first_name }}', 'Subject B']}).get_json()
    result = client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth).get_json()
    assert result['recipients_queued'] == 4  # unsubscribed excluded
    email_service.process_email_queue()
    subjects = sorted(m['Subject'] for m in outbox)
    assert subjects.count('Subject B') == 2
    analytics = client.get(f"/api/campaigns/{campaign['id']}/analytics", headers=auth).get_json()
    assert len(analytics['ab_test']['variants']) == 2


def test_campaign_requires_own_template(client, auth, other_auth):
    template = create_template(client, auth)
    response = client.post('/api/campaigns', json={'name': 'x', 'template_id': template['id']}, headers=other_auth)
    assert response.status_code == 404


def test_template_in_use_cannot_be_deleted(client, auth):
    campaign = _setup_campaign(client, auth, [])
    response = client.delete(f"/api/templates/{campaign['template_id']}", headers=auth)
    assert response.status_code == 409
