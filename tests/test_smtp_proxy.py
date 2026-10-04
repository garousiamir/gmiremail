import smtplib

import pytest

from app import create_app, db
from app.services import smtp_service


class FakeServer:
    instances = []

    def __init__(self, host, port, timeout=None, extensions=('auth', 'starttls')):
        self.host = host
        self.extensions = set(FakeServer.extensions)
        self.calls = []
        FakeServer.instances.append(self)

    def ehlo(self):
        self.calls.append('ehlo')

    def has_extn(self, name):
        return name in self.extensions

    def starttls(self, context=None):
        if 'starttls' not in self.extensions:
            raise smtplib.SMTPNotSupportedError('STARTTLS extension not supported by server.')
        self.calls.append('starttls')

    def login(self, user, password):
        self.calls.append('login')


@pytest.fixture
def fake_smtp(monkeypatch, app):
    FakeServer.instances = []
    monkeypatch.setattr(smtplib, 'SMTP', FakeServer)
    return FakeServer


def test_remote_server_uses_tls_and_login(fake_smtp, monkeypatch):
    fake_smtp.extensions = {'auth', 'starttls'}
    monkeypatch.setattr(smtp_service, 'is_loopback', lambda host: False)
    smtp_service.open_connection('smtp.example.com', 587, 'user', 'pw', use_tls=True)
    assert fake_smtp.instances[0].calls == ['ehlo', 'starttls', 'ehlo', 'login']


def test_remote_server_without_auth_is_an_error(fake_smtp, monkeypatch):
    fake_smtp.extensions = {'starttls'}
    monkeypatch.setattr(smtp_service, 'is_loopback', lambda host: False)
    with pytest.raises(smtp_service.SMTPConnectionError, match='AUTH'):
        smtp_service.open_connection('smtp.example.com', 587, 'user', 'pw', use_tls=True)


def test_local_relay_skips_tls_and_login(fake_smtp):
    # Postfix on loopback: no STARTTLS, no AUTH; username/TLS settings are ignored
    fake_smtp.extensions = set()
    smtp_service.open_connection('127.0.0.1', 25, 'owner@example.com', '', use_tls=True)
    assert fake_smtp.instances[0].calls == ['ehlo']


def test_is_loopback():
    assert smtp_service.is_loopback('127.0.0.1')
    assert smtp_service.is_loopback('localhost')
    assert not smtp_service.is_loopback('10.1.2.3')
    assert not smtp_service.is_loopback('no-such-host.invalid')


def _ip_app(trusted_proxies):
    app = create_app('testing', config_overrides={'TRUSTED_PROXIES': trusted_proxies})

    @app.get('/_ip')
    def show_ip():
        from app.utils.helpers import client_ip
        return client_ip()
    return app


@pytest.mark.parametrize('trusted, expected', [(0, '127.0.0.1'), (1, '203.0.113.9')])
def test_client_ip_respects_trusted_proxies(trusted, expected):
    app = _ip_app(trusted)
    with app.app_context():
        client = app.test_client()
        # A forged first hop must never win; nginx appends the real address last
        response = client.get('/_ip', headers={'X-Forwarded-For': '6.6.6.6, 203.0.113.9'},
                              environ_base={'REMOTE_ADDR': '127.0.0.1'})
        assert response.get_data(as_text=True) == expected
        db.session.remove()
        db.drop_all()
