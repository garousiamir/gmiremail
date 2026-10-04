#!/usr/bin/env bash
# Restore a gmiremail backup (downloaded from Settings -> Backup) onto this server.
#   sudo deploy/restore.sh gmiremail-backup-YYYY-MM-DD-HHMM.tar.gz [--yes]
#
# Run deploy/install.sh first. This REPLACES all data on this server with the
# backup's: businesses, subscribers, campaigns, automations, analytics, the
# secret keys (old email links keep working) and the DKIM keys.
set -euo pipefail

FILE="${1:-}"
ASSUME_YES="${2:-}"
APP_USER="gmiremail"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="/etc/gmiremail/gmiremail.env"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root (sudo)."
[[ -n "$FILE" && -f "$FILE" ]] || die "Usage: sudo deploy/restore.sh <backup.tar.gz> [--yes]"
[[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found. Run deploy/install.sh on this server first."

TMP="$(mktemp -d /tmp/gmiremail-restore-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
# Refuse anything but plain files/dirs with safe relative names (this runs as root)
python3 - "$FILE" <<'PY' || die "The backup file is damaged or not a gmiremail backup."
import sys, tarfile
with tarfile.open(sys.argv[1], 'r:gz') as tar:
    for m in tar.getmembers():
        parts = m.name.split('/')
        if m.name.startswith('/') or '..' in parts or not (m.isfile() or m.isdir()):
            sys.exit(f'unsafe entry in archive: {m.name}')
PY
tar -xzf "$FILE" -C "$TMP" --no-same-owner
[[ -f "$TMP/manifest.json" ]] || die "Not a gmiremail backup (manifest.json missing)."

read_manifest() { python3 -c "import json,sys; m=json.load(open('$TMP/manifest.json')); print($1)"; }
[[ "$(read_manifest "m.get('app')")" == "gmiremail" ]] || die "Not a gmiremail backup."
[[ "$(read_manifest "m.get('format')")" == "1" ]] || die "Unsupported backup format; update this server's code (git pull)."
DB_KIND="$(read_manifest "m['database']")"
[[ "$DB_KIND" == "postgresql" && -f "$TMP/database.dump" ]] || \
  die "This backup was made from a $DB_KIND (development) install; only PostgreSQL backups can be restored here."

log "Backup contents"
read_manifest "'  created:      ' + m['created_at']"
read_manifest "'  hostname:     ' + str(m.get('tracking_domain'))"
read_manifest "'\n'.join(f'  {k + \":\":13} {v}' for k, v in m['counts'].items())"
read_manifest "'  DKIM domains: ' + (', '.join(m.get('dkim_domains') or []) or 'none')"

if [[ "$ASSUME_YES" != "--yes" ]]; then
  echo
  read -r -p "This REPLACES all data on this server. Type 'restore' to continue: " answer
  [[ "$answer" == "restore" ]] || die "Cancelled."
fi

log "Stopping the app"
systemctl stop gmiremail-web gmiremail-worker

log "Restoring the database"
chmod 755 "$TMP"
chmod 644 "$TMP/database.dump"
# Connects over the local socket as the app's own database role
runuser -u "$APP_USER" -- pg_restore --clean --if-exists --no-owner --no-privileges \
  --exit-on-error -d "$APP_USER" "$TMP/database.dump"

log "Restoring secret keys"
while IFS='=' read -r key value; do
  [[ "$key" =~ ^(SECRET_KEY|JWT_SECRET_KEY)$ && -n "$value" ]] || continue
  [[ "$value" =~ ^[A-Za-z0-9._~+/=-]+$ ]] || die "Unexpected characters in $key from the backup."
  if grep -q "^$key=" "$ENV_FILE"; then
    sed -i "s|^$key=.*|$key=$value|" "$ENV_FILE"
  else
    echo "$key=$value" >> "$ENV_FILE"
  fi
done < "$TMP/secrets.env"

if [[ -d "$TMP/dkim" ]]; then
  if command -v opendkim >/dev/null 2>&1; then
    log "Restoring DKIM keys"
    for domain_dir in "$TMP"/dkim/*/; do
      domain="$(basename "$domain_dir")"
      for key in "$domain_dir"*.private; do
        [[ -f "$key" ]] || continue
        selector="$(basename "$key" .private)"
        install -d -m 700 "/etc/opendkim/keys/$domain"
        install -m 600 "$key" "/etc/opendkim/keys/$domain/$selector.private"
        [[ -f "$domain_dir$selector.txt" ]] && install -m 644 "$domain_dir$selector.txt" "/etc/opendkim/keys/$domain/$selector.txt"
        "$APP_DIR/deploy/add-dkim-domain.sh" "$domain" "$selector" --quiet
        echo "  $domain (selector $selector)"
      done
    done
    systemctl restart opendkim
  else
    echo "Skipping DKIM keys: OpenDKIM is not installed (install.sh was run with --no-postfix)."
  fi
fi

log "Applying database migrations"
runuser -u "$APP_USER" -- bash -c "set -a; . '$ENV_FILE'; set +a; cd '$APP_DIR' && venv/bin/flask --app wsgi db upgrade"

log "Starting the app"
systemctl start gmiremail-web gmiremail-worker
sleep 2
if ! systemctl is-active --quiet gmiremail-web || ! systemctl is-active --quiet gmiremail-worker; then
  die "The app did not start: journalctl -u gmiremail-web -u gmiremail-worker"
fi

OLD_HOST="$(read_manifest "str(m.get('tracking_domain') or '')")"
NEW_HOST="$(sed -n 's/^TRACKING_DOMAIN=//p' "$ENV_FILE")"
log "Restore complete"
cat <<NEXT

Sign in with the same accounts and passwords as on the old server.

Still to do:
  1. Point the DNS A record of your hostname at this server's IP.
  2. Update SPF (ip4:...) and reverse DNS (PTR) for this server's IP.
  3. Warm up the new IP: keep DAILY_EMAIL_LIMIT low at first in $ENV_FILE.
NEXT
if [[ -n "$OLD_HOST" && "$OLD_HOST" != "$NEW_HOST" ]]; then
  echo
  echo "NOTE: the backup was made on $OLD_HOST but this server uses $NEW_HOST."
  echo "Links in emails sent from the old server point to $OLD_HOST and only keep working"
  echo "if that hostname points here. Set TRACKING_DOMAIN=$OLD_HOST in $ENV_FILE to keep using it."
fi
