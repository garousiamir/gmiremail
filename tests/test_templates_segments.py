from tests.conftest import add_subscriber, create_template


def test_template_crud_and_preview(client, auth):
    template = create_template(client, auth, html_content='<p>Hi {{ first_name }} from {{ city }}</p>')
    assert template['template_variables'] == ['city', 'first_name']

    response = client.post(f"/api/templates/{template['id']}/preview",
                           json={'sample_data': {'first_name': 'Bob', 'city': 'Rome'}}, headers=auth)
    preview = response.get_json()
    assert preview['subject'] == 'Hello Bob'
    assert 'Hi Bob from Rome' in preview['html']
    assert 'Hi Bob from Rome' in preview['text']

    response = client.put(f"/api/templates/{template['id']}", json={'subject_line': 'New {{ last_name }}'},
                          headers=auth)
    assert 'last_name' in response.get_json()['template_variables']


def test_template_variables_are_escaped_and_sandboxed(client, auth):
    template = create_template(client, auth, html_content='<p>{{ first_name }}</p>')
    response = client.post(f"/api/templates/{template['id']}/preview",
                           json={'first_name': '<script>alert(1)</script>'}, headers=auth)
    assert '<script>' not in response.get_json()['html']

    response = client.post('/api/templates', headers=auth, json={
        'name': 'evil', 'subject_line': 'x',
        'html_content': "{{ ''.__class__.__mro__[1].__subclasses__() }}"})
    template_id = response.get_json()['id']
    response = client.post(f'/api/templates/{template_id}/preview', json={}, headers=auth)
    assert response.status_code == 400


def test_template_syntax_error(client, auth):
    response = client.post('/api/templates', headers=auth,
                           json={'name': 'bad', 'subject_line': 'x', 'html_content': '{% if %}'})
    assert response.status_code == 400


def test_template_library(client, auth):
    library = client.get('/api/templates/library', headers=auth).get_json()['templates']
    assert {t['key'] for t in library} >= {'welcome', 'newsletter'}
    response = client.post('/api/templates/library/welcome', json={}, headers=auth)
    assert response.status_code == 201


def test_segments(client, auth):
    add_subscriber(client, auth, 'a@example.com', first_name='Ann', custom_fields={'plan': 'pro', 'seats': 10},
                   tags=['vip'])
    add_subscriber(client, auth, 'b@example.com', first_name='Bob', custom_fields={'plan': 'free', 'seats': 1})
    add_subscriber(client, auth, 'c@other.example.org', first_name='Cat', status='unsubscribed',
                   custom_fields={'plan': 'pro'})

    def count(rules):
        response = client.post('/api/segments/preview', json={'filter_rules': rules}, headers=auth)
        assert response.status_code == 200, response.get_json()
        return response.get_json()['subscriber_count']

    assert count({'rules': [{'field': 'status', 'operator': 'equals', 'value': 'active'}]}) == 2
    assert count({'rules': [{'field': 'custom_fields.plan', 'operator': 'equals', 'value': 'pro'}]}) == 2
    assert count({'rules': [{'field': 'plan', 'operator': 'in', 'value': ['pro', 'team']},
                            {'field': 'status', 'operator': 'equals', 'value': 'active'}], 'logic': 'AND'}) == 1
    assert count({'rules': [{'field': 'seats', 'operator': 'greater_than', 'value': 5}]}) == 1
    assert count({'rules': [{'field': 'email', 'operator': 'ends_with', 'value': '@example.com'}]}) == 2
    assert count({'rules': [{'field': 'first_name', 'operator': 'contains', 'value': 'an'}]}) == 1
    assert count({'rules': [{'field': 'tags', 'operator': 'contains', 'value': 'vip'}]}) == 1
    assert count({'rules': [{'field': 'created_at', 'operator': 'within_last_days', 'value': 1}]}) == 3
    assert count({'logic': 'OR', 'rules': [
        {'field': 'first_name', 'operator': 'equals', 'value': 'Bob'},
        {'logic': 'AND', 'rules': [{'field': 'plan', 'operator': 'equals', 'value': 'pro'},
                                   {'field': 'status', 'operator': 'equals', 'value': 'unsubscribed'}]},
    ]}) == 2
    # LIKE wildcards in values are literal
    assert count({'rules': [{'field': 'email', 'operator': 'contains', 'value': '%'}]}) == 0

    response = client.post('/api/segments/preview', headers=auth,
                           json={'filter_rules': {'rules': [{'field': 'x', 'operator': 'bogus', 'value': 1}]}})
    assert response.status_code == 400

    response = client.post('/api/segments', headers=auth, json={
        'name': 'Pro', 'filter_rules': {'rules': [{'field': 'plan', 'operator': 'equals', 'value': 'pro'}]}})
    segment = response.get_json()
    assert segment['subscriber_count'] == 2
    response = client.get(f"/api/segments/{segment['id']}/count", headers=auth)
    assert response.get_json() == {'segment_id': segment['id'], 'subscriber_count': 2, 'active_subscriber_count': 1}
