"""SMTP connection management (per-business connections with reuse)."""
import ipaddress
import logging
import smtplib
import socket
import ssl
import time

from flask import current_app

logger = logging.getLogger(__name__)


class SMTPConnectionError(Exception):
    """Could not connect / authenticate to the business's SMTP server."""


def is_loopback(host):
    try:
        return ipaddress.ip_address(socket.gethostbyname(host)).is_loopback
    except (OSError, ValueError):
        return False


def open_connection(host, port, username=None, password=None, use_tls=True, timeout=None):
    timeout = timeout or current_app.config.get('SMTP_TIMEOUT', 30)
    context = ssl.create_default_context()
    # A relay on this same machine (e.g. Postfix on 127.0.0.1) needs neither
    # TLS nor a login: the traffic never leaves the server.
    local = is_loopback(host)
    try:
        if int(port) == 465:
            conn = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        else:
            conn = smtplib.SMTP(host, port, timeout=timeout)
            conn.ehlo()
            if use_tls and not local:
                conn.starttls(context=context)
                conn.ehlo()
        if username:
            if conn.has_extn('auth'):
                conn.login(username, password or '')
            elif not local:
                raise smtplib.SMTPNotSupportedError(
                    'server does not offer AUTH (check the port and TLS setting)')
        return conn
    except (smtplib.SMTPException, OSError, socket.timeout) as exc:
        raise SMTPConnectionError(f'SMTP connection to {host}:{port} failed: {exc}') from exc


def connect_for_business(business):
    return open_connection(business.smtp_host, business.smtp_port, business.smtp_username,
                           business.smtp_password, business.smtp_tls)


def explain_smtp_error(text, host, port):
    """Turn a raw SMTP/TLS error into a hint about what to change."""
    low = text.lower()
    if 'certificate verify failed' in low or 'hostname mismatch' in low:
        return (f"The server's TLS certificate is not valid for '{host}'. Use the exact hostname on the "
                "mail server's certificate (not an IP address), or install a valid certificate for mail "
                "(in Plesk: Tools & Settings > SSL/TLS Certificates > certificate for securing mail).")
    if 'wrong version number' in low or 'unexpected eof' in low:
        return ('TLS mismatch between port and setting: use port 587 with STARTTLS on, '
                'or port 465 (SSL) for servers that expect TLS immediately.')
    if any(s in low for s in ('timed out', 'connection refused', 'no route to host', 'unreachable')):
        return (f'Cannot reach {host}:{port}. Check that the port is open on that server (in Plesk: '
                'Tools & Settings > Mail Server Settings > "Enable mail submission port 587"), that its '
                'firewall allows this server, and that Fail2Ban has not banned this server\'s IP.')
    if 'name or service not known' in low or 'nodename nor servname' in low or 'getaddrinfo' in low:
        return f"The hostname '{host}' does not resolve. Check the spelling."
    if 'does not offer auth' in low:
        return 'The server only allows login after STARTTLS: turn "Use STARTTLS" on.'
    if '535' in low or 'authentication' in low:
        return ('Username or password rejected. Use the full email address as the username and check '
                'the mailbox password (and that the mailbox is allowed to send).')
    return None


def test_connection(business):
    """Try to connect + authenticate; returns (ok, message)."""
    try:
        conn = connect_for_business(business)
    except SMTPConnectionError as exc:
        hint = explain_smtp_error(str(exc), business.smtp_host, business.smtp_port)
        return False, f'{exc}' + (f' -> {hint}' if hint else '')
    try:
        conn.quit()
    except smtplib.SMTPException:
        pass
    return True, 'SMTP connection successful'


def classify_smtp_error(exc):
    """Map an SMTP exception to 'hard' (permanent), 'soft' (retry) or 'connection'."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _ in exc.recipients.values()]
        code = codes[0] if codes else 550
        return ('hard' if 500 <= code < 600 else 'soft'), f'Recipient refused: {exc.recipients}'
    if isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                        smtplib.SMTPAuthenticationError, SMTPConnectionError, OSError)):
        return 'connection', str(exc)
    code = getattr(exc, 'smtp_code', None)
    if code is not None:
        if isinstance(exc, smtplib.SMTPSenderRefused):
            # Sender problems are our configuration, not the recipient's fault
            return 'connection' if code >= 500 else 'soft', str(exc)
        return ('hard' if 500 <= code < 600 else 'soft'), str(exc)
    return 'soft', str(exc)


class SMTPConnectionPool:
    """Keeps one live connection per business for the duration of a queue run.

    Connections are health-checked with NOOP before reuse and closed when idle
    for longer than ``max_idle`` seconds or when the pool is closed.
    """

    def __init__(self, max_idle=60, connector=None):
        self._connections = {}
        self.max_idle = max_idle
        self._connector = connector or connect_for_business

    def get(self, business):
        entry = self._connections.get(business.id)
        if entry is not None:
            conn, last_used = entry
            if time.monotonic() - last_used < self.max_idle and self._alive(conn):
                self._connections[business.id] = (conn, time.monotonic())
                return conn
            self.discard(business.id)
        conn = self._connector(business)
        self._connections[business.id] = (conn, time.monotonic())
        return conn

    @staticmethod
    def _alive(conn):
        try:
            return conn.noop()[0] == 250
        except (smtplib.SMTPException, OSError):
            return False

    def discard(self, business_id):
        entry = self._connections.pop(business_id, None)
        if entry is not None:
            try:
                entry[0].quit()
            except (smtplib.SMTPException, OSError):
                pass

    def close_all(self):
        for business_id in list(self._connections):
            self.discard(business_id)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close_all()
