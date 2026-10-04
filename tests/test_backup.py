import io
import json
import sqlite3
import tarfile

from tests.conftest import add_subscriber, create_template, register


def _open(response):
    return tarfile.open(fileobj=io.BytesIO(response.data), mode='r:gz')


def test_only_owner_with_password_can_download(client, auth, other_auth):
    # The first account created is the server owner
    me = client.get('/api/businesses/me', headers=auth).get_json()
    other = client.get('/api/businesses/me', headers=other_auth).get_json()
    assert me['is_admin'] is True and other['is_admin'] is False

    assert client.get('/api/admin/backup', headers=other_auth).status_code == 403
    assert client.post('/api/admin/backup', json={'password': 'supersecret'}, headers=other_auth).status_code == 403
    assert client.post('/api/admin/backup', json={'password': 'wrong-password'}, headers=auth).status_code == 403
    assert client.post('/api/admin/backup', json={}).status_code == 401


def test_backup_contains_everything(app, tmp_path, client, auth, other_auth):
    template = create_template(client, auth)
    add_subscriber(client, auth, 'a@example.com', custom_fields={'plan': 'pro'})
    add_subscriber(client, other_auth, 'b@example.com')
    client.post('/api/campaigns', json={'name': 'C', 'template_id': template['id']}, headers=auth)

    info = client.get('/api/admin/backup', headers=auth).get_json()
    assert info['counts']['subscribers'] == 2 and info['counts']['businesses'] == 2

    response = client.post('/api/admin/backup', json={'password': 'supersecret'}, headers=auth)
    assert response.status_code == 200
    assert response.headers['Content-Disposition'].startswith('attachment; filename=gmiremail-backup-')
    assert response.headers['Cache-Control'] == 'no-store'

    with _open(response) as tar:
        names = set(tar.getnames())
        assert {'manifest.json', 'README.txt', 'secrets.env', 'database.sqlite'} <= names
        manifest = json.load(tar.extractfile('manifest.json'))
        secrets = tar.extractfile('secrets.env').read().decode()
        db_bytes = tar.extractfile('database.sqlite').read()

    assert manifest['app'] == 'gmiremail' and manifest['format'] == 1
    assert manifest['database'] == 'sqlite'
    assert manifest['counts']['subscribers'] == 2 and manifest['counts']['campaigns'] == 1
    assert f"SECRET_KEY={app.config['SECRET_KEY']}" in secrets

    # The database copy is complete and readable
    path = tmp_path / 'restored.sqlite'
    with open(path, 'wb') as fh:
        fh.write(db_bytes)
    conn = sqlite3.connect(path)
    try:
        emails = sorted(r[0] for r in conn.execute('SELECT email FROM subscribers'))
        assert emails == ['a@example.com', 'b@example.com']
        assert conn.execute('SELECT count(*) FROM businesses').fetchone()[0] == 2
    finally:
        conn.close()


def test_admin_emails_setting(app, client):
    register(client, email='first@acme.example.com', name='First')
    second = register(client, email='boss@acme.example.com', name='Boss')
    app.config['ADMIN_EMAILS'] = ['boss@acme.example.com']
    headers = {'Authorization': f"Bearer {second['access_token']}"}
    assert client.get('/api/businesses/me', headers=headers).get_json()['is_admin'] is True


def test_cli_backup(app, tmp_path, client, auth):
    add_subscriber(client, auth, 'a@example.com')
    out = tmp_path / 'b.tar.gz'
    result = app.test_cli_runner().invoke(args=['backup', 'create', '-o', str(out)])
    assert result.exit_code == 0, result.output
    with tarfile.open(out) as tar:
        assert json.load(tar.extractfile('manifest.json'))['counts']['subscribers'] == 1
