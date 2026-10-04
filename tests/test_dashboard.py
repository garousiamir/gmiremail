from tests.conftest import add_subscriber, create_template


def test_dashboard_is_served_with_csp(client):
    assert client.get('/').headers['Location'].endswith('/app/')
    response = client.get('/app/')
    assert response.status_code == 200
    assert b'/static/dashboard/js/main.js' in response.data
    assert "script-src 'self'" in response.headers['Content-Security-Policy']
    assert client.get('/static/dashboard/js/main.js').status_code == 200
    assert client.get('/static/dashboard/css/app.css').status_code == 200


def test_render_unsaved_template(client, auth):
    response = client.post('/api/templates/render', headers=auth, json={
        'subject_line': 'Hi {{ first_name }}', 'html_content': '<p>{{ first_name }} from {{ city }}</p>',
        'sample_data': {'first_name': 'Zoe', 'city': 'Oslo'}})
    data = response.get_json()
    assert response.status_code == 200
    assert data['subject'] == 'Hi Zoe'
    assert 'Zoe from Oslo' in data['html']
    assert data['template_variables'] == ['city', 'first_name']
    bad = client.post('/api/templates/render', headers=auth, json={'subject_line': 'x', 'html_content': '{% if %}'})
    assert bad.status_code == 400


def test_known_fields(client, auth, other_auth):
    add_subscriber(client, auth, 'a@example.com', custom_fields={'plan': 'pro'}, tags=['vip'])
    add_subscriber(client, other_auth, 'b@example.com', custom_fields={'secret': 1}, tags=['other'])
    data = client.get('/api/subscribers/fields', headers=auth).get_json()
    assert data == {'custom_fields': ['plan'], 'tags': ['vip']}


def test_campaign_includes_names(client, auth):
    template = create_template(client, auth)
    campaign = client.post('/api/campaigns', json={'name': 'C', 'template_id': template['id']}, headers=auth).get_json()
    assert campaign['template_name'] == 'Welcome'
    assert campaign['segment_name'] is None
