import smtplib

import pytest

from app import create_app, db
from app.services import smtp_service


class FakeSMTP:
    """Stands in for smtplib.SMTP. Recipients starting with "hard" are
    rejected permanently, "soft" temporarily."""

    def __init__(self, outbox):
        self.outbox = outbox

    def send_message(self, message):
        recipient = message['To']
        if recipient.startswith('hard'):
            raise smtplib.SMTPRecipientsRefused({recipient: (550, b'No such user')})
        if recipient.startswith('relay'):
            raise smtplib.SMTPRecipientsRefused({recipient: (554, b'5.7.1 <x>: Relay access denied')})
        if recipient.startswith('soft'):
            raise smtplib.SMTPRecipientsRefused({recipient: (451, b'Try again later')})
        self.outbox.append(message)
        return {}

    def noop(self):
        return (250, b'OK')

    def quit(self):
        pass


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(smtp_service, 'connect_for_business', lambda business: FakeSMTP(sent))
    return sent


def register(client, email='owner@acme.example.com', name='Acme', **extra):
    payload = {'name': name, 'email': email, 'password': 'supersecret', 'smtp_host': 'smtp.acme.test',
               'smtp_port': 587, 'smtp_username': 'mailer', 'smtp_password': 'pw',
               'physical_address': '1 Main St', **extra}
    response = client.post('/api/auth/register', json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


@pytest.fixture
def auth(client):
    data = register(client)
    return {'Authorization': f"Bearer {data['access_token']}"}


@pytest.fixture
def other_auth(client):
    data = register(client, email='owner@globex.example.com', name='Globex')
    return {'Authorization': f"Bearer {data['access_token']}"}


def create_template(client, auth, name='Welcome', **extra):
    payload = {'name': name, 'subject_line': 'Hello {{ first_name }}',
               'html_content': '<html><body><p>Hi {{ first_name }}</p>'
                               '<a href="https://example.com/page?a=1&amp;b=2">Link</a></body></html>',
               **extra}
    response = client.post('/api/templates', json=payload, headers=auth)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def add_subscriber(client, auth, email, **extra):
    response = client.post('/api/subscribers', json={'email': email, **extra}, headers=auth)
    assert response.status_code == 201, response.get_json()
    return response.get_json()
