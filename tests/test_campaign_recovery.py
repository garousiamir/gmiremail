import pytest

from app import db
from app.models import Campaign, EmailEvent, EmailLog, Subscriber
from app.services import email_service, smtp_service, tracking_service
from tests.conftest import add_subscriber, create_template


def _sent_campaign(client, auth, emails):
    template = create_template(client, auth)
    for email in emails:
        add_subscriber(client, auth, email)
    campaign = client.post('/api/campaigns', json={'name': 'Launch', 'template_id': template['id'],
                                                   'subject_variants': ['A', 'B']}, headers=auth).get_json()
    client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth)
    email_service.process_email_queue()
    return campaign


@pytest.mark.parametrize('text, kind', [
    ('550 5.1.1 The email account that you tried to reach does not exist', 'hard'),
    ('550 Recipient address rejected: User unknown in virtual mailbox table', 'hard'),
    ('554 5.7.1 <a@b.c>: Relay access denied', 'policy'),
    ('550 5.7.1 Service unavailable, Client host [1.2.3.4] blocked using Spamhaus', 'policy'),
    ('550 Message rejected due to SPF policy', 'policy'),
    ('553 sorry, that domain isn\'t in my list of allowed rcpthosts', 'policy'),
])
def test_permanent_kind(text, kind):
    assert smtp_service.permanent_kind(text) == kind


def test_policy_rejection_does_not_bounce_subscriber(client, auth, outbox):
    campaign = _sent_campaign(client, auth, ['relay@example.com', 'ok@example.com'])
    sub = Subscriber.query.filter_by(email='relay@example.com').one()
    log = EmailLog.query.filter_by(subscriber_id=sub.id).one()
    assert sub.status == 'active' and sub.bounce_count == 0
    assert log.status == 'failed' and 'Relay access denied' in log.error_message
    analytics = client.get(f"/api/campaigns/{campaign['id']}/analytics", headers=auth).get_json()
    assert analytics['failed'] == 1 and analytics['bounces'] == 0


def test_retry_failed_requeues_and_sends(client, auth, outbox, monkeypatch):
    campaign = _sent_campaign(client, auth, ['relay@example.com', 'ok@example.com'])
    assert db.session.get(Campaign, campaign['id']).status == 'sent'

    # "Fix" the SMTP server: the relay now accepts everyone
    from tests.conftest import FakeSMTP
    monkeypatch.setattr(FakeSMTP, 'send_message', lambda self, m: self.outbox.append(m) or {})
    response = client.post(f"/api/campaigns/{campaign['id']}/retry-failed", headers=auth)
    assert response.status_code == 200 and response.get_json()['requeued'] == 1
    assert db.session.get(Campaign, campaign['id']).status == 'sending'
    assert email_service.process_email_queue()['sent'] == 1
    assert db.session.get(Campaign, campaign['id']).status == 'sent'
    # Nothing left to retry
    assert client.post(f"/api/campaigns/{campaign['id']}/retry-failed", headers=auth).status_code == 409


def test_reset_clears_history_and_allows_resend(client, auth, outbox):
    campaign = _sent_campaign(client, auth, ['a@example.com', 'hard@example.com', 'gone@example.com'])
    tracking_service.track_email_open(EmailLog.query.filter_by(recipient_email='a@example.com').one().id)
    gone = Subscriber.query.filter_by(email='gone@example.com').one()
    client.put(f'/api/subscribers/{gone.id}/status', json={'status': 'unsubscribed'}, headers=auth)
    assert Subscriber.query.filter_by(email='hard@example.com').one().status == 'bounced'

    response = client.post(f"/api/campaigns/{campaign['id']}/reset", json={'restore_bounced': True}, headers=auth)
    body = response.get_json()
    assert response.status_code == 200 and body['restored_subscribers'] == 1
    assert body['campaign']['status'] == 'draft' and body['campaign']['total_sent'] == 0
    assert EmailLog.query.filter_by(campaign_id=campaign['id']).count() == 0
    assert EmailEvent.query.filter_by(campaign_id=campaign['id']).count() == 0
    assert Subscriber.query.filter_by(email='hard@example.com').one().status == 'active'
    assert Subscriber.query.filter_by(email='gone@example.com').one().status == 'unsubscribed'

    outbox.clear()
    result = client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth).get_json()
    assert result['recipients_queued'] == 2  # unsubscribed person is not mailed again


def test_reset_without_restore_keeps_bounced(client, auth, outbox):
    campaign = _sent_campaign(client, auth, ['hard@example.com'])
    client.post(f"/api/campaigns/{campaign['id']}/reset", json={}, headers=auth)
    assert Subscriber.query.filter_by(email='hard@example.com').one().status == 'bounced'


def test_reset_rules(client, auth, outbox):
    template = create_template(client, auth)
    draft = client.post('/api/campaigns', json={'name': 'D', 'template_id': template['id']}, headers=auth).get_json()
    assert client.post(f"/api/campaigns/{draft['id']}/reset", json={}, headers=auth).status_code == 409
    add_subscriber(client, auth, 'a@example.com')
    client.post(f"/api/campaigns/{draft['id']}/send", json={}, headers=auth)  # now 'sending'
    assert client.post(f"/api/campaigns/{draft['id']}/reset", json={}, headers=auth).status_code == 409


def test_duplicate(client, auth, other_auth, outbox):
    campaign = _sent_campaign(client, auth, ['a@example.com'])
    response = client.post(f"/api/campaigns/{campaign['id']}/duplicate", headers=auth)
    copy = response.get_json()
    assert response.status_code == 201
    assert copy['name'] == 'Launch (copy)' and copy['status'] == 'draft'
    assert copy['subject_variants'] == ['A', 'B'] and copy['total_sent'] == 0
    assert db.session.get(Campaign, campaign['id']).total_sent == 1  # original untouched
    assert client.post(f"/api/campaigns/{campaign['id']}/duplicate", headers=other_auth).status_code == 404


@pytest.mark.parametrize('exc, kind', [
    (__import__('smtplib').SMTPDataError(554, b'5.7.1 Relay access denied'), 'policy'),
    (__import__('smtplib').SMTPDataError(550, b'5.1.1 No such user'), 'hard'),
    (__import__('smtplib').SMTPDataError(451, b'4.3.0 Try again later'), 'soft'),
    (__import__('smtplib').SMTPSenderRefused(553, b'5.7.1 Sender not owned by user', 'a@b.c'), 'policy'),
    (__import__('smtplib').SMTPAuthenticationError(535, b'5.7.8 bad credentials'), 'connection'),
    (__import__('smtplib').SMTPServerDisconnected('gone'), 'connection'),
    (TimeoutError('timed out'), 'connection'),
])
def test_classify_reads_smtp_code_before_oserror(exc, kind):
    assert smtp_service.classify_smtp_error(exc)[0] == kind
