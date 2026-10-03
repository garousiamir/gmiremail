import io

from tests.conftest import add_subscriber


def test_subscriber_crud(client, auth):
    sub = add_subscriber(client, auth, 'Jane@Example.com', first_name='Jane', custom_fields={'plan': 'pro'},
                         tags=['vip'])
    assert sub['email'] == 'jane@example.com'

    response = client.post('/api/subscribers', json={'email': 'jane@example.com'}, headers=auth)
    assert response.status_code == 409
    response = client.post('/api/subscribers', json={'email': 'not-an-email'}, headers=auth)
    assert response.status_code == 400

    response = client.put(f"/api/subscribers/{sub['id']}", json={'custom_fields': {'city': 'Paris'}}, headers=auth)
    assert response.get_json()['custom_fields'] == {'plan': 'pro', 'city': 'Paris'}

    response = client.put(f"/api/subscribers/{sub['id']}/status", json={'status': 'unsubscribed'}, headers=auth)
    assert response.get_json()['status'] == 'unsubscribed'
    assert response.get_json()['unsubscribed_at']

    response = client.get('/api/subscribers?status=unsubscribed', headers=auth)
    assert response.get_json()['total'] == 1

    assert client.delete(f"/api/subscribers/{sub['id']}", headers=auth).status_code == 200
    assert client.get(f"/api/subscribers/{sub['id']}", headers=auth).status_code == 404


def test_bulk_import_json_with_duplicates(client, auth):
    add_subscriber(client, auth, 'existing@example.com')
    records = [{'email': f'user{i}@example.com', 'first_name': f'U{i}', 'company': 'Acme'} for i in range(100)]
    records += [{'email': 'existing@example.com'}, {'email': 'user1@example.com'}, {'email': 'bad'}]
    response = client.post('/api/subscribers/bulk', json={'subscribers': records}, headers=auth)
    result = response.get_json()
    assert response.status_code == 201
    assert result['created'] == 100
    assert result['skipped'] == 2
    assert result['failed'] == 1

    response = client.get('/api/subscribers?per_page=1&search=user5', headers=auth)
    item = response.get_json()['items'][0]
    assert item['custom_fields'] == {'company': 'Acme'}


def test_bulk_import_csv_upload(client, auth):
    csv_data = 'email,first_name,plan\na@example.com,A,pro\nb@example.com,B,free\n'
    response = client.post('/api/subscribers/bulk', headers=auth, content_type='multipart/form-data',
                           data={'file': (io.BytesIO(csv_data.encode()), 'subs.csv')})
    assert response.status_code == 201
    assert response.get_json()['created'] == 2


def test_export_csv_guards_formula_injection(client, auth):
    add_subscriber(client, auth, 'x@example.com', first_name='=HYPERLINK("evil")')
    response = client.post('/api/subscribers/export', json={}, headers=auth)
    assert response.status_code == 200
    assert response.mimetype == 'text/csv'
    body = response.get_data(as_text=True)
    assert 'x@example.com' in body
    assert "'=HYPERLINK" in body


def test_tenant_isolation(client, auth, other_auth):
    sub = add_subscriber(client, auth, 'private@example.com')
    assert client.get(f"/api/subscribers/{sub['id']}", headers=other_auth).status_code == 404
    assert client.delete(f"/api/subscribers/{sub['id']}", headers=other_auth).status_code == 404
    assert client.get('/api/subscribers', headers=other_auth).get_json()['total'] == 0
    # The same email can exist under another business
    add_subscriber(client, other_auth, 'private@example.com')
