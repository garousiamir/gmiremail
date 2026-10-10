from datetime import timedelta

from app import db
from app.models import Campaign, EmailLog, Subscriber
from app.services import email_service
from app.utils.helpers import utcnow
from tests.conftest import add_subscriber, create_template


def _people(client, auth):
    """a: vip, pro  | b: pro, joined 40 days ago | c: beta | d: unsubscribed vip"""
    a = add_subscriber(client, auth, 'a@example.com', tags=['vip'], custom_fields={'plan': 'pro'})
    b = add_subscriber(client, auth, 'b@example.com', custom_fields={'plan': 'pro'})
    c = add_subscriber(client, auth, 'c@example.com', tags=['beta'])
    d = add_subscriber(client, auth, 'd@example.com', tags=['vip'], status='unsubscribed')
    old = db.session.get(Subscriber, b['id'])
    old.subscribed_at = old.created_at = utcnow() - timedelta(days=40)
    db.session.commit()
    return a, b, c, d


def _preview(client, auth, audience):
    response = client.post('/api/campaigns/audience/preview', json={'audience': audience}, headers=auth)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_audience_groups_union_and_exclusions(client, auth):
    a, b, c, d = _people(client, auth)
    pro = client.post('/api/segments', headers=auth, json={'name': 'Pro', 'filter_rules': {
        'rules': [{'field': 'plan', 'operator': 'equals', 'value': 'pro'}]}}).get_json()

    assert _preview(client, auth, None)['recipients'] == 3                       # all active
    assert _preview(client, auth, {'tags': ['vip']})['recipients'] == 1          # d is unsubscribed
    assert _preview(client, auth, {'segment_ids': [pro['id']], 'tags': ['beta']})['recipients'] == 3
    assert _preview(client, auth, {'subscriber_ids': [c['id'], d['id']]})['recipients'] == 1
    assert _preview(client, auth, {'segment_ids': [pro['id']], 'exclude_tags': ['vip']})['recipients'] == 1
    assert _preview(client, auth, {'exclude_segment_ids': [pro['id']]})['recipients'] == 1
    joined_recently = {'rules': [{'field': 'subscribed_at', 'operator': 'within_last_days', 'value': 7}]}
    assert _preview(client, auth, {'rules': joined_recently})['recipients'] == 2


def test_campaign_sends_to_audience_only(client, auth, outbox):
    a, b, c, d = _people(client, auth)
    template = create_template(client, auth)
    campaign = client.post('/api/campaigns', headers=auth, json={
        'name': 'Picked', 'template_id': template['id'],
        'audience': {'subscriber_ids': [a['id'], c['id']], 'exclude_tags': ['beta']}}).get_json()
    assert campaign['audience_summary'] == '2 people (excluding 1 group)'
    result = client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth).get_json()
    assert result['recipients_queued'] == 1
    email_service.process_email_queue()
    assert [m['To'] for m in outbox] == ['a@example.com']
    # Duplicates keep the audience
    copy = client.post(f"/api/campaigns/{campaign['id']}/duplicate", headers=auth).get_json()
    assert copy['audience']['subscriber_ids'] == [a['id'], c['id']]


def test_audience_validation_and_isolation(client, auth, other_auth):
    other_segment = client.post('/api/segments', headers=other_auth, json={
        'name': 'Theirs', 'filter_rules': {'rules': []}}).get_json()
    r = client.post('/api/campaigns/audience/preview', json={'audience': {'segment_ids': [other_segment['id']]}},
                    headers=auth)
    assert r.status_code == 404
    r = client.post('/api/campaigns/audience/preview', json={'audience': {'colour': 'red'}}, headers=auth)
    assert r.status_code == 400
    # Picking another tenant's subscriber reaches nobody
    theirs = add_subscriber(client, other_auth, 'x@example.com')
    assert _preview(client, auth, {'subscriber_ids': [theirs['id']]})['recipients'] == 0


def test_between_operator(client, auth):
    _people(client, auth)
    today = utcnow().date()

    def count(rule):
        r = client.post('/api/segments/preview', json={'filter_rules': {'rules': [rule]}}, headers=auth)
        assert r.status_code == 200, r.get_json()
        return r.get_json()['subscriber_count']

    since = (today - timedelta(days=50)).isoformat()
    until = (today - timedelta(days=30)).isoformat()
    assert count({'field': 'subscribed_at', 'operator': 'between', 'value': [since, until]}) == 1
    assert count({'field': 'subscribed_at', 'operator': 'between', 'value': [today.isoformat(), today.isoformat()]}) == 3
    assert count({'field': 'subscribed_at', 'operator': 'between', 'value': ['', until]}) == 1
    assert count({'field': 'subscribed_at', 'operator': 'not_within_last_days', 'value': 30}) == 1
    assert count({'field': 'engagement_score', 'operator': 'between', 'value': [0, 10]}) == 4
    bad = client.post('/api/segments/preview', headers=auth, json={'filter_rules': {'rules': [
        {'field': 'subscribed_at', 'operator': 'between', 'value': 'yesterday'}]}})
    assert bad.status_code == 400


