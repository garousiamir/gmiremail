"""Full-server backups: one .tar.gz with everything needed to move servers.

Archive layout::

    manifest.json     format version, created_at, database type, migration, row counts
    database.dump     PostgreSQL custom-format dump (pg_dump -Fc), or
    database.sqlite   for SQLite (development) installs
    secrets.env       SECRET_KEY / JWT_SECRET_KEY: keeps unsubscribe and click
                      links in already-sent emails valid, and logins working
    dkim/<domain>/    DKIM signing keys (production installs with Postfix)
    README.txt        how to restore

Restore on a new server with ``sudo deploy/restore.sh <file>`` (PostgreSQL).
"""
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile

from flask import current_app
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app import db
from app.models import Automation, Business, Campaign, EmailLog, EmailTemplate, Segment, Subscriber
from app.utils.helpers import ServiceError, utcnow

FORMAT_VERSION = 1

README = """gmiremail backup
================

This file contains ALL data on the server (every business, subscriber,
campaign, automation and analytics record) plus the secret keys.
Store it somewhere safe.

Restore on a new server (Ubuntu/Debian):

  sudo git clone https://github.com/garousiamir/gmiremail /opt/gmiremail
  cd /opt/gmiremail
  sudo deploy/install.sh --domain <same hostname> --email <you> --restore <this file>

or, on a server where install.sh already ran:

  sudo deploy/restore.sh <this file>

Then point the hostname's DNS A record at the new server and update SPF /
reverse DNS for the new IP (see docs/DEPLOYMENT.md, "Moving to a new server").
"""


def is_admin(business):
    """The server owner: listed in ADMIN_EMAILS, or else the first account created."""
    admins = current_app.config.get('ADMIN_EMAILS') or []
    if admins:
        return business.account_email.lower() in admins
    first = Business.query.order_by(Business.created_at, Business.id).first()
    return first is not None and first.id == business.id


def summary():
    return {
        'businesses': Business.query.count(),
        'subscribers': Subscriber.query.count(),
        'templates': EmailTemplate.query.count(),
        'segments': Segment.query.count(),
        'campaigns': Campaign.query.count(),
        'automations': Automation.query.count(),
        'email_logs': EmailLog.query.count(),
    }


def _migration_revision():
    try:
        return db.session.execute(text('SELECT version_num FROM alembic_version')).scalar()
    except Exception:  # noqa: BLE001 - table absent when tables were auto-created
        db.session.rollback()
        return None


def _dump_postgres(path):
    url = make_url(current_app.config['SQLALCHEMY_DATABASE_URI'])
    host = url.host or url.query.get('host')
    port = url.port or url.query.get('port')
    args = ['pg_dump', '--format=custom', f'--file={path}']
    if host:
        args.append(f'--host={host}')
    if port:
        args.append(f'--port={port}')
    if url.username:
        args.append(f'--username={url.username}')
    args.append(url.database)
    env = dict(os.environ)
    if url.password:
        env['PGPASSWORD'] = url.password  # never on the command line (visible in ps)
    try:
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise ServiceError('pg_dump is not installed on this server', 500)
    if result.returncode != 0:
        raise ServiceError('Database dump failed', 500, details=result.stderr.strip()[-500:])


def _dump_sqlite(path):
    raw = db.engine.raw_connection()
    try:
        target = sqlite3.connect(path)
        try:
            raw.driver_connection.backup(target)
        finally:
            target.close()
    finally:
        raw.close()


def _add_bytes(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = int(utcnow().timestamp())
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(data))


def create_backup(path):
    """Write a full backup archive to ``path``. Returns the manifest."""
    dialect = db.engine.dialect.name
    if dialect not in ('postgresql', 'sqlite'):
        raise ServiceError(f'Backups are not supported for {dialect}', 500)

    manifest = {
        'format': FORMAT_VERSION,
        'app': 'gmiremail',
        'created_at': utcnow().isoformat() + 'Z',
        'database': dialect,
        'migration_revision': _migration_revision(),
        'tracking_domain': current_app.config.get('TRACKING_DOMAIN'),
        'counts': summary(),
        'dkim_domains': [],
    }
    with tempfile.TemporaryDirectory(prefix='gmiremail-backup-') as tmp:
        dump_name = 'database.dump' if dialect == 'postgresql' else 'database.sqlite'
        dump_path = os.path.join(tmp, dump_name)
        if dialect == 'postgresql':
            _dump_postgres(dump_path)
        else:
            _dump_sqlite(dump_path)

        dkim_dir = current_app.config.get('DKIM_BACKUP_DIR')
        dkim_files = []
        if dkim_dir and os.path.isdir(dkim_dir):
            for domain in sorted(os.listdir(dkim_dir)):
                domain_dir = os.path.join(dkim_dir, domain)
                if not os.path.isdir(domain_dir):
                    continue
                for name in sorted(os.listdir(domain_dir)):
                    if name.endswith(('.private', '.txt')):
                        dkim_files.append((os.path.join(domain_dir, name), f'dkim/{domain}/{name}'))
                manifest['dkim_domains'].append(domain)

        secrets = (f"SECRET_KEY={current_app.config['SECRET_KEY']}\n"
                   f"JWT_SECRET_KEY={current_app.config['JWT_SECRET_KEY']}\n")
        with tarfile.open(path, 'w:gz') as tar:
            _add_bytes(tar, 'manifest.json', json.dumps(manifest, indent=2).encode())
            _add_bytes(tar, 'README.txt', README.encode())
            _add_bytes(tar, 'secrets.env', secrets.encode())
            tar.add(dump_path, arcname=dump_name)
            for source, arcname in dkim_files:
                tar.add(source, arcname=arcname)
    return manifest


def create_backup_tempfile():
    """Create a backup in a temp file; caller must delete it. Returns (path, manifest)."""
    handle, path = tempfile.mkstemp(prefix='gmiremail-', suffix='.tar.gz')
    os.close(handle)
    try:
        manifest = create_backup(path)
    except Exception:
        os.unlink(path)
        raise
    return path, manifest


def backup_filename():
    return f'gmiremail-backup-{utcnow():%Y-%m-%d-%H%M}.tar.gz'


def copy_to(path, out):
    """Stream a finished backup to a file object (CLI: stdout)."""
    with open(path, 'rb') as src:
        shutil.copyfileobj(src, out)
