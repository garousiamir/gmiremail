"""Command-line tools: flask --app wsgi backup create -o FILE"""
import os
import sys

import click

from app.services import backup_service


def register_cli(app):
    @app.cli.group()
    def backup():
        """Full-server backups."""

    @backup.command('create')
    @click.option('-o', '--output', required=True,
                  help='Path of the .tar.gz to write, or "-" for stdout')
    def create(output):
        """Write a full backup (database, secret keys, DKIM keys)."""
        if output == '-':
            path, manifest = backup_service.create_backup_tempfile()
            try:
                backup_service.copy_to(path, sys.stdout.buffer)
            finally:
                os.unlink(path)
        else:
            manifest = backup_service.create_backup(output)
        click.echo(f"Backup written ({manifest['counts']['subscribers']} subscribers, "
                   f"{manifest['counts']['email_logs']} email logs)", err=True)
