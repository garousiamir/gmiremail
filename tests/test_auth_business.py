from tests.conftest import register


def test_register_login_refresh(client):
    data = register(client)
    assert data['business']['api_key'].startswith('emk_')
    assert 'smtp_password' not in data['business']

    response = client.post('/api/auth/login', json={'email': 'OWNER@acme.example.com', 'password': 'supersecret'})
    assert response.status_code == 200
    tokens = response.get_json()

    response = client.post('/api/auth/refresh', json={'refresh_token': tokens['refresh_token']})
    assert response.status_code == 200
    # An access token cannot be used as a refresh token
    response = client.post('/api/auth/refresh', json={'refresh_token': tokens['access_token']})
    assert response.status_code == 401


def test_login_rejects_bad_password(client):
    register(client)
    response = client.post('/api/auth/login', json={'email': 'owner@acme.example.com', 'password': 'wrong-password'})
    assert response.status_code == 401


def test_duplicate_registration(client):
    register(client)
    response = client.post('/api/auth/register', json={'name': 'X', 'email': 'owner@acme.example.com',
                                                       'password': 'supersecret'})
    assert response.status_code == 409


def test_auth_required(client):
    assert client.get('/api/businesses/me').status_code == 401
    assert client.get('/api/businesses/me', headers={'Authorization': 'Bearer junk'}).status_code == 401


def test_api_key_auth_and_rotation(client):
    data = register(client)
    key = data['business']['api_key']
    assert client.get('/api/businesses/me', headers={'X-API-Key': key}).status_code == 200
    response = client.post('/api/businesses/me/api-key/rotate', headers={'X-API-Key': key})
    new_key = response.get_json()['api_key']
    assert new_key != key
    assert client.get('/api/businesses/me', headers={'X-API-Key': key}).status_code == 401
    assert client.get('/api/businesses/me', headers={'X-API-Key': new_key}).status_code == 200


def test_update_business_and_password_change_revokes_tokens(client, auth):
    response = client.put('/api/businesses/me', json={'name': 'Acme Inc', 'daily_email_limit': 50}, headers=auth)
    assert response.status_code == 200
    assert response.get_json()['name'] == 'Acme Inc'

    response = client.put('/api/businesses/me', json={'api_key': 'hack'}, headers=auth)
    assert response.status_code == 400

    response = client.put('/api/businesses/me', json={'password': 'newpassword1', 'current_password': 'supersecret'},
                          headers=auth)
    assert response.status_code == 200
    assert client.get('/api/businesses/me', headers=auth).status_code == 401


def test_logout_revokes_tokens(client, auth):
    assert client.post('/api/auth/logout', headers=auth).status_code == 200
    assert client.get('/api/businesses/me', headers=auth).status_code == 401


def test_business_stats(client, auth):
    response = client.get('/api/businesses/stats', headers=auth)
    assert response.status_code == 200
    assert response.get_json()['subscribers']['total'] == 0
