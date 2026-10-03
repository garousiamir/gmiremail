from datetime import timedelta

from app import db
from app.models import AutomationInstance, EmailLog, Subscriber
from app.services import automation_service, email_service, tracking_service
from app.tasks import scheduled_tasks
from app.utils.helpers import utcnow
from tests.conftest import add_subscriber, create_template


def _welcome_automation(client, auth, welcome_id, followup_id):
    response = client.post('/api/automations', headers=auth, json={
        'name': 'Welcome series', 'trigger_type': 'new_subscriber',
        'workflow': {'steps': [
            {'id': 1, 'type': 'send_email', 'template_id': welcome_id, 'delay_days': 0},
            {'id': 2, 'type': 'wait', 'days': 2},
            {'id': 3, 'type': 'condition', 'condition': 'email_opened', 'if_true': 5, 'if_false': 4},
            {'id': 4, 'type': 'send_email', 'template_id': followup_id, 'next': 'end'},
            {'id': 5, 'type': 'add_tag', 'tag': 'engaged'},
        ]}})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _expire_wait(instance):
    instance.next_run_at = utcnow() - timedelta(seconds=1)
    db.session.commit()


def test_welcome_series_not_opened(client, auth, outbox):
    welcome = create_template(client, auth, name='Welcome')
    followup = create_template(client, auth, name='Reminder', subject_line='Did you see this?')
    automation = _welcome_automation(client, auth, welcome['id'], followup['id'])

    add_subscriber(client, auth, 'new@example.com', first_name='Nia')
    instance = AutomationInstance.query.one()
    assert instance.waiting_step == 1  # waiting on step id 2
    email_service.process_email_queue()
    assert [m['Subject'] for m in outbox] == ['Hello Nia']

    _expire_wait(instance)
    automation_service.execute_pending_automations()
    email_service.process_email_queue()
    assert [m['Subject'] for m in outbox] == ['Hello Nia', 'Did you see this?']
    instance = AutomationInstance.query.one()
    assert instance.status == 'completed'

    details = client.get(f"/api/automations/{automation['id']}", headers=auth).get_json()
    assert details['instances']['completed'] == 1


def test_welcome_series_opened(client, auth, outbox):
    welcome = create_template(client, auth, name='Welcome')
    followup = create_template(client, auth, name='Reminder')
    _welcome_automation(client, auth, welcome['id'], followup['id'])
    add_subscriber(client, auth, 'new@example.com')
    email_service.process_email_queue()
    log = EmailLog.query.one()
    tracking_service.track_email_open(log.id)

    _expire_wait(AutomationInstance.query.one())
    automation_service.execute_pending_automations()
    subscriber = Subscriber.query.one()
    assert subscriber.tags == ['engaged']
    assert EmailLog.query.count() == 1
    assert AutomationInstance.query.one().status == 'completed'


def test_inactive_automation_does_not_trigger(client, auth, outbox):
    welcome = create_template(client, auth)
    automation = _welcome_automation(client, auth, welcome['id'], welcome['id'])
    client.post(f"/api/automations/{automation['id']}/deactivate", headers=auth)
    add_subscriber(client, auth, 'new@example.com')
    assert AutomationInstance.query.count() == 0


def test_custom_event_and_unsubscribe_step(client, auth):
    add_subscriber(client, auth, 'buyer@example.com')
    client.post('/api/automations', headers=auth, json={
        'name': 'Cancel', 'trigger_type': 'custom_event', 'trigger_value': 'account_closed',
        'workflow': {'steps': [{'type': 'update_field', 'field': 'closed', 'value': True},
                               {'type': 'unsubscribe'}]}})
    response = client.post('/api/automations/events', headers=auth,
                           json={'event': 'account_closed', 'email': 'buyer@example.com'})
    assert response.get_json()['automations_started'] == 1
    subscriber = Subscriber.query.one()
    assert subscriber.status == 'unsubscribed'
    assert subscriber.custom_fields == {'closed': True}


def test_workflow_validation(client, auth, other_auth):
    template = create_template(client, auth)
    bad = [
        {'steps': []},
        {'steps': [{'type': 'teleport'}]},
        {'steps': [{'type': 'wait'}]},
        {'steps': [{'type': 'condition', 'condition': 'moon_phase'}]},
    ]
    for workflow in bad:
        response = client.post('/api/automations', headers=auth,
                               json={'name': 'x', 'trigger_type': 'new_subscriber', 'workflow': workflow})
        assert response.status_code == 400, workflow
    # Another tenant's template cannot be used
    response = client.post('/api/automations', headers=other_auth, json={
        'name': 'x', 'trigger_type': 'new_subscriber',
        'workflow': {'steps': [{'type': 'send_email', 'template_id': template['id']}]}})
    assert response.status_code == 404


def test_analytics_endpoints(client, auth, outbox):
    template = create_template(client, auth)
    add_subscriber(client, auth, 'a@example.com')
    add_subscriber(client, auth, 'b@example.com')
    campaign = client.post('/api/campaigns', json={'name': 'C', 'template_id': template['id']},
                           headers=auth).get_json()
    client.post(f"/api/campaigns/{campaign['id']}/send", json={}, headers=auth)
    email_service.process_email_queue()
    tracking_service.track_email_open(EmailLog.query.first().id)

    overview = client.get('/api/analytics/overview', headers=auth).get_json()
    assert overview['subscribers']['total'] == 2
    assert overview['emails']['sent'] == 2
    assert overview['open_rate'] == 50.0

    engagement = client.get('/api/analytics/engagement?days=7', headers=auth).get_json()
    assert len(engagement['daily']) == 7
    assert engagement['daily'][-1]['sent'] == 2

    growth = client.get('/api/analytics/subscribers', headers=auth).get_json()
    assert growth['new_subscribers'] == 2 and growth['daily'][-1]['total'] == 2

    comparison = client.get('/api/analytics/campaigns', headers=auth).get_json()
    assert comparison['campaigns'][0]['id'] == campaign['id']

    logs = client.get('/api/analytics/email-logs?status=opened', headers=auth).get_json()
    assert logs['total'] == 1

    result = scheduled_tasks.calculate_analytics()
    assert result['subscribers'] == 2
    opened = Subscriber.query.filter(Subscriber.total_opens == 1).one()
    assert opened.engagement_score > 0


def test_background_jobs(app, client, auth, outbox):
    add_subscriber(client, auth, 'a@example.com')
    assert scheduled_tasks.reset_daily_limits() == 1
    assert scheduled_tasks.process_bounces() == {'deactivated': 0, 'dropped': 0}
    assert scheduled_tasks.cleanup_old_data()['email_logs'] == 0
    scheduler = scheduled_tasks.build_scheduler(app)
    assert {job.id for job in scheduler.get_jobs()} == {
        'email_queue_processor', 'automation_executor', 'analytics_calculator',
        'bounce_processor', 'daily_cleanup', 'reset_daily_limits'}