def test_subscriber_filters_and_query(client, auth):
    _people(client, auth)
    today = utcnow().date().isoformat()
    old = (utcnow().date() - timedelta(days=45)).isoformat()
    r = client.get(f'/api/subscribers?subscribed_from={today}', headers=auth).get_json()
    assert r['total'] == 3
    r = client.get(f'/api/subscribers?subscribed_from={old}&subscribed_to={old[:8]}28', headers=auth).get_json()
    r = client.post('/api/subscribers/query', headers=auth, json={
        'status': 'active', 'rules': {'logic': 'AND', 'rules': [{'field': 'plan', 'operator': 'equals', 'value': 'pro'}]},
        'per_page': 10}).get_json()
    assert r['total'] == 2
    assert client.get('/api/subscribers?engagement_min=abc', headers=auth).status_code == 400


def test_bulk_actions(client, auth, other_auth):
    a, b, c, d = _people(client, auth)
    theirs = add_subscriber(client, other_auth, 'x@example.com')

    r = client.post('/api/subscribers/bulk-action', headers=auth,
                    json={'action': 'add_tag', 'value': 'october', 'ids': [a['id'], b['id'], theirs['id']]})
    assert r.get_json() == {'action': 'add_tag', 'affected': 2}
    assert 'october' not in db.session.get(Subscriber, theirs['id']).tags

    # "select all matching" by filter
    r = client.post('/api/subscribers/bulk-action', headers=auth,
                    json={'action': 'set_status', 'value': 'inactive', 'filters': {'tag': 'october'}})
    assert r.get_json()['affected'] == 2
    assert db.session.get(Subscriber, a['id']).status == 'inactive'

    r = client.post('/api/subscribers/bulk-action', headers=auth,
                    json={'action': 'remove_tag', 'value': 'october', 'filters': {'status': 'inactive'}})
    assert r.get_json()['affected'] == 2

    r = client.post('/api/subscribers/bulk-action', headers=auth, json={'action': 'delete', 'ids': [c['id']]})
    assert r.get_json()['affected'] == 1
    assert client.post('/api/subscribers/bulk-action', headers=auth, json={'action': 'explode', 'ids': []}).status_code == 400
    assert client.post('/api/subscribers/bulk-action', headers=auth, json={'action': 'add_tag', 'ids': [a['id']]}).status_code == 400


def test_campaign_list_filters(client, auth):
    template = create_template(client, auth)
    for name in ('Spring sale', 'Autumn news', 'Spring follow-up'):
        client.post('/api/campaigns', json={'name': name, 'template_id': template['id']}, headers=auth)
    old = Campaign.query.filter_by(name='Autumn news').one()
    old.created_at = utcnow() - timedelta(days=60)
    db.session.commit()
    names = lambda q: sorted(c['name'] for c in client.get(f'/api/campaigns?{q}', headers=auth).get_json()['items'])
    assert names('search=spring') == ['Spring follow-up', 'Spring sale']
    since = (utcnow().date() - timedelta(days=7)).isoformat()
    assert names(f'date_from={since}') == ['Spring follow-up', 'Spring sale']
    assert names(f'date_to={(utcnow().date() - timedelta(days=30)).isoformat()}') == ['Autumn news']


def test_analytics_custom_range_and_log_dates(client, auth, outbox):
    add_subscriber(client, auth, 'a@example.com')
    template = create_template(client, auth)
    campaign = client.post('/api/campaigns', json={'name': 'C', 'template_id': template['id']}, headers=auth).get_json()
    client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth)
    email_service.process_email_queue()
    today = utcnow().date()
    start = (today - timedelta(days=13)).isoformat()
    data = client.get(f'/api/analytics/engagement?date_from={start}&date_to={today.isoformat()}', headers=auth).get_json()
    assert data['days'] == 14 and len(data['daily']) == 14 and data['daily'][-1]['sent'] == 1
    past = client.get('/api/analytics/engagement?date_from=2026-01-01&date_to=2026-01-31', headers=auth).get_json()
    assert past['days'] == 31 and past['sent'] == 0 and past['daily'][0]['date'] == '2026-01-01'
    growth = client.get(f'/api/analytics/subscribers?date_from={start}', headers=auth).get_json()
    assert growth['new_subscribers'] == 1
    assert client.get('/api/analytics/engagement?date_from=2026-02-01&date_to=2026-01-01', headers=auth).status_code == 400
    logs = client.get(f'/api/analytics/email-logs?date_from={today.isoformat()}', headers=auth).get_json()
    assert logs['total'] == 1
    logs = client.get('/api/analytics/email-logs?date_to=2026-01-01', headers=auth).get_json()
    assert logs['total'] == 0
    assert EmailLog.query.count() == 1
